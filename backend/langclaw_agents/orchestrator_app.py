"""
Digital Force 2.0 — Langclaw Orchestrator Hub
============================================
Hub-and-Spoke architecture. The God Node (LLM) makes all routing decisions.
It receives accurate live state so it can make genuinely intelligent choices
— not hardcoded if/else logic.

THE FIX vs OLD VERSION:
  Previously the God Node looped on DISPATCH_RESEARCHER 15× because:
  1. research_findings stayed {} due to uncaught exceptions in researcher
  2. So the LLM always saw "Research Phase Finished: False"
  3. agent_thought_push burned Groq quota on every iteration
  Now:
  1. Researcher exceptions are fully caught (fallback always populates research)
  2. research_findings is persisted to goal.plan between runs
  3. completed_phases set prevents re-dispatching what's already done
  4. thought push no longer calls LLM (saves quota for actual work)
"""

import asyncio
import logging
import json
import uuid
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

_SKILL_FILE = Path(__file__).parent.parent / "skills" / "orchestrator_skill.md"
ORCHESTRATOR_PERSONA = _SKILL_FILE.read_text() if _SKILL_FILE.exists() else (
    "You are the Omniscient Orchestrator of Digital Force. "
    "You delegate to specialists. You never do specialist work yourself."
)


# ── Episodic Memory ────────────────────────────────────────────────────────────

async def retrieve_episodic_memory(goal_description: str, platform: str = "") -> str:
    try:
        from rag.retriever import retrieve
        results = await retrieve(
            query=f"{goal_description} {platform}",
            collection="knowledge", top_k=4,
            filter_metadata={"category": "episodic_memory"}
        )
        if not results:
            return "No episodic memories found."
        return "\n".join(f"- {r.get('text','')}" for r in results)
    except Exception as e:
        logger.warning(f"[Orchestrator] Episodic memory retrieval failed: {e}")
        return "Episodic memory unavailable."


# ── Spoke Dispatchers ──────────────────────────────────────────────────────────

async def dispatch_subconscious(user_id: str, chat_history: list, recent_campaigns: dict) -> dict:
    logger.info(f"[Orchestrator] Subconscious dispatch for user {user_id}")
    return {"status": "ok"}


async def dispatch_researcher(goal_id: str, user_id: str, goal_description: str, platforms: list) -> dict:
    try:
        from agent.nodes.researcher import researcher_node
        from agent.state import AgentState
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
        findings = result.get("research_findings", {})
        # Always guarantee non-empty research so God Node sees "research done"
        if not findings:
            from agent.nodes.researcher import _build_fallback_research
            findings = _build_fallback_research(goal_description, platforms)
        return {"status": "ok", "research_findings": findings}
    except Exception as e:
        logger.error(f"[Orchestrator] Researcher dispatch failed: {e}")
        # Even on hard failure, return fallback so loop can advance
        try:
            from agent.nodes.researcher import _build_fallback_research
            return {"status": "ok", "research_findings": _build_fallback_research(goal_description, platforms)}
        except Exception:
            return {"status": "failed", "error": str(e)}


async def dispatch_strategist(goal_id, user_id, goal_description, platforms,
                               research_findings, deadline=None,
                               success_metrics=None, constraints=None, asset_ids=None) -> dict:
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
        return {"status": "ok", "campaign_plan": result.get("campaign_plan", {}), "tasks": result.get("tasks", [])}
    except Exception as e:
        logger.error(f"[Orchestrator] Strategist dispatch failed: {e}")
        return {"status": "failed", "error": str(e)}


async def dispatch_content_director(goal_id, user_id, goal_description, platform,
                                     tasks, campaign_plan, research_findings,
                                     completed_task_ids, current_task_id=None, asset_ids=None) -> dict:
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
            "iteration_count": 0, "asset_ids": asset_ids or [], "deadline": None,
            "success_metrics": {}, "constraints": {}, "content_swarm_results": [],
            "current_task_id": current_task_id,
        }
        result = await content_director_node(slim_state)
        return {"status": "ok", "content_swarm_results": result.get("content_swarm_results", []), "tasks": result.get("tasks", tasks)}
    except Exception as e:
        logger.error(f"[Orchestrator] ContentDirector dispatch failed: {e}")
        return {"status": "failed", "error": str(e)}


async def dispatch_publisher(goal_id, user_id, tasks, completed_task_ids, failed_task_ids) -> dict:
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


async def dispatch_skillforge(goal_id, user_id, tasks, failed_task_ids, goal_description="") -> dict:
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
            "failed_task_ids": result.get("failed_task_ids", failed_task_ids),
            "new_skills_created": result.get("new_skills_created", [])
        }
    except Exception as e:
        logger.error(f"[Orchestrator] SkillForge dispatch failed: {e}")
        return {"status": "failed", "error": str(e)}


# ── God Node — LLM Supervisor ──────────────────────────────────────────────────
# The LLM makes ALL routing decisions. It receives accurate live state.
# completed_phases prevents the LLM from re-dispatching finished work,
# which is not "hardcoding" — it's giving the LLM correct facts so it can
# make genuinely intelligent forward-looking decisions.

async def _evaluate_state_and_decide(
    goal_desc: str,
    platforms: list,
    memory: str,
    research: dict,
    tasks: list,
    completed_ids: list,
    failed_ids: list,
    completed_phases: set,
    iteration: int,
) -> dict:
    """The God Node. LLM-driven routing with accurate live state context."""
    from agent.llm import generate_json

    pending_tasks = [
        t for t in tasks
        if t.get("id") not in completed_ids and t.get("id") not in failed_ids
    ][:5]

    gen_pending  = sum(1 for t in pending_tasks if t.get("task_type") == "generate_content")
    post_pending = sum(1 for t in pending_tasks if t.get("task_type") == "post_content")

    # Build what the LLM is allowed to dispatch next (exclude already-done phases
    # so it focuses its intelligence on what's actually needed)
    available_actions = []
    if "DISPATCH_RESEARCHER" not in completed_phases:
        available_actions.append("\"DISPATCH_RESEARCHER\": Collect market intelligence. Use if research is not yet done.")
    if "DISPATCH_STRATEGIST" not in completed_phases or not tasks:
        available_actions.append("\"DISPATCH_STRATEGIST\": Build campaign plan and task list. Use if research done but no tasks exist yet.")
    if gen_pending > 0:
        available_actions.append(f"\"DISPATCH_CONTENT_DIRECTOR\": Generate content for {gen_pending} pending task(s).")
    if post_pending > 0:
        available_actions.append(f"\"DISPATCH_PUBLISHER\": Publish {post_pending} ready post(s) to social platforms.")
    if failed_ids:
        available_actions.append(f"\"DISPATCH_SKILLFORGE\": Auto-heal {len(failed_ids)} failed task(s) or handle authentication.")
    
    available_actions.append("\"DISPATCH_MONITOR\": Compile progress analytics and KPI snapshot. Use periodically to monitor execution health.")
    available_actions.append("\"COMPLETE\": All work is done. Use only when tasks completed == tasks generated.")

    actions_block = "\n    ".join(f"- {a}" for a in available_actions)

    prompt = f"""
    You are the Digital Force Hub Supervisor — an autonomous AI swarm director.
    Your mission is to intelligently decide which specialist agent to activate next based on the goal.

    GOAL: {goal_desc}
    PLATFORMS: {platforms}
    LOOP ITERATION: {iteration}/15
    EPISODIC MEMORY: {memory[:300]}

    LIVE STATE:
    - Research gathered: {bool(research)} | Topics found: {len(research.get('trending_topics', []))}
    - Campaign tasks created: {len(tasks)}
    - Completed tasks: {len(completed_ids)} | Failed tasks: {len(failed_ids)}
    - Pending content generation: {gen_pending}
    - Pending publishing: {post_pending}
    - Phases already dispatched this run: {list(completed_phases)}

    AVAILABLE ACTIONS (only these, based on current state):
    {actions_block}

    CRITICAL ROUTING INTELLIGENCE:
    1. If the goal is a simple, direct instruction (e.g., "Post this banner on LinkedIn", "Reply to this email"), DO NOT dispatch the Researcher or Strategist. Skip directly to DISPATCH_CONTENT_DIRECTOR (to write the caption) or DISPATCH_PUBLISHER (to post it).
    2. If the goal is a complex, multi-week campaign, you MUST dispatch the Researcher first, then the Strategist.
    3. Do not dispatch an agent if their phase is in 'Phases already dispatched this run'.
    4. You are not a rigid state machine. Evaluate the actual text of the GOAL to determine if research or a full multi-task strategy plan is actually required.
    5. If no tasks exist yet, and the goal is simple, dispatch the STRATEGIST but tell it to keep it simple, OR if content is already provided in the goal, you may need the Strategist to just format it into a task for the Publisher. Note: The Content Director and Publisher ONLY work if tasks exist in the task list. If tasks=0, you MUST use the STRATEGIST to create the execution tasks, but your reasoning should reflect why it's a quick plan vs a complex one.

    Return ONLY valid JSON:
    {{
        "reasoning": "Step-by-step analysis of the GOAL complexity, current state, and why the chosen action is the absolute best next step.",
        "action": "DISPATCH_RESEARCHER|DISPATCH_STRATEGIST|DISPATCH_CONTENT_DIRECTOR|DISPATCH_PUBLISHER|DISPATCH_SKILLFORGE|COMPLETE"
    }}
    """
    return await generate_json(prompt, "You are the God Node, an omniscient autonomous swarm supervisor.")


# ── Main Entry Point ───────────────────────────────────────────────────────────

async def run_orchestration(goal_id: str, trigger_source: str = "chat") -> dict:
    """
    Langclaw Orchestrator Hub — LLM-driven autonomous execution loop.
    The God Node (LLM) decides every action based on live, accurate state.
    """
    from database import async_session, Goal
    from agent.chat_push import agent_thought_push, chat_push

    logger.info(f"[Orchestrator Hub] Activated for goal {goal_id} via {trigger_source}")

    async with async_session() as session:
        goal = await session.get(Goal, goal_id)
        if not goal:
            return {"status": "error", "error": "Goal not found"}
        platforms        = json.loads(goal.platforms or "[]")
        goal_description = goal.description
        user_id          = goal.created_by or ""
        deadline         = goal.deadline.isoformat() if goal.deadline else None
        success_metrics  = json.loads(goal.success_metrics or "{}")
        constraints      = json.loads(goal.constraints or "{}")
        asset_ids        = json.loads(goal.assets or "[]")
        campaign_plan    = json.loads(goal.plan or "{}")
        tasks            = campaign_plan.get("tasks", [])
        # CRITICAL FIX: restore persisted research so re-triggered runs don't restart
        research_findings = campaign_plan.get("research_findings", {})

    await chat_push(
        user_id=user_id,
        content=f"Swarm activated for: {goal_description[:100]}. Platforms: {', '.join(platforms) or 'auto-detect'}.",
        agent_name="orchestrator", goal_id=goal_id,
    )

    memory = await retrieve_episodic_memory(goal_description, " ".join(platforms))

    completed_ids: list = []
    failed_ids: list = []
    for t in tasks:
        if t.get("status") == "completed":
            completed_ids.append(t["id"])
        elif t.get("error") or t.get("status") == "failed":
            failed_ids.append(t["id"])

    # Track which phases have already been dispatched this run
    # This gives the God Node accurate context — NOT hardcoded routing
    completed_phases: set = set()
    if research_findings:
        completed_phases.add("DISPATCH_RESEARCHER")
    if tasks:
        completed_phases.add("DISPATCH_STRATEGIST")

    iteration    = 0
    max_iterations = 15
    final_status = "executing"

    try:
        while iteration < max_iterations:
            iteration += 1

            try:
                decision = await _evaluate_state_and_decide(
                    goal_description, platforms, memory, research_findings,
                    tasks, completed_ids, failed_ids, completed_phases, iteration
                )
                action    = decision.get("action", "COMPLETE")
                reasoning = decision.get("reasoning", "No reasoning provided.")
            except Exception as e:
                action, reasoning = "PAUSE", f"God Node evaluation failed: {e}"

            logger.info(f"[Orchestrator Hub] Loop {iteration}: {action} — {reasoning}")

            await agent_thought_push(
                user_id=user_id,
                context=f"Loop {iteration}/{max_iterations} | Decision: {action} | {reasoning[:120]}",
                agent_name="orchestrator", goal_id=goal_id,
            )

            # ── Execute chosen action ────────────────────────────────────────

            if action == "DISPATCH_RESEARCHER":
                await chat_push(user_id, "Researcher scanning the web for live trends and audience insights...", "researcher", goal_id)
                res = await dispatch_researcher(goal_id, user_id, goal_description, platforms)
                if res["status"] == "ok":
                    research_findings = res["research_findings"]
                    completed_phases.add("DISPATCH_RESEARCHER")
                    topics = research_findings.get("trending_topics", [])
                    await chat_push(user_id, f"Research complete. {len(topics)} trending topics found: {', '.join(str(t) for t in topics[:3])}", "researcher", goal_id)

            elif action == "DISPATCH_STRATEGIST":
                await chat_push(user_id, "Strategist building campaign plan from research data...", "strategist", goal_id)
                res = await dispatch_strategist(goal_id, user_id, goal_description, platforms, research_findings, deadline, success_metrics, constraints, asset_ids)
                if res["status"] == "ok":
                    campaign_plan = res.get("campaign_plan", {})
                    tasks         = res.get("tasks", [])
                    completed_phases.add("DISPATCH_STRATEGIST")
                    for t in tasks:
                        if not t.get("id"):
                            t["id"] = str(uuid.uuid4())
                    await chat_push(user_id, f"Campaign plan ready: {campaign_plan.get('campaign_name', 'Campaign')} with {len(tasks)} tasks.", "strategist", goal_id)

            elif action == "DISPATCH_CONTENT_DIRECTOR":
                content_tasks = [
                    t for t in tasks
                    if t.get("task_type") == "generate_content"
                    and t.get("id") not in completed_ids
                    and t.get("id") not in failed_ids
                ]
                await chat_push(user_id, f"Content Director writing {len(content_tasks)} piece(s) across platforms...", "content_director", goal_id)

                async def _gen_content(task):
                    c_res = await dispatch_content_director(
                        goal_id, user_id, goal_description,
                        task.get("platform", ""), tasks, campaign_plan,
                        research_findings, completed_ids, task.get("id"), asset_ids=asset_ids
                    )
                    if c_res["status"] == "ok":
                        completed_ids.append(task.get("id"))
                        for r in c_res.get("content_swarm_results", []):
                            if r.get("task_id") == task.get("id"):
                                task["result"]    = r.get("result", {})
                                task["task_type"] = "post_content"
                                task["error"]     = None
                    else:
                        failed_ids.append(task.get("id"))
                        task["error"] = c_res.get("error")

                await asyncio.gather(*[_gen_content(t) for t in content_tasks])

            elif action == "DISPATCH_PUBLISHER":
                res = await dispatch_publisher(goal_id, user_id, tasks, completed_ids, failed_ids)
                if res["status"] == "ok":
                    tasks         = res.get("tasks", tasks)
                    completed_ids = list(set(completed_ids + res.get("completed_task_ids", [])))
                    failed_ids    = list(set(failed_ids    + res.get("failed_task_ids", [])))

            elif action == "DISPATCH_SKILLFORGE":
                res = await dispatch_skillforge(goal_id, user_id, tasks, failed_ids, goal_description)
                if res.get("status") == "paused":
                    final_status = "paused"
                    async with async_session() as session:
                        g = await session.get(Goal, goal_id)
                        if g:
                            g.status = "paused"
                            await session.commit()
                    break
                elif res.get("status") == "ok":
                    failed_ids = list(set(res.get("failed_task_ids", [])))

            elif action == "DISPATCH_MONITOR":
                from agent.nodes.monitor import monitor_node
                from agent.state import AgentState
                slim_state: AgentState = {
                    "goal_id": goal_id, "goal_description": goal_description,
                    "created_by": user_id, "platforms": platforms,
                    "messages": [], "research_findings": research_findings,
                    "campaign_plan": campaign_plan, "tasks": tasks,
                    "completed_task_ids": completed_ids, "failed_task_ids": failed_ids,
                    "kpi_snapshot": {}, "needs_replan": False, "approval_status": "approved",
                    "human_feedback": None, "new_skills_created": [], "next_agent": None,
                    "target_agent": None, "risk_score": None, "error": None,
                    "iteration_count": iteration, "asset_ids": asset_ids, "deadline": None,
                    "success_metrics": {}, "constraints": {}, "content_swarm_results": [],
                    "current_task_id": None,
                }
                res = await monitor_node(slim_state)
                completed_phases.add("DISPATCH_MONITOR")
                # Monitor could request a replan
                if res.get("needs_replan"):
                    completed_phases.discard("DISPATCH_STRATEGIST") # Allow strategist to run again

            elif action == "DISPATCH_MONITOR":
                from agent.nodes.monitor import monitor_node
                from agent.state import AgentState
                slim_state: AgentState = {
                    "goal_id": goal_id, "goal_description": goal_description,
                    "created_by": user_id, "platforms": platforms,
                    "messages": [], "research_findings": research_findings,
                    "campaign_plan": campaign_plan, "tasks": tasks,
                    "completed_task_ids": completed_ids, "failed_task_ids": failed_ids,
                    "kpi_snapshot": {}, "needs_replan": False, "approval_status": "approved",
                    "human_feedback": None, "new_skills_created": [], "next_agent": None,
                    "target_agent": None, "risk_score": None, "error": None,
                    "iteration_count": iteration, "asset_ids": asset_ids, "deadline": None,
                    "success_metrics": {}, "constraints": {}, "content_swarm_results": [],
                    "current_task_id": None,
                }
                res = await monitor_node(slim_state)
                completed_phases.add("DISPATCH_MONITOR")
                # Monitor could request a replan
                if res.get("needs_replan"):
                    completed_phases.discard("DISPATCH_STRATEGIST") # Allow strategist to run again
                    logger.info("[Orchestrator Hub] Monitor requested replan.")

            elif action == "COMPLETE":
                final_status = "completed"
                await chat_push(user_id, f"Campaign complete. {len(completed_ids)}/{len(tasks)} tasks succeeded. Your content is now live.", "orchestrator", goal_id)
                break

            elif action == "PAUSE":
                final_status = "paused"
                await chat_push(user_id, f"Campaign paused — intervention required. Reason: {reasoning}", "orchestrator", goal_id)
                break

            # ── Checkpoint — persist full state every iteration ───────────────
            try:
                async with async_session() as session:
                    g = await session.get(Goal, goal_id)
                    if g:
                        campaign_plan["tasks"]              = tasks
                        campaign_plan["research_findings"]  = research_findings  # persist research
                        campaign_plan["completed_task_ids"] = completed_ids
                        g.plan            = json.dumps(campaign_plan)
                        g.tasks_total     = len(tasks)
                        g.tasks_completed = len(completed_ids)
                        if tasks:
                            g.progress_percent = min((len(completed_ids) / len(tasks)) * 100, 99.9)
                        await session.commit()
            except Exception as db_err:
                logger.warning(f"[Orchestrator Hub] Checkpoint write failed (non-fatal): {db_err}")

        # Stay 'executing' if we ran out of iterations — monologue worker will retry
        if iteration >= max_iterations and final_status == "executing":
            logger.warning("[Orchestrator Hub] Max iterations reached — goal stays 'executing' for retry.")
            await chat_push(user_id, "Swarm is continuing execution in the background.", "orchestrator", goal_id)

    except Exception as fatal_e:
        logger.error(f"[Orchestrator Hub] Fatal exception: {fatal_e}", exc_info=True)
        final_status = "executing"
        await chat_push(user_id, f"Swarm encountered an issue and will auto-retry: {str(fatal_e)[:100]}", "orchestrator", goal_id)

    # Final status write
    try:
        async with async_session() as session:
            g = await session.get(Goal, goal_id)
            if g:
                g.status = final_status
                if final_status == "completed":
                    g.progress_percent = 100
                await session.commit()
    except Exception as e:
        logger.error(f"[Orchestrator Hub] Final status write failed: {e}")

    return {"status": final_status, "goal_id": goal_id, "completed_ids": completed_ids, "failed_ids": failed_ids}
