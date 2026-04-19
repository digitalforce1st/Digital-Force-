"""
Digital Force — Chat API
SSE-streaming interface to the ASMIA agency with persistent memory and agent push polling.
"""

import json
import asyncio
import logging
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
    Pass the message directly to the LangGraph execution graph.
    The graph's nodes (like Executive) will push real-time responses to the DB,
    which the frontend polls.
    """
    user_id = user.get("sub", "unknown")
    
    # 1. Save user message to DB
    from database import ChatMessage
    import uuid
    msg_db = ChatMessage(
        id=str(uuid.uuid4()),
        user_id=user_id,
        role="user",
        content=body.message
    )
    db.add(msg_db)
    await db.commit()

    async def generate():
        try:
            yield f"data: {json.dumps({'type': 'action', 'content': 'Transmitting to Digital Force...'})}\n\n"
            await asyncio.sleep(0.1)

            # Fetch goals or context if any
            from database import Goal
            active_goals_query = select(Goal).where(
                Goal.created_by == user_id,
                Goal.status.in_(["planning", "executing", "awaiting_approval", "monitoring"])
            ).order_by(desc(Goal.created_at)).limit(1)
            active_goals_result = await db.execute(active_goals_query)
            active_goal = active_goals_result.scalar_one_or_none()
            
            # We want to pull recent history as well
            hist_result = await db.execute(
                select(ChatMessage)
                .where(ChatMessage.user_id == user_id)
                .order_by(desc(ChatMessage.created_at)).limit(10)
            )
            hist = hist_result.scalars().all()
            hist_msgs = [{"role": m.role if m.role != "agent" else "assistant", "content": f"[{m.agent_name}]: {m.content}" if m.agent_name and m.role == "agent" else m.content} for m in reversed(hist)]
            
            # Initial state mapping natively eliminated by LangClaw. 
            # Chat history fetched directly in chat_orchestrator using DB queries.
            
            # ---- LLM EVALUATION (INSTANT STREAMING) ----
            from agent.llm import generate_json
            
            agent_tone = "Highly professional, direct, and slightly futuristic"
            from database import AgencySettings, PlatformConnection
            from sqlalchemy import or_
            cfg_res = await db.execute(select(AgencySettings).where(AgencySettings.user_id == user_id))
            cfg = cfg_res.scalar_one_or_none()
            if cfg and cfg.agent_tone:
                agent_tone = cfg.agent_tone
                
            prompt = f"""You are the central Orchestrator Hub of Digital Force, an autonomous social media marketing agency.
You are talking to the human operator/owner of this agency. Provide a direct, highly competent, and brief response to their last message. DO NOT hallucinate technical framework specifications or claim technical difficulties.
Your persona and tone: {agent_tone}

Recent context:
{json.dumps(hist_msgs[-4:], indent=2)}

Determine if the user's latest message requires running any background autonomous tools (e.g. they want you to search the web, execute a script, analyze database metrics, or launch a social media operation). If yes, set 'requires_workflow' to true. If they are just chatting or answering a question, set it to false.
If the user is approving a previously proposed plan, mark approval_status as "approved". If rejecting, mark "rejected". Otherwise "none".
If the user is explicitly providing credentials, a password, a 2FA code, or telling you to inherently update the 'Truth Bucket' for an account, provide the account name you detect, and the specific text to append to their auth_data bucket.

Return strictly JSON:
{{
  "reply": "Your dynamic response to the user, in character.",
  "requires_workflow": <boolean>,
  "approval_status": "approved" | "rejected" | "none",
  "update_truth_bucket": {{
     "account_name_match": "string matching account name (e.g. 'Acme Corp') or null",
     "text_to_append": "Exact credential string to append safely to DB (e.g. 'Backup pass: 123') or null"
  }}
}}"""
            try:
                response = await generate_json(prompt)
                reply = response.get("reply", "Acknowledged.")
                requires_workflow = response.get("requires_workflow", False)
                approval_status = response.get("approval_status", "none")
                truth_update = response.get("update_truth_bucket")
                
                if truth_update and isinstance(truth_update, dict) and truth_update.get("account_name_match"):
                    account_match = truth_update.get("account_name_match")
                    text_to_append = truth_update.get("text_to_append")
                    if text_to_append:
                        match_str = f"%{account_match}%"
                        conn = (await db.execute(select(PlatformConnection).where(or_(PlatformConnection.account_label.ilike(match_str), PlatformConnection.display_name.ilike(match_str))))).scalars().first()
                        if conn:
                            conn.auth_data = (f"{conn.auth_data or ''}"
                                               f"\n[Agent Auto-Saved Update]: {text_to_append}").strip()
                            await db.commit()
            except Exception as e:
                reply = "Acknowledged. Routing internal systems to compensate."
                requires_workflow = True
                approval_status = "none"

            # Save the agent reply directly to DB so it persists
            bot_msg_id = str(uuid.uuid4())
            db.add(ChatMessage(id=bot_msg_id, user_id=user_id, role="agent", agent_name="orchestrator", content=reply, goal_id=active_goal.id if active_goal else None))
            await db.commit()

            # STREAM RESULT TO UI IMMEDIATELY
            yield f"data: {json.dumps({'type': 'bubble_start', 'bubble_id': bot_msg_id})}\n\n"
            chunk_size = 5
            for i in range(0, len(reply), chunk_size):
                yield f"data: {json.dumps({'type': 'message', 'content': reply[i:i+chunk_size]})}\n\n"
                await asyncio.sleep(0.01)
            yield f"data: {json.dumps({'type': 'bubble_end'})}\n\n"

            # ── Execute LangClaw God-Node (Chat Orchestrator) ──
            from langclaw_agents.chat_orchestrator import run_chat_agent
            
            if approval_status == "approved" and active_goal and active_goal.status == "awaiting_approval":
                active_goal.status = "executing"
                active_goal.approved_by = user_id
                active_goal.approved_at = datetime.utcnow()
                await db.commit()

            asyncio.create_task(run_chat_agent(user_id, body.message, active_goal.id if active_goal else None, requires_workflow))
            yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"
        except Exception as e:
            logger.error(f"[Chat] Stream error: {e}")
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
    """
    Return recent chat messages for the current user.
    Includes user, assistant, and agent-pushed messages.
    """
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
    since: Optional[str] = Query(None, description="ISO timestamp — return messages created after this"),
):
    """
    Polling endpoint for agent-pushed messages since a given timestamp.
    Frontend calls this every 10s to pick up autonomous agent updates.
    Returns { "messages": [...], "agents_active": True/False }
    """
    from database import Goal
    user_id = user.get("sub", "unknown")

    # 1. Fetch active goals to determine if agents are currently running
    active_goals_query = select(Goal).where(
        Goal.created_by == user_id,
        Goal.status.in_(["planning", "executing", "awaiting_approval", "monitoring"])
    ).limit(1)
    active_goals_result = await db.execute(active_goals_query)
    active_goal = active_goals_result.scalar_one_or_none()
    agents_active = active_goal is not None

    current_activity = None
    if active_goal:
        from database import AgentLog
        from sqlalchemy import desc
        log_res = await db.execute(select(AgentLog).where(AgentLog.goal_id == active_goal.id).order_by(desc(AgentLog.created_at)).limit(1))
        latest_log = log_res.scalar_one_or_none()
        if latest_log:
            current_activity = f"{latest_log.agent.upper()}: {latest_log.thought}"

    # 2. Fetch new agent messages
    query = (
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .where(ChatMessage.role == "agent")
        .order_by(ChatMessage.created_at.asc())
    )

    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            # Use naive UTC comparison — strip tzinfo to match DB datetime
            since_naive = since_dt.replace(tzinfo=None)
            query = query.where(ChatMessage.created_at > since_naive)
        except ValueError:
            pass  # Bad timestamp — return all agent messages

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
        ]
    }


@router.delete("/history")
async def clear_chat_history(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Clear all chat history for the current user."""
    from sqlalchemy import delete
    user_id = user.get("sub", "unknown")
    await db.execute(
        delete(ChatMessage).where(ChatMessage.user_id == user_id)
    )
    await db.commit()
    return {"status": "cleared", "message": "Chat history cleared."}
