import json
import logging
import base64
import os
import aiofiles
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from groq import AsyncGroq
import httpx
from pydantic import BaseModel

from config import get_settings
from groq import AsyncGroq
import random
from database import async_session, Goal
from sqlalchemy import select, desc
import asyncio

# Imports to actually trigger the agent without needing FastAPI BackgroundTasks mapping
from api.goals import run_planning_agent, _run_execution_agent
import uuid
from datetime import datetime
router = APIRouter()
settings = get_settings()

def _get_groq_client():
    key = settings.groq_api_key_1 or settings.groq_api_key_2 or settings.groq_api_key_3
    if not key:
        raise Exception("No Groq API keys configured.")
    return AsyncGroq(api_key=key, max_retries=1)

def rotate_api_keys(keys):
    if not keys: return None
    return random.choice(keys)

class VoiceManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"🎤 Voice WebSocket Connected.")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("🎤 Voice WebSocket Disconnected.")

manager = VoiceManager()

async def get_groq_tts(text: str) -> bytes:
    """Uses Groq API (OpenAI compatible) to get PlayAI/Orpheus TTS audio bytes."""
    keys = [k for k in [settings.groq_api_key_1, settings.groq_api_key_2, settings.groq_api_key_3] if k]
    if not keys:
         raise Exception("No Groq API keys configured.")
    # Assuming PlayAI model name on Groq is "playai-dialog" or similar. 
    # NOTE: Since the exact string name is fresh, we will use HTTPX directly to hit the standard spec.
    api_key = rotate_api_keys(keys)
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # As a fallback if Groq's TTS endpoint isn't fully migrated, we use standard OpenAI spec
    # since PlayAI via Groq supports OpenAI endpoints.
    payload = {
        "model": "playai-dialog", # Placeholder for the active PlayAI on Groq
        "input": text,
        "voice": "alloy",
        "response_format": "mp3"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                "https://api.groq.com/openai/v1/audio/speech",
                headers=headers,
                json=payload,
                timeout=10.0
            )
            if resp.status_code == 200:
                return resp.content
            else:
                 logger.warning(f"Groq TTS failed ({resp.status_code}): {resp.text}")
                 return b""
        except Exception as e:
            logger.error(f"Groq TTS HTTP error: {e}")
            return b""


@router.websocket("/stream")
async def voice_stream(websocket: WebSocket):
    await manager.connect(websocket)
    
    # ── Tool Definitions for Groq LLM ──
    voice_tools = [
        {
            "type": "function",
            "function": {
                "name": "get_active_goals",
                "description": "Get a list of currently active goals/campaigns in the system, including their id and status.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "create_campaign_goal",
                "description": "Create a new campaign or orchestration goal and start planning it.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Short title of the campaign"},
                        "description": {"type": "string", "description": "Full description of what to do"}
                    },
                    "required": ["title", "description"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "approve_goal",
                "description": "Approve a goal that is 'awaiting_approval' and execute it.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "goal_id": {"type": "string", "description": "The ID of the goal to approve."}
                    },
                    "required": ["goal_id"]
                }
            }
        }
    ]

    # Temporary history for the session
    chat_history = [
        {"role": "system", "content": "You are Digital Force, an autonomous Orchestrator. You control the system. You can create campaigns, check statuses, and approve plans for the user using your tools. Keep spoken answers extremely short and direct."}
    ]
    
    try:
        while True:
            # Receive audio Blob as bytes
            data = await websocket.receive_bytes()
            logger.info(f"🎤 Received audio chunk: {len(data)} bytes")
            
            # Save temporary WEBM/MP4 chunk locally for Groq STT processing
            temp_path = "temp_audio_chunk.webm"
            async with aiofiles.open(temp_path, "wb") as f:
                await f.write(data)
                
            client = _get_groq_client()
            
            # 1. Speech to Text (Whisper)
            try:
                with open(temp_path, "rb") as audio_file:
                    transcription = await client.audio.transcriptions.create(
                        file=(temp_path, audio_file.read()),
                        model="whisper-large-v3-turbo",
                        response_format="text"
                    )
                user_text = transcription.strip()
                if not user_text:
                    await websocket.send_json({"type": "info", "message": "Could not hear audio."})
                    continue
                    
                logger.info(f"🧑 User Said: {user_text}")
                await websocket.send_json({"type": "stt", "text": user_text})
                
                chat_history.append({"role": "user", "content": user_text})
            
            except Exception as e:
                logger.error(f"STT Error: {e}")
                await websocket.send_json({"type": "error", "message": "Failed to transcribe audio."})
                continue
                
            finally:
                if os.path.exists(temp_path):
                     os.remove(temp_path)

            # 2. Fast Agent Brain (Langclaw Voice Spoke)
            try:
                response = await client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=chat_history,
                    tools=voice_tools,
                    tool_choice="auto",
                    temperature=0.6,
                    max_tokens=250
                )
                message = response.choices[0].message
                
                # Check for Tool Calls
                agent_text = ""
                if message.tool_calls:
                    tool_call = message.tool_calls[0]
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"🛠️ Voice triggered tool: {func_name}({args})")
                    
                    system_msg = ""
                    if func_name == "get_active_goals":
                        async with async_session() as db:
                            res = await db.execute(select(Goal).where(Goal.status.in_(["planning", "awaiting_approval", "executing", "monitoring"])))
                            goals = res.scalars().all()
                            if not goals:
                                system_msg = "Currently, there are no active goals or campaigns."
                            else:
                                system_msg = "System Status:\n" + "\n".join([f"- '{g.title}' (ID {g.id}) is {g.status}." for g in goals])
                    
                    elif func_name == "create_campaign_goal":
                        goal_id = str(uuid.uuid4())
                        goal = Goal(
                            id=goal_id,
                            title=args.get("title", "Voice Campaign"),
                            description=args.get("description", ""),
                            platforms=json.dumps([]),
                            status="planning",
                            priority="high"
                        )
                        async with async_session() as db:
                            db.add(goal)
                            await db.commit()
                        
                        # Fire Background task
                        initial_state = {
                            "goal_id": goal.id, "goal_description": args.get("description", ""),
                            "platforms": [], "asset_ids": [], "success_metrics": {}, "constraints": {},
                            "messages": [], "research_findings": {}, "campaign_plan": {}, "tasks": [],
                            "completed_task_ids": [], "failed_task_ids": [], "kpi_snapshot": {},
                            "needs_replan": False, "approval_status": "pending", "human_feedback": None,
                            "new_skills_created": [], "next_agent": None, "error": None, "iteration_count": 0,
                            "replan_count": 0, "current_task_id": None
                        }
                        asyncio.create_task(run_planning_agent(goal.id, args.get("description", ""), initial_state))
                        system_msg = f"Success. Orchestration initialized for goal {goal_id}."
                        
                    elif func_name == "approve_goal":
                        goal_id = args.get("goal_id")
                        async with async_session() as db:
                            goal = await db.get(Goal, goal_id)
                            if goal and goal.status == "awaiting_approval":
                                goal.status = "executing"
                                goal.approved_at = datetime.utcnow()
                                await db.commit()
                                asyncio.create_task(_run_execution_agent(goal_id))
                                system_msg = "Authorization confirmed. Protocol executing."
                            else:
                                system_msg = f"Cannot approve. Goal {goal_id} not found or not awaiting authorization."
                                
                    # Drop the tool call to history so it doesn't crash Groq, then get voice response
                    # Note: We must append message first, but groq strict schemas require a specific format.
                    # Instead of full tool back-and-forth, we just inject the system result as a system prompt to save tokens
                    # and ask it to say it out loud.
                    chat_history.append({"role": "system", "content": f"TOOL_RESULT [{func_name}]: {system_msg}. Please summarize this result out loud to the user briefly."})
                    
                    response2 = await client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=chat_history,
                        temperature=0.6,
                        max_tokens=150
                    )
                    agent_text = response2.choices[0].message.content
                else:
                    agent_text = message.content

                chat_history.append({"role": "assistant", "content": agent_text})
                
                logger.info(f"🤖 Agent Said: {agent_text}")
                await websocket.send_json({"type": "llm", "text": agent_text})
                
            except Exception as e:
                logger.error(f"LLM Error: {e}", exc_info=True)
                await websocket.send_json({"type": "error", "message": "Failed to generate reply."})
                continue
                
            # 3. Text to Speech (PlayAI on Groq)
            try:
                audio_bytes = await get_groq_tts(agent_text)
                if audio_bytes:
                     # Send base64 audio over websocket to play directly
                     b64_audio = base64.b64encode(audio_bytes).decode('utf-8')
                     await websocket.send_json({"type": "tts", "audio_b64": b64_audio})
                else:
                     await websocket.send_json({"type": "error", "message": "TTS Failed. Continuing text only."})
            except Exception as e:
                 logger.error(f"TTS execution error: {e}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Unexpected Voice Stream Error: {e}")
        manager.disconnect(websocket)
