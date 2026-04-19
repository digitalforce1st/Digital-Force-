"""
Digital Force — Reflector Node
Post-campaign analysis and Episodic Memory Generation.
Upgraded in v2.0 to also write lessons directly into agent skill markdown files.
"""
import logging
import uuid
import json
from datetime import datetime
from agent.state import AgentState
from agent.llm import generate_completion
from agent.chat_push import agent_thought_push, chat_push
from database import async_session, KnowledgeItem

logger = logging.getLogger(__name__)

async def reflector_node(state: AgentState) -> dict:
    """
    Evaluates completed campaigns to extract actionable lessons and saves them:
    1. Into Qdrant as Episodic Memory so the Strategist learns.
    2. Into the relevant agent's skill markdown file so the agent directly
       evolves its own behavior for the next campaign.
    """
    goal_id = state['goal_id']
    user_id = state.get('created_by', '')
    logger.info(f"[Reflector] Analyzing completed goal {goal_id} for Episodic Memory.")

    await agent_thought_push(
        user_id=user_id,
        context="campaign completed. engaging neural reflection to generate episodic memories for future campaigns",
        agent_name="reflector",
        goal_id=goal_id
    )

    plan = str(state.get("campaign_plan", {}))
    kpis = state.get("kpi_snapshot", {})
    failed_tasks = state.get("failed_task_ids", [])
    platforms = state.get("platforms", [])
    platform_str = ", ".join(platforms) if platforms else "unknown"

    prompt = f"""You are the Reflector Node of an autonomous social media agency.
A campaign just finished.

Plan executed:
{plan[:1500]}

KPI Snapshot:
Total Tasks: {kpis.get('total_tasks', 0)}
Failed Tasks: {len(failed_tasks)}
Platforms: {platform_str}

Extract TWO things:
1. ONE core "Campaign Lesson" for the Strategist (what to do differently next campaign).
2. ONE "Agent Refinement" — identify which specific agent made the biggest impact or mistake
   (content_director, strategist, researcher, publisher) and what rule they should learn.

Return JSON only:
{{
  "campaign_lesson": "A single actionable sentence about the overall campaign.",
  "agent_refinement": {{
    "agent": "content_director",
    "lesson": "A specific behavioral lesson for this agent.",
    "old_rule_hint": "Optional: a phrase from the agent's rules that should be updated, or null"
  }}
}}"""

    try:
        from agent.llm import generate_json
        response = await generate_json(prompt, "You are a senior marketing strategist analyzing post-mortem data.")
        campaign_lesson = response.get("campaign_lesson", "").strip(' "')
        agent_refinement = response.get("agent_refinement", {})

        # 1. Save campaign lesson as KnowledgeItem for Qdrant indexing
        if campaign_lesson:
            async with async_session() as session:
                ki = KnowledgeItem(
                    id=str(uuid.uuid4()),
                    title=f"Episodic Memory: Goal {goal_id[:8]}",
                    source_type="text",
                    raw_content=campaign_lesson,
                    category="episodic_memory",
                    tags=json.dumps(["auto_generated", "lesson"]),
                    processing_status="processing",
                    uploaded_by=user_id
                )
                session.add(ki)
                await session.commit()
            logger.info(f"[Reflector] Saved campaign lesson to Qdrant queue: {campaign_lesson[:80]}")

        # 2. Update the specific agent's skill markdown file
        if agent_refinement and agent_refinement.get("agent") and agent_refinement.get("lesson"):
            target_agent = agent_refinement["agent"]
            agent_lesson = agent_refinement["lesson"]
            old_rule_hint = agent_refinement.get("old_rule_hint")

            from langclaw_agents.skill_evolver import update_skill_from_lesson, refine_skill_rule

            if old_rule_hint:
                # Surgically refine the rule in the skill file
                await refine_skill_rule(
                    agent_name=target_agent,
                    old_rule_fragment=old_rule_hint,
                    refined_rule=agent_lesson,
                    reason=f"Post-campaign reflection on goal {goal_id[:8]}"
                )
            else:
                # Append the lesson to the skill file's learned lessons section
                await update_skill_from_lesson(
                    agent_name=target_agent,
                    lesson=agent_lesson,
                    campaign_context=f"Goal: {state.get('goal_description', '')[:100]}"
                )

            logger.info(f"[Reflector] Updated {target_agent} skill file with new lesson.")

        await agent_thought_push(
            user_id=user_id,
            agent_name="reflector",
            context="extracted and embedded episodic memory — agents have evolved their skill files for the next campaign",
            goal_id=goal_id
        )

    except Exception as e:
        logger.error(f"[Reflector] Failed to generate episodic memory: {e}")

    # After reflecting, the graph truly ends.
    return {"next_agent": "__end__"}
