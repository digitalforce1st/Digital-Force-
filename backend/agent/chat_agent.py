"""
Digital Force — Chat Agent
The conversational brain of the agency. Understands intent, queries the DB,
takes action, and streams responses token-by-token like a senior strategist.
"""

import json
import logging
import asyncio
from typing import AsyncGenerator
from datetime import datetime

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are ASMIA — the Autonomous Social Media Intelligence Agency AI at Digital Force.

You speak like a world-class senior marketing strategist running a $50M agency.
You are confident, strategic, direct, and genuinely helpful. You are NOT a chatbot.

Your personality:
- You think out loud, sharing your reasoning before taking action
- You are honest about performance — you don't sugarcoat bad results
- You speak in first person: "I'm creating...", "I've found...", "Let me check..."
- You are concise but complete — no filler, no waffle
- You proactively suggest next steps after completing a request

Your capabilities:
- Create and manage marketing campaigns (goals)
- Research trends, competitors, and hashtags for any niche
- Plan content calendars with specific tasks across platforms
- Publish to LinkedIn, Facebook, Twitter, TikTok, Instagram, YouTube
- Monitor performance KPIs and replan campaigns based on real data
- Learn from training documents and apply that knowledge to campaigns
- Generate platform-native content (posts, carousels, reels, threads)
- Manage media assets and apply them to campaigns

How to respond:
1. First, briefly state what you understand the request to be
2. Describe the action you're taking
3. If creating something, confirm what was created and what happens next
4. Always end with a natural next step or question

When a user wants to create a campaign, acknowledge you're starting the planning process.
When they ask for status, pull real data and report honestly.
When they give feedback, incorporate it and explain your adjustments.

NEVER say "As an AI language model" or "I cannot". You ARE the agency. You CAN do it.
NEVER make up data. Only report what you actually find.
Keep responses under 300 words unless depth is specifically needed.
"""


async def handle_chat_message(
    message: str,
    context: dict,
    user_id: str,
) -> AsyncGenerator[dict, None]:
    """
    Core chat handler. Yields SSE-compatible dicts:
      { type: "thinking" | "action" | "message" | "error" | "done", content: str }
    """
    from agent.llm import stream_chat_response
    from database import Goal, AgentLog, async_session
    from sqlalchemy import select, desc

    # --- Step 1: Fetch platform state ------------------------------------------
    yield {"type": "thinking", "content": "Checking agency status..."}

    try:
        async with async_session() as session:
            goals_result = await session.execute(
                select(Goal).order_by(desc(Goal.created_at)).limit(20)
            )
            goals = goals_result.scalars().all()

        goals_context = "\n".join([
            f"- [{g.status.upper()}] \"{g.title}\" (id: {g.id}, progress: {g.progress_percent:.0f}%, "
            f"tasks: {g.tasks_completed}/{g.tasks_total})"
            for g in goals
        ]) if goals else "No campaigns created yet."

    except Exception as e:
        logger.warning(f"[ChatAgent] Could not fetch goals: {e}")
        goals_context = "Unable to fetch current campaign data."

    # --- Step 2: Detect intent and compute action hints -------------------------
    msg_lower = message.lower()
    intent_hints = []

    create_keywords = ["create", "launch", "start", "build", "new campaign", "new mission", "run a", "make a", "set up"]
    status_keywords = ["status", "what's happening", "how is", "update", "progress", "overview", "report"]
    approve_keywords = ["approve", "looks good", "go ahead", "execute", "start running"]
    replan_keywords = ["replan", "change the strategy", "pivot", "adjust", "rethink", "not working"]
    pause_keywords = ["pause", "stop", "halt", "cancel"]

    if any(k in msg_lower for k in create_keywords):
        intent_hints.append("The user likely wants to CREATE a new campaign.")
        yield {"type": "action", "content": "🎯 Detecting campaign creation request..."}
    elif any(k in msg_lower for k in status_keywords):
        intent_hints.append("The user wants a STATUS REPORT on their campaigns.")
        yield {"type": "action", "content": "📊 Pulling campaign data..."}
    elif any(k in msg_lower for k in approve_keywords):
        intent_hints.append("The user may want to APPROVE a plan.")
    elif any(k in msg_lower for k in replan_keywords):
        intent_hints.append("The user wants to REPLAN or ADJUST a campaign strategy.")
    elif any(k in msg_lower for k in pause_keywords):
        intent_hints.append("The user wants to PAUSE or STOP a campaign.")

    # --- Step 3: Build LLM prompt ----------------------------------------------
    user_prompt = f"""Current Agency State:
{goals_context}

Current Date/Time: {datetime.utcnow().strftime('%A, %B %d %Y, %H:%M UTC')}
User's context: {json.dumps(context) if context else 'None'}
Intent hints: {' '.join(intent_hints) if intent_hints else 'Interpret naturally.'}

User message: "{message}"

Respond as ASMIA. Be conversational, strategic, and action-oriented.
If the user is creating a campaign, tell them you're starting the planning process immediately.
If reporting status, be specific with the data above.
"""

    # --- Step 4: Stream LLM response -------------------------------------------
    full_response = ""
    try:
        async for token in stream_chat_response(system=SYSTEM_PROMPT, user=user_prompt):
            full_response += token
            yield {"type": "message", "content": token}
            await asyncio.sleep(0)
    except Exception as e:
        logger.error(f"[ChatAgent] LLM stream error: {e}")
        yield {"type": "error", "content": f"I encountered an issue connecting to the AI. Check your API keys in Settings."}
        return

    # --- Step 5: Execute side effects based on intent --------------------------
    if any(k in msg_lower for k in create_keywords):
        try:
            yield {"type": "action", "content": "⚙️ Registering campaign in the system..."}
            await _create_goal_from_message(message, user_id)
            yield {"type": "action", "content": "✅ Campaign registered. Planning agent launched in background."}
        except Exception as e:
            logger.warning(f"[ChatAgent] Goal creation side-effect failed: {e}")

    # --- Step 6: Persist to chat history ---------------------------------------
    try:
        async with async_session() as session:
            session.add(AgentLog(
                goal_id=context.get("goal_id"),
                agent="chat",
                level="user",
                thought=message,
            ))
            session.add(AgentLog(
                goal_id=context.get("goal_id"),
                agent="chat",
                level="info",
                thought=full_response,
            ))
            await session.commit()
    except Exception as e:
        logger.warning(f"[ChatAgent] Failed to persist chat history: {e}")


async def _create_goal_from_message(message: str, user_id: str):
    """Extract goal data from a message and create it in the DB."""
    import uuid
    from agent.llm import generate_json
    from database import Goal, async_session
    from api.goals import run_planning_agent

    extraction_prompt = f"""
Extract a social media campaign goal from this message: "{message}"

Return valid JSON:
{{
  "title": "Short campaign title (max 80 chars)",
  "description": "The full goal description for the planning agent",
  "platforms": ["linkedin", "facebook"],
  "priority": "normal"
}}

Rules:
- title should be descriptive but concise
- description should elaborate on the goal with any details mentioned
- platforms: only include platforms explicitly mentioned or strongly implied
- If no platforms mentioned, default to ["linkedin", "facebook"]
- priority: "urgent" if time pressure mentioned, "high" if important, else "normal"
"""

    try:
        goal_data = await generate_json(
            extraction_prompt,
            "Extract structured campaign goal from user message. Return JSON only."
        )
    except Exception:
        goal_data = {
            "title": message[:80],
            "description": message,
            "platforms": ["linkedin", "facebook"],
            "priority": "normal",
        }

    if not goal_data.get("description"):
        goal_data["description"] = message

    async with async_session() as session:
        goal = Goal(
            id=str(uuid.uuid4()),
            title=goal_data.get("title", message[:80]),
            description=goal_data.get("description", message),
            platforms=json.dumps(goal_data.get("platforms", ["linkedin", "facebook"])),
            priority=goal_data.get("priority", "normal"),
            status="planning",
            created_by=user_id,
        )
        session.add(goal)
        await session.commit()
        goal_id = goal.id

    initial_state = {
        "goal_id": goal_id,
        "goal_description": goal_data.get("description", message),
        "platforms": goal_data.get("platforms", ["linkedin", "facebook"]),
        "messages": [], "research_findings": {}, "campaign_plan": {},
        "tasks": [], "completed_task_ids": [], "failed_task_ids": [],
        "kpi_snapshot": {}, "needs_replan": False,
        "approval_status": "pending", "human_feedback": None,
        "new_skills_created": [], "next_agent": None, "error": None,
        "iteration_count": 0, "replan_count": 0, "current_task_id": None,
        "deadline": None, "asset_ids": [], "success_metrics": {}, "constraints": {},
    }

    # Fire planning agent in background (non-blocking)
    asyncio.create_task(run_planning_agent(goal_id, goal_data.get("description", message), initial_state))
    logger.info(f"[ChatAgent] Created goal {goal_id} and launched planning agent")
