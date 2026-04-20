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


async def dispatch_publisher(goal_id: str, user_id: str, tasks: list, completed_task_ids: list, failed_task_ids: list) -> dict:
    """Kick off the publisher spoke to blast content to social graphs."""
    try:
        from agent.nodes.publisher import publisher_node
        from agent.state import AgentState
        slim_state: AgentState = {
            "goal_id": goal_id, "goal_description": "",
            "created_by": user_id, "platforms": [],
            "messages": [], "research_findings": {},
            "campaign_plan": {}, "tasks": tasks,
            "completed_task_ids": completed_task_ids, "failed_task_ids": failed_task_ids,
            "kpi_snapshot": {}, "needs_replan": False, "approval_status": "approved",
            "human_feedback": None, "new_skills_created": [], "next_agent": None,
            "target_agent": None, "risk_score": None, "error": None,
            "iteration_count": 0, "asset_ids": [], "deadline": None,
            "success_metrics": {}, "constraints": {}, "content_swarm_results": [],
            "current_task_id": None,
        }
        result = await publisher_node(slim_state)
        return {
            "status": "ok",
            "completed_task_ids": result.get("completed_task_ids", []),
            "failed_task_ids": result.get("failed_task_ids", []),
            "tasks": result.get("tasks", tasks)
        }
    except Exception as e:
        logger.error(f"[Orchestrator] Publisher dispatch failed: {e}")
        return {"status": "failed", "error": str(e)}


async def dispatch_skillforge(goal_id: str, user_id: str, tasks: list, failed_task_ids: list, goal_description: str = "") -> dict:
    """Kick off the Auto-Healer spoke to build fallbacks for failed tasks."""
    try:
        from agent.nodes.skillforge import skillforge_node
        from agent.state import AgentState
        slim_state: AgentState = {
            "goal_id": goal_id, "goal_description": goal_description,
            "created_by": user_id, "platforms": [],
            "messages": [], "research_findings": {},
            "campaign_plan": {}, "tasks": tasks,
            "completed_task_ids": [], "failed_task_ids": failed_task_ids,
            "kpi_snapshot": {}, "needs_replan": False, "approval_status": "approved",
            "human_feedback": None, "new_skills_created": [], "next_agent": None,
            "target_agent": None, "risk_score": None, "error": None,
            "iteration_count": 0, "asset_ids": [], "deadline": None,
            "success_metrics": {}, "constraints": {}, "content_swarm_results": [],
            "current_task_id": None,
        }
        result = await skillforge_node(slim_state)
        return {
            "status": "ok",
            "failed_task_ids": result.get("failed_task_ids", failed_task_ids), # Return updated unresolved failures
            "new_skills_created": result.get("new_skills_created", [])
        }
    except Exception as e:
        logger.error(f"[Orchestrator] SkillForge dispatch failed: {e}")
        return {"status": "failed", "error": str(e)}


async def _evaluate_state_and_decide(goal_desc: str, platforms: list, memory: str, research: dict, tasks: list, completed_ids: list, failed_ids: list, iteration: int) -> dict:
    """The Global Supervisor ('God Node') ReAct prompt loop."""
    from agent.llm import generate_json
    # Filter only uncompleted tasks for context window sanity
    pending_tasks = [t for t in tasks if t.get("id") not in completed_ids and t.get("id") not in failed_ids][:5]
    
    prompt = f"""
    You are the Digital Force Hub Supervisor. You execute an autonomous multi-agent swarm.
    Your mission: evaluate the current execution state and dispatch exactly ONE spoke agent.

    Goal: {goal_desc}
    Platforms: {platforms}
    Hub Loop Iteration: {iteration}/15
    
    CURRENT STATE TRACKERS:
    - Research Phase Finished: {bool(research)}
    - Tasks Generated: {len(tasks)}
    - Tasks Completed Successfully: {len(completed_ids)}
    - Tasks Failed Critically: {len(failed_ids)} (Failed Task IDs: {failed_ids})

    Pending Tasks Snippet ({len(pending_tasks)} shown):
    {pending_tasks}
    
    AVAILABLE SPOKE AGENTS (Choose exactly one):
    - "DISPATCH_RESEARCHER": Collects context. Use if Research Phase is False and goal requires strategy.
    - "DISPATCH_STRATEGIST": Creates the campaign tasks. Use if Research is True but Tasks Generated is 0.
    - "DISPATCH_CONTENT_DIRECTOR": Generates content payloads. Use if there are pending tasks with task_type="generate_content".
    - "DISPATCH_PUBLISHER": Publishes content. Use if there are pending tasks with task_type="post_content".
    - "DISPATCH_SKILLFORGE": The Auto-Healer & Authenticator. Use if there are Tasks Failed Critically. ALSO USE IMMEDIATELY if the goal is "SYSTEM_AUTH_PROVISION" to orchestrate headless login scripts.
    - "COMPLETE": Use if Tasks Completed == Tasks Generated, OR if there is absolutely no path forward.
    
    Return JSON only:
    {{
        "reasoning": "Step-by-step logic explaining the state, what is missing, and what Spoke must be injected into the Execution Runtime next to achieve the user's ultimate goal.",
        "action": "DISPATCH_RESEARCHER" | "DISPATCH_STRATEGIST" | "DISPATCH_CONTENT_DIRECTOR" | "DISPATCH_PUBLISHER" | "DISPATCH_SKILLFORGE" | "COMPLETE"
    }}
    """
    return await generate_json(prompt, "You are the God Node, an omniscient supervisor overseeing autonomous execution.")



# ── Main Orchestrator Entry Point ──────────────────────────────────────────────

async def run_orchestration(goal_id: str, trigger_source: str = "chat") -> dict:
    """
    Main entry point for the Langclaw Orchestrator Hub.
    Executes a dynamic ReAct (Reasoning and Acting) LLM loop to evaluate
    and dynamically route goal progression until fully complete or fatally stalled.
    """
    from database import async_session, Goal
    from agent.chat_push import agent_thought_push, chat_push
    import json
    import uuid

    logger.info(f"[Orchestrator Hub] ReAct Loop activated for goal {goal_id} via {trigger_source}")

    # 1. Load context
    async with async_session() as session:
        goal = await session.get(Goal, goal_id)
        if not goal:
            return {"status": "error", "error": "Goal not found"}
        
        platforms = json.loads(goal.platforms or "[]")
        goal_description = goal.description
        user_id = goal.created_by or ""
        deadline = goal.deadline.isoformat() if goal.deadline else None
        success_metrics = json.loads(goal.success_metrics or "{}")
        constraints = json.loads(goal.constraints or "{}")
        asset_ids = json.loads(goal.assets or "[]")
        
        campaign_plan = json.loads(goal.plan or "{}")
        tasks = campaign_plan.get("tasks", []) 

    memory = await retrieve_episodic_memory(goal_description, " ".join(platforms))
    research_findings = {} 
    
    completed_ids = []
    failed_ids = [] 
    for t in tasks:
        if t.get("status") == "completed":
             completed_ids.append(t["id"])
        elif t.get("error"):
             failed_ids.append(t["id"])

    iteration = 0
    max_iterations = 15
    final_status = "error"

    try:
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"[Orchestrator Hub] Loop {iteration}: God Node evaluating state...")
            
            try:
                decision = await _evaluate_state_and_decide(
                    goal_description, platforms, memory, research_findings, 
                    tasks, completed_ids, failed_ids, iteration
                )
                action = decision.get("action", "COMPLETE")
                reasoning = decision.get("reasoning", "No reasoning provided.")
            except Exception as e:
                action, reasoning = "PAUSE", f"God Node evaluation failed: {e}"
                
            logger.info(f"[Orchestrator Hub] Command => {action} (Reason: {reasoning})")
            
            # Announce the dynamic decision
            await agent_thought_push(
                user_id=user_id, 
                context=f"Hub Supervisor executed Cognitive Loop {iteration} | Reasoning: {reasoning} | Invoking Component: {action}", 
                agent_name="orchestrator", 
                goal_id=goal_id
            )

            if action == "DISPATCH_RESEARCHER":
                res = await dispatch_researcher(goal_id, user_id, goal_description, platforms)
                if res["status"] == "ok":
                    research_findings = res["research_findings"]

            elif action == "DISPATCH_STRATEGIST":
                res = await dispatch_strategist(goal_id, user_id, goal_description, platforms, research_findings, deadline, success_metrics, constraints, asset_ids)
                if res["status"] == "ok":
                    campaign_plan = res.get("campaign_plan", {})
                    tasks = res.get("tasks", [])
                    for t in tasks:
                        if not t.get("id"):
                            t["id"] = str(uuid.uuid4())

            elif action == "DISPATCH_CONTENT_DIRECTOR":
                content_tasks = [t for t in tasks if t.get("task_type") == "generate_content" and t.get("id") not in completed_ids and t.get("id") not in failed_ids]
                
                async def _gen_content(task):
                    c_res = await dispatch_content_director(goal_id, user_id, goal_description, task.get("platform", ""), tasks, campaign_plan, research_findings, completed_ids, task.get("id"))
                    if c_res["status"] == "ok":
                        completed_ids.append(task.get("id"))
                        for r in c_res.get("content_swarm_results", []):
                            if r.get("task_id") == task.get("id"):
                                task["result"] = r.get("result", {})
                                task["task_type"] = "post_content" 
                                task["error"] = None # Clear old errors
                    else:
                        failed_ids.append(task.get("id"))
                        task["error"] = c_res.get("error")

                await asyncio.gather(*[_gen_content(t) for t in content_tasks])

            elif action == "DISPATCH_PUBLISHER":
                res = await dispatch_publisher(goal_id, user_id, tasks, completed_ids, failed_ids)
                if res["status"] == "ok":
                    tasks = res.get("tasks", tasks)
                    new_completed = res.get("completed_task_ids", [])
                    new_failed = res.get("failed_task_ids", [])
                    completed_ids = list(set(completed_ids + new_completed))
                    failed_ids = list(set(failed_ids + new_failed))

            elif action == "DISPATCH_SKILLFORGE":
                res = await dispatch_skillforge(goal_id, user_id, tasks, failed_ids, goal_description)
                if res.get("status") == "paused":
                    # SkillForge requested a human (e.g. captcha/QR via chat)
                    final_status = "paused"
                    async with async_session() as session:
                        g = await session.get(Goal, goal_id)
                        if g:
                            g.status = final_status
                            await session.commit()
                    break
                elif res.get("status") == "ok":
                    failed_ids = list(set(res.get("failed_task_ids", [])))

            elif action == "COMPLETE":
                final_status = "completed"
                break
                
            elif action == "PAUSE":
                final_status = "paused"
                await chat_push(user_id, f"⚠️ Campaign Hub paused execution. Goal requires intervention.\nReason: {reasoning}", "orchestrator", goal_id)
                break
                
            else:
                logger.warning(f"[Orchestrator Hub] God Node hallucinated action {action}! Breaking loop.")
                final_status = "completed_with_errors"
                break

            # Postgres Checkpoint: Save strict state boundaries safely every loop iteration
            async with async_session() as session:
                g = await session.get(Goal, goal_id)
                if g:
                    campaign_plan["tasks"] = tasks
                    g.plan = json.dumps(campaign_plan)
                    g.tasks_total = len(tasks)
                    g.tasks_completed = len(completed_ids)
                    if len(tasks) > 0:
                        prog = (len(completed_ids) / len(tasks)) * 100
                        g.progress_percent = min(prog, 99.9)  # Keep under 100 until fully COMPLETE status
                    await session.commit()

        if iteration >= max_iterations:
             logger.warning("[Orchestrator Hub] Hit max loop iterations! Forcing pause.")
             final_status = "completed_with_errors"

    except Exception as fatal_e:
        logger.error(f"[Orchestrator Hub] Fatal Orchestration Loop exception: {fatal_e}", exc_info=True)
        final_status = "failed"
        await chat_push(user_id, f"🚨 Critical Swarm Failure. The Orchestrator loop crashed: {str(fatal_e)}", "orchestrator", goal_id)

    # FINAL State Write (Closes the "Perma-Executing" Deadlock)
    async with async_session() as session:
        g = await session.get(Goal, goal_id)
        if g:
            g.status = final_status
            if final_status == "completed":
                g.progress_percent = 100
            await session.commit()
            logger.info(f"[Orchestrator Hub] Execution Loop Terminated. Final Status: {final_status}")

    return {
        "status": final_status,
        "goal_id": goal_id,
        "completed_ids": completed_ids,
        "failed_ids": failed_ids
    }
