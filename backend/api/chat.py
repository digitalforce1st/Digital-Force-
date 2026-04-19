"""
Digital Force — Chat API
SSE-streaming interface that pipes the LangClaw ReAct loop directly to the browser.
Every cognitive step (thinking, action, observation, token) is streamed in real time.
"""

import json
import asyncio
import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from database import get_db, ChatMessage
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessageBody(BaseModel):
    message: str
    context: Optional[dict] = {}


@router.post("/stream")
async def chat_stream(
    body: ChatMessageBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Fully transparent SSE stream. Pipes the LangClaw ReAct loop directly:
      thinking → action → observation → token (streamed) → done
    """
    user_id = user.get("sub", "unknown")

    # 1. Save user message
    msg_db = ChatMessage(
        id=str(uuid.uuid4()),
        user_id=user_id,
        role="user",
        content=body.message
    )
    db.add(msg_db)
    await db.commit()

    # 2. Get current active goal
    from database import Goal
    active_goals_query = select(Goal).where(
        Goal.created_by == user_id,
        Goal.status.in_(["planning", "executing", "awaiting_approval", "monitoring"])
    ).order_by(desc(Goal.created_at)).limit(1)
    active_goals_result = await db.execute(active_goals_query)
    active_goal = active_goals_result.scalar_one_or_none()

    # 3. Quick intent classification (non-blocking)
    requires_workflow = False
    approval_status = "none"
    try:
        from agent.llm import generate_json
        from database import AgencySettings
        cfg_res = await db.execute(select(AgencySettings).where(AgencySettings.user_id == user_id))
        cfg = cfg_res.scalar_one_or_none()

        clf_prompt = f"""Classify this user message in the context of an autonomous AI agency. 
User said: "{body.message}"

Return ONLY JSON:
{{
  "requires_workflow": <true if launching/executing a campaign or complex autonomous task, false otherwise>,
  "approval_status": "approved" | "rejected" | "none"
}}"""
        clf = await generate_json(clf_prompt)
        requires_workflow = clf.get("requires_workflow", False)
        approval_status = clf.get("approval_status", "none")

        if approval_status == "approved" and active_goal and active_goal.status == "awaiting_approval":
            active_goal.status = "executing"
            active_goal.approved_by = user_id
            active_goal.approved_at = datetime.utcnow()
            await db.commit()

    except Exception as e:
        logger.warning(f"[Chat] Intent classification failed: {e}")

    async def generate():
        try:
            from langclaw_agents.chat_orchestrator import stream_chat_agent

            async for event in stream_chat_agent(
                user_id=user_id,
                message=body.message,
                goal_id=active_goal.id if active_goal else None,
                requires_workflow=requires_workflow,
            ):
                yield f"data: {json.dumps(event)}\n\n"
                await asyncio.sleep(0)  # yield control to event loop

        except Exception as e:
            logger.error(f"[Chat] Fatal stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/history")
async def get_chat_history(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
    limit: int = 100,
):
    user_id = user.get("sub", "unknown")
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
    )
    messages = result.scalars().all()
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "agent_name": m.agent_name,
            "goal_id": m.goal_id,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@router.get("/updates")
async def get_chat_updates(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
    since: Optional[str] = Query(None),
):
    """Background campaign update polling — keeps the chat alive for autonomous agents."""
    from database import Goal, AgentLog
    user_id = user.get("sub", "unknown")

    active_goals_result = await db.execute(
        select(Goal).where(
            Goal.created_by == user_id,
            Goal.status.in_(["planning", "executing", "awaiting_approval", "monitoring"])
        ).limit(1)
    )
    active_goal = active_goals_result.scalar_one_or_none()
    agents_active = active_goal is not None

    current_activity = None
    if active_goal:
        log_res = await db.execute(
            select(AgentLog)
            .where(AgentLog.goal_id == active_goal.id)
            .order_by(desc(AgentLog.created_at)).limit(1)
        )
        latest_log = log_res.scalar_one_or_none()
        if latest_log:
            current_activity = f"{latest_log.agent.upper()}: {latest_log.thought}"

    query = (
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .where(ChatMessage.role == "agent")
        .order_by(ChatMessage.created_at.asc())
    )
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            since_naive = since_dt.replace(tzinfo=None)
            query = query.where(ChatMessage.created_at > since_naive)
        except ValueError:
            pass

    result = await db.execute(query)
    messages = result.scalars().all()

    return {
        "agents_active": agents_active,
        "current_activity": current_activity,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "agent_name": m.agent_name,
                "goal_id": m.goal_id,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }


@router.delete("/history")
async def clear_chat_history(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    from sqlalchemy import delete
    user_id = user.get("sub", "unknown")
    await db.execute(delete(ChatMessage).where(ChatMessage.user_id == user_id))
    await db.commit()
    return {"status": "cleared"}
