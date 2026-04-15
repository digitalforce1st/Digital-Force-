"""
Digital Force — Chat API
Natural language SSE-streaming interface to the ASMIA agency.
"""

import json
import asyncio
import logging
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from database import get_db, AgentLog
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessage(BaseModel):
    message: str
    context: Optional[dict] = {}


@router.post("/stream")
async def chat_stream(
    body: ChatMessage,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Stream a natural language conversation with the Digital Force agency.
    Returns SSE with typed chunks:
      { type: "thinking" | "action" | "message" | "error" | "done", content: str }
    """

    async def generate():
        try:
            from agent.chat_agent import handle_chat_message
            async for chunk in handle_chat_message(
                message=body.message,
                context=body.context or {},
                user_id=user.get("sub", "unknown"),
            ):
                yield f"data: {json.dumps(chunk)}\n\n"
                await asyncio.sleep(0)
        except Exception as e:
            logger.error(f"[Chat] Stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        finally:
            yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"

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
    Return recent chat messages.
    User messages: level='user', assistant responses: level='info', agent='chat'
    """
    result = await db.execute(
        select(AgentLog)
        .where(AgentLog.agent == "chat")
        .order_by(AgentLog.created_at.asc())
        .limit(limit)
    )
    logs = result.scalars().all()

    messages = []
    for log in logs:
        messages.append({
            "id": log.id,
            "role": "user" if log.level == "user" else "assistant",
            "content": log.thought or "",
            "created_at": log.created_at.isoformat(),
        })

    return messages


@router.delete("/history")
async def clear_chat_history(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Clear all chat history for a fresh start."""
    from sqlalchemy import delete
    await db.execute(delete(AgentLog).where(AgentLog.agent == "chat"))
    await db.commit()
    return {"status": "cleared", "message": "Chat history cleared."}
