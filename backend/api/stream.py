"""Digital Force — SSE Stream for real-time agent activity feed."""
import asyncio
import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, desc
from database import get_db, AgentLog
from auth import get_current_user, decode_token

router = APIRouter(prefix="/api/stream", tags=["stream"])
logger = logging.getLogger(__name__)


@router.get("/goals/{goal_id}")
async def stream_goal_activity(
    goal_id: str,
    token: Optional[str] = Query(None),  # For EventSource (can't set headers)
    user: dict = Depends(get_current_user),
):
    """SSE endpoint — streams agent log updates for a specific goal."""
    async def event_generator():
        last_log_id = None
        yield f"data: {json.dumps({'type': 'connected', 'goal_id': goal_id})}\n\n"
        for _ in range(600):  # Max 10 minutes
            try:
                from database import async_session
                async with async_session() as db:
                    q = (
                        select(AgentLog)
                        .where(AgentLog.goal_id == goal_id)
                        .order_by(desc(AgentLog.created_at))
                        .limit(10)
                    )
                    result = await db.execute(q)
                    logs = result.scalars().all()
                    new_logs = []
                    for log in reversed(logs):
                        if log.id != last_log_id:
                            new_logs.append(log)
                    for log in new_logs:
                        last_log_id = log.id
                        event = {
                            "type": "agent_log",
                            "agent": log.agent,
                            "level": log.level,
                            "thought": log.thought,
                            "action": log.action,
                            "timestamp": log.created_at.isoformat(),
                        }
                        yield f"data: {json.dumps(event)}\n\n"
            except Exception as e:
                logger.error(f"[Stream] Error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            # Keep-alive ping every 15s
            if _ % 15 == 0:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
            await asyncio.sleep(1)
        yield f"data: {json.dumps({'type': 'stream_ended'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
