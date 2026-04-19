"""
Digital Force 2.0 — Langclaw Orchestrator Hub
============================================
This replaces the monolithic manager.py. Instead of routing a bloated AgentState
dictionary between every node, the Orchestrator:
  1. Reads goal context from Postgres (by goal_id — no payload bloat).
  2. Retrieves relevant episodic memories from Qdrant before deciding.
  3. Delegates to focused sub-agent functions (The Spokes).
  4. Sub-agents write their outputs directly to Postgres and return a status code.
  5. The Hub never accumulates raw content — only IDs and status flags.

Architecture Rule: PASS IDs, NOT OBJECTS.
"""

import asyncio
import logging
import random
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Load Hub Persona from Markdown Skill File ──────────────────────────────────
_SKILL_FILE = Path(__file__).parent.parent / "skills" / "orchestrator_skill.md"
ORCHESTRATOR_PERSONA = _SKILL_FILE.read_text() if _SKILL_FILE.exists() else (
    "You are the Omniscient Orchestrator of Digital Force. "
    "You delegate to specialists. You never do specialist work yourself."
)


# ── Episodic Memory Retrieval ──────────────────────────────────────────────────

async def retrieve_episodic_memory(goal_description: str, platform: str = "") -> str:
    """
    Query the Qdrant vector DB for past campaign lessons before starting a new goal.
    This gives the Orchestrator 'wisdom' from previous campaigns.
    Returns a formatted string of relevant memories.
    """
    try:
        from rag.retriever import retrieve
        results = await retrieve(
            query=f"{goal_description} {platform}",
            collection="knowledge",
            top_k=4,
            filter_metadata={"category": "episodic_memory"}
        )
        if not results:
            return "No episodic memories found. This may be the first campaign."
        memories = [f"- {r.get('text', '')}" for r in results]
        return "\n".join(memories)
    except Exception as e:
        logger.warning(f"[Orchestrator] Episodic memory retrieval failed: {e}")
        return "Episodic memory unavailable."


# ── Sub-Agent Spoke Dispatchers ────────────────────────────────────────────────
# Each function is a clean, isolated call to a spoke agent.
# It receives only the goal_id, reads from DB internally, and returns a status.

async def dispatch_researcher(goal_id: str, user_id: str, goal_description: str, platforms: list) -> dict:
    """Kick off the researcher spoke. It reads its own context from DB."""
    try:
        from agent.nodes.researcher import researcher_node
        from agent.state import AgentState
        # Build a minimal state — researcher only needs description + platforms
        slim_state: AgentState = {
            "goal_id": goal_id, "goal_description": goal_description,
            "created_by": user_id, "platforms": platforms,
            "messages": [], "research_findings": {}, "campaign_plan": {},
            "tasks": [], "completed_task_ids": [], "failed_task_ids": [],
            "kpi_snapshot": {}, "needs_replan": False, "approval_status": "pending",
            "human_feedback": None, "new_skills_created": [], "next_agent": None,
            "target_agent": None, "risk_score": None, "error": None,
            "iteration_count": 0, "asset_ids": [], "deadline": None,
            "success_metrics": {}, "constraints": {}, "content_swarm_results": [],
            "current_task_id": None,
        }
        result = await researcher_node(slim_state)
        return {"status": "ok", "research_findings": result.get("research_findings", {})}
    except Exception as e:
        logger.error(f"[Orchestrator] Researcher dispatch failed: {e}")
        return {"status": "failed", "error": str(e)}


async def dispatch_strategist(goal_id: str, user_id: str, goal_description: str,
                               platforms: list, research_findings: dict,
                               deadline: Optional[str] = None,
                               success_metrics: dict = None,
                               constraints: dict = None,
                               asset_ids: list = None) -> dict:
    """Kick off the strategist spoke."""
    try:
        from agent.nodes.strategist import strategist_node
        from agent.state import AgentState
        slim_state: AgentState = {
            "goal_id": goal_id, "goal_description": goal_description,
            "created_by": user_id, "platforms": platforms,
            "messages": [], "research_findings": research_findings,
            "campaign_plan": {}, "tasks": [],
            "completed_task_ids": [], "failed_task_ids": [],
            "kpi_snapshot": {}, "needs_replan": False, "approval_status": "pending",
            "human_feedback": None, "new_skills_created": [], "next_agent": None,
            "target_agent": None, "risk_score": None, "error": None,
            "iteration_count": 0, "asset_ids": asset_ids or [],
            "deadline": deadline, "success_metrics": success_metrics or {},
            "constraints": constraints or {}, "content_swarm_results": [],
            "current_task_id": None,
        }
        result = await strategist_node(slim_state)
        return {
            "status": "ok",
            "campaign_plan": result.get("campaign_plan", {}),
            "tasks": result.get("tasks", [])
        }
    except Exception as e:
        logger.error(f"[Orchestrator] Strategist dispatch failed: {e}")
        return {"status": "failed", "error": str(e)}


async def dispatch_content_director(goal_id: str, user_id: str, goal_description: str,
                                     platform: str, tasks: list,
                                     campaign_plan: dict,
                                     research_findings: dict,
                                     completed_task_ids: list,
                                     current_task_id: Optional[str] = None) -> dict:
    """Kick off the content director spoke for a single platform task."""
    try:
        from agent.nodes.content_director import content_director_node
        from agent.state import AgentState
        slim_state: AgentState = {
            "goal_id": goal_id, "goal_description": goal_description,
            "created_by": user_id, "platforms": [platform],
            "messages": [], "research_findings": research_findings,
            "campaign_plan": campaign_plan, "tasks": tasks,
            "completed_task_ids": completed_task_ids, "failed_task_ids": [],
            "kpi_snapshot": {}, "needs_replan": False, "approval_status": "approved",
            "human_feedback": None, "new_skills_created": [], "next_agent": None,
            "target_agent": None, "risk_score": None, "error": None,
            "iteration_count": 0, "asset_ids": [], "deadline": None,
            "success_metrics": {}, "constraints": {}, "content_swarm_results": [],
            "current_task_id": current_task_id,
        }
        result = await content_director_node(slim_state)
        return {
            "status": "ok",
            "content_swarm_results": result.get("content_swarm_results", []),
            "tasks": result.get("tasks", tasks)
        }
    except Exception as e:
        logger.error(f"[Orchestrator] ContentDirector dispatch failed: {e}")
        return {"status": "failed", "error": str(e)}


# ── Main Orchestrator Entry Point ──────────────────────────────────────────────

async def run_orchestration(goal_id: str, trigger_source: str = "chat") -> dict:
    """
    Main entry point for the Langclaw Orchestrator Hub.
    Reads goal from DB by ID. Dispatches spokes. Returns final status.
    """
    from database import async_session, Goal, AgentTask
    from sqlalchemy import select
    import json

    logger.info(f"[Orchestrator] Hub activated for goal {goal_id} via {trigger_source}")

    # ── Read goal from DB (not from a bloated state dict) ─────────────────────
    async with async_session() as session:
        goal = await session.get(Goal, goal_id)
        if not goal:
            logger.error(f"[Orchestrator] Goal {goal_id} not found in database.")
            return {"status": "error", "error": "Goal not found"}

        platforms = json.loads(goal.platforms or "[]")
        goal_description = goal.description
        user_id = goal.created_by or ""
        deadline = goal.deadline.isoformat() if goal.deadline else None
        success_metrics = json.loads(goal.success_metrics or "{}")
        constraints = json.loads(goal.constraints or "{}")
        asset_ids = json.loads(goal.assets or "[]")

    # ── Step 1: Retrieve Episodic Memory ──────────────────────────────────────
    memory = await retrieve_episodic_memory(goal_description, " ".join(platforms))
    logger.info(f"[Orchestrator] Episodic memory loaded: {memory[:100]}...")

    # ── Step 2: Research Phase ─────────────────────────────────────────────────
    research_result = await dispatch_researcher(goal_id, user_id, goal_description, platforms)
    research_findings = research_result.get("research_findings", {})

    # ── Step 3: Strategy Phase ──────────────────────────────────────────────
    strategy_result = await dispatch_strategist(
        goal_id, user_id, goal_description, platforms, research_findings,
        deadline, success_metrics, constraints, asset_ids
    )
    if strategy_result["status"] == "failed":
        return {"status": "error", "error": strategy_result.get("error")}

    campaign_plan = strategy_result.get("campaign_plan", {})
    tasks = strategy_result.get("tasks", [])

    # Assign IDs to any tasks missing them
    import uuid as _uuid
    for t in tasks:
        if not t.get("id"):
            t["id"] = str(_uuid.uuid4())
    campaign_plan["tasks"] = tasks

    # Persist plan + tasks to Postgres immediately
    async with async_session() as session:
        goal_row = await session.get(Goal, goal_id)
        if goal_row:
            goal_row.plan = json.dumps(campaign_plan)
            goal_row.tasks_total = len(tasks)
            await session.commit()
            logger.info(f"[Orchestrator] Persisted plan with {len(tasks)} tasks for goal {goal_id}")

    # ── Step 4: Content Generation (Parallel per platform) ────────────────────
    content_tasks = [t for t in tasks if t.get("task_type") == "generate_content"]
    completed_ids: list = []

    async def _gen_content(task):
        result = await dispatch_content_director(
            goal_id=goal_id, user_id=user_id, goal_description=goal_description,
            platform=task.get("platform", "linkedin"), tasks=tasks,
            campaign_plan=campaign_plan, research_findings=research_findings,
            completed_task_ids=completed_ids, current_task_id=task.get("id")
        )
        if result["status"] == "ok":
            completed_ids.append(task.get("id"))
            # Merge generated content back into the task dict for persistence
            for r in result.get("content_swarm_results", []):
                if r.get("task_id") == task.get("id"):
                    task["result"] = r.get("result", {})
                    task["task_type"] = "post_content"  # Ready for publisher
        return result

    content_results = await asyncio.gather(*[_gen_content(t) for t in content_tasks])
    logger.info(f"[Orchestrator] Content generation complete: {len(content_results)} results")

    # Persist updated tasks with content back to Postgres
    campaign_plan["tasks"] = tasks
    async with async_session() as session:
        goal_row = await session.get(Goal, goal_id)
        if goal_row:
            goal_row.plan = json.dumps(campaign_plan)
            goal_row.tasks_completed = len(completed_ids)
            if len(tasks) > 0:
                goal_row.progress_percent = (len(completed_ids) / len(tasks)) * 100
            await session.commit()
            logger.info(f"[Orchestrator] Persisted {len(completed_ids)} content results for goal {goal_id}")

    return {
        "status": "ok",
        "goal_id": goal_id,
        "tasks_generated": len(tasks),
        "content_generated": len(content_results),
        "completed_ids": completed_ids,
    }
