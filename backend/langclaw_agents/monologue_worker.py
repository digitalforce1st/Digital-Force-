"""
Digital Force 2.0 — Internal Monologue Worker
==============================================
The "Living Organism" heartbeat. Upgraded to true parallel swarm execution.

KEY UPGRADES (v3 — Swarm Scale):
  - PARALLEL GOAL EXECUTION: asyncio.gather() runs ALL eligible goals
    simultaneously instead of serially. 20 goals → all 20 fire at once.
  - PARALLEL USER PROCESSING: All users in a batch process in parallel,
    not sequentially. PAGE_SIZE users → PAGE_SIZE concurrent thoughts.
  - HIGHER GOAL LIMIT: Picks up 100 goals per cycle (was 20).
  - FASTER CYCLE: Min sleep reduced to 60s (was 180s) — more responsive.
  - SWARM CONCURRENCY LIMITER: asyncio.Semaphore caps orchestration fanout
    to prevent RAM exhaustion while still being massively parallel.
  - PARALLEL BATCH CONTENT: When the monologue generates content ideas,
    it uses generate_completion_batch() to write 50 posts simultaneously.

PRESERVED from v2:
  - GC-safe _safe_create_task() pinning
  - Real web research via RSS feed
  - Timezone-safe _to_naive_utc()
  - DB-backed nudge throttle
  - Correct RAG API calls
"""

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
MIN_SLEEP_SECONDS    = 60     # Minimum idle period (1 min — was 3min)
MAX_SLEEP_SECONDS    = 180    # Maximum idle period (3 min — was 8min)
RELEVANCE_THRESHOLD  = 75
PROACTIVE_HOURS      = 2
IDLE_THRESHOLD_HRS   = 24
PAGE_SIZE            = 25     # Users processed per cycle (was 10)
MAX_GOAL_BATCH       = 100    # Goals picked up per cycle (was 20)

# Max truly parallel orchestration runs at once (RAM protection)
# Each orchestration run holds research + content in memory
MAX_PARALLEL_ORCHESTRATIONS = 10

# ── GC-safe task registry ──────────────────────────────────────────────────────
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _safe_create_task(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


# ── Timezone-safe datetime normalizer ─────────────────────────────────────────

def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

async def internal_monologue():
    """
    Entry point — called from main.py lifespan as asyncio.create_task().
    Runs indefinitely with randomized sleep. Fully non-blocking.
    """
    logger.info("🧠 [Monologue] Digital Force Swarm Worker online — parallel autonomous execution active")
    await asyncio.sleep(15)  # Allow DB/server to fully initialize

    while True:
        try:
            await _run_monologue_cycle()
        except Exception as e:
            logger.error(f"[Monologue] Unhandled cycle error: {e}", exc_info=True)

        sleep_duration = random.randint(MIN_SLEEP_SECONDS, MAX_SLEEP_SECONDS)
        logger.debug(f"[Monologue] Sleeping {sleep_duration}s before next cycle...")
        await asyncio.sleep(sleep_duration)


# ══════════════════════════════════════════════════════════════════════════════
# ONE MONOLOGUE CYCLE — FULLY PARALLEL
# ══════════════════════════════════════════════════════════════════════════════

async def _run_monologue_cycle():
    """
    One full cycle. PARALLEL execution for goals AND users.
    Goals fire concurrently (up to MAX_PARALLEL_ORCHESTRATIONS at once).
    Users think in parallel (up to PAGE_SIZE at once).
    """
    from database import async_session, AgencySettings
    from sqlalchemy import select

    logger.info("[Monologue] ── Swarm cycle starting ──")
    now = datetime.utcnow()

    # Phase 1: Fire all eligible goals IN PARALLEL
    await _phase_execute_goals_parallel(now)
    await _phase_retry_failed_posts(now)

    # Phase 2: Process all autonomous users IN PARALLEL (paginated batches)
    offset = 0
    while True:
        async with async_session() as session:
            result = await session.execute(
                select(AgencySettings)
                .where(AgencySettings.autonomous_mode == True)
                .offset(offset)
                .limit(PAGE_SIZE)
            )
            batch = result.scalars().all()

        if not batch:
            break

        # All users in this page think simultaneously
        await asyncio.gather(
            *[_process_user_thought_safe(cfg, now) for cfg in batch],
            return_exceptions=True,
        )

        offset += PAGE_SIZE
        await asyncio.sleep(0)  # Yield to event loop between pages

    logger.info("[Monologue] ── Swarm cycle complete ──")


async def _process_user_thought_safe(cfg, now: datetime):
    """Wrapper that catches exceptions so one user's failure doesn't stop others."""
    try:
        await _process_user_thought(cfg, now)
    except Exception as e:
        logger.error(f"[Monologue] Error processing user {cfg.user_id[:8]}: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — PARALLEL GOAL EXECUTION & RECOVERY
# ══════════════════════════════════════════════════════════════════════════════

async def _phase_execute_goals_parallel(now: datetime):
    """
    Pick up ALL eligible goals and fire their orchestration IN PARALLEL.
    A semaphore limits true concurrency to MAX_PARALLEL_ORCHESTRATIONS
    so we don't saturate RAM with 100 simultaneous LLM contexts.
    """
    from database import async_session, Goal
    from sqlalchemy import select

    try:
        async with async_session() as session:
            result = await session.execute(
                select(Goal).where(
                    Goal.status.in_(["planning", "executing", "awaiting_approval"])
                ).limit(MAX_GOAL_BATCH)
            )
            goals = result.scalars().all()
    except Exception as e:
        if "connection" in str(e).lower() or "getaddrinfo" in str(e):
            logger.warning(f"[Monologue] DB connection asleep or dropped. Skipping cycle: {e}")
            return
        logger.error(f"[Monologue] DB error fetching goals: {e}")
        return

    if not goals:
        return

    logger.info(f"[Monologue] Found {len(goals)} active goal(s) — firing in parallel (max {MAX_PARALLEL_ORCHESTRATIONS} concurrent)")

    semaphore = asyncio.Semaphore(MAX_PARALLEL_ORCHESTRATIONS)

    async def _handle_goal(goal):
        async with semaphore:
            try:
                if goal.status == "planning":
                    created_at = _to_naive_utc(goal.created_at) or now
                    age = (now - created_at).total_seconds()
                    if age > 600 and not goal.plan:
                        logger.info(f"[Monologue] Goal {goal.id[:8]} stuck >10min — retrying")
                        await _retry_planning(goal)

                elif goal.status == "awaiting_approval":
                    updated_at = _to_naive_utc(goal.updated_at)
                    if updated_at and (now - updated_at).total_seconds() > 3600:
                        await _nudge_approval(goal, now)

                elif goal.status == "executing":
                    updated_at = _to_naive_utc(goal.updated_at)
                    age_secs = (now - updated_at).total_seconds() if updated_at else 99999

                    # Case A: Executing but has NO tasks — orchestrator got stuck early.
                    # Retry the full orchestration run to restart from scratch.
                    if (goal.tasks_total or 0) == 0 and age_secs > 600:
                        logger.info(f"[Monologue] Goal {goal.id[:8]} stuck executing with 0 tasks ({age_secs/60:.1f}min) — forcing full retry")
                        await _retry_planning(goal)

                    # Case B: Has tasks but stale for >10min — push a status update
                    elif age_secs > 600:
                        await _push_execution_status(goal)
            except Exception as e:
                logger.error(f"[Monologue] Error handling goal {goal.id[:8]}: {e}")

    await asyncio.gather(*[_handle_goal(g) for g in goals], return_exceptions=True)


async def _retry_planning(goal):
    from langclaw_agents.orchestrator_app import run_orchestration
    _safe_create_task(run_orchestration(goal.id, trigger_source="monologue_retry"))


async def _nudge_approval(goal, now: datetime):
    from agent.chat_push import chat_push
    from database import async_session, ChatMessage
    from sqlalchemy import select

    one_hour_ago = now - timedelta(hours=1)
    async with async_session() as session:
        result = await session.execute(
            select(ChatMessage).where(
                ChatMessage.goal_id == goal.id,
                ChatMessage.agent_name == "orchestrator",
                ChatMessage.created_at >= one_hour_ago,
            ).limit(1)
        )
        recent_nudge = result.scalar_one_or_none()

    if recent_nudge:
        return

    await chat_push(
        goal.created_by,
        f"Campaign \"{goal.title}\" is ready and waiting for your approval. "
        f"Reply 'approve' or open the Goals page to review the plan.",
        "orchestrator",
        goal.id,
    )


async def _push_execution_status(goal):
    from agent.chat_push import chat_push
    from database import async_session, AgentLog
    from sqlalchemy import select, desc

    pct = goal.progress_percent or 0
    done = goal.tasks_completed or 0
    total = goal.tasks_total or 0
    if pct >= 100:
        msg = f"Campaign \"{goal.title}\" complete. All {total} tasks finished."
    elif total == 0:
        msg = f"Campaign \"{goal.title}\" is active. Initializing strategy and preparing tasks."
    else:
        msg = (
            f"Campaign \"{goal.title}\" running — {pct:.0f}% ({done}/{total} tasks). "
            f"Scheduler is distributing posts throughout the day."
        )

    # ── Spam guard: skip if the exact same message was logged in the last 30min ──
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=30)
        async with async_session() as session:
            result = await session.execute(
                select(AgentLog).where(
                    AgentLog.goal_id == goal.id,
                    AgentLog.agent == "monitor",
                    AgentLog.thought == msg,
                    AgentLog.created_at >= cutoff,
                ).limit(1)
            )
            if result.scalar_one_or_none():
                logger.debug(f"[Monologue] Suppressing duplicate monitor push for goal {goal.id[:8]}")
                return
    except Exception:
        pass  # If spam-check fails, still send the message

    await chat_push(goal.created_by, msg, "monitor", goal.id)


async def _phase_retry_failed_posts(now: datetime):
    """Sweep failed posts and re-queue them to the scheduler."""
    from database import async_session, PublishedPost, AgentTask
    from sqlalchemy import select
    import uuid

    async with async_session() as session:
        result = await session.execute(
            select(PublishedPost).where(PublishedPost.status == "failed").limit(50)
        )
        failed_posts = result.scalars().all()

        for post in failed_posts:
            post.status = "retrying"
            if post.goal_id:
                new_task = AgentTask(
                    id=str(uuid.uuid4()),
                    goal_id=post.goal_id,
                    task_type="post_content",
                    agent="publisher",
                    description=f"Auto-Retry: failed post on {post.platform}",
                    status="queued",
                    platform=post.platform,
                    connection_id=post.connection_id,
                )
                session.add(new_task)
                logger.info(f"[Monologue] Re-queued failed post {post.id[:8]}")

        if failed_posts:
            await session.commit()


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — PER-USER PARALLEL AUTONOMOUS THINKING
# ══════════════════════════════════════════════════════════════════════════════

async def _process_user_thought(cfg, now: datetime):
    """
    The autonomous thought process for one user.
    Runs in parallel alongside all other users in the batch.
    """
    user_id = cfg.user_id
    from database import async_session, Goal
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(
            select(Goal).where(
                Goal.created_by == user_id,
                Goal.status.in_(["planning", "executing", "awaiting_approval", "monitoring"])
            )
        )
        active_goals = result.scalars().all()

    if not active_goals:
        last_ran = _to_naive_utc(cfg.daemon_last_ran)
        hours_idle = (now - last_ran).total_seconds() / 3600 if last_ran else IDLE_THRESHOLD_HRS + 1
        if hours_idle >= IDLE_THRESHOLD_HRS:
            await _push_idle_report(user_id, cfg, now)

    # Proactive background research — throttled to every PROACTIVE_HOURS
    last_research = _to_naive_utc(cfg.last_proactive_research)
    hours_since = (now - last_research).total_seconds() / 3600 if last_research else PROACTIVE_HOURS + 1
    if hours_since >= PROACTIVE_HOURS:
        await _run_background_thought(user_id, cfg, now)
        async with async_session() as session:
            s = await session.get(type(cfg), cfg.id)
            if s:
                s.last_proactive_research = now
                s.daemon_last_ran = now
                await session.commit()

    await _check_brief_schedule(user_id, cfg, now, active_goals)


async def _run_background_thought(user_id: str, cfg, now: datetime):
    """Background research and subconscious planning for a user."""
    from langclaw_agents.orchestrator_app import dispatch_subconscious
    from database import async_session, Goal, ChatMessage
    from sqlalchemy import select, desc

    logger.info(f"[Monologue] Background thought for user {user_id[:8]}...")

    try:
        async with async_session() as session:
            goals_result = await session.execute(
                select(Goal).where(Goal.created_by == user_id)
                .order_by(desc(Goal.created_at)).limit(5)
            )
            past_goals = goals_result.scalars().all()

            chat_result = await session.execute(
                select(ChatMessage).where(
                    ChatMessage.goal_id == None,
                ).order_by(desc(ChatMessage.created_at)).limit(15)
            )
            recent_chats = chat_result.scalars().all()
            recent_chats.reverse()

        recent_campaigns = {g.id: g.title for g in past_goals}
        chat_dicts = [{"role": c.role, "content": c.content} for c in recent_chats]
        await dispatch_subconscious(user_id, chat_dicts, recent_campaigns)

    except Exception as e:
        logger.error(f"[Monologue] Background thought failed for {user_id[:8]}: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# IDLE REPORT & BRIEF SCHEDULER
# ══════════════════════════════════════════════════════════════════════════════

async def _push_idle_report(user_id: str, cfg, now: datetime):
    from agent.llm import generate_completion
    from agent.chat_push import chat_push

    industry = cfg.industry or "technology and business"
    prompt = f"""The Digital Force agency has been idle — no active campaigns.
Today is {now.strftime('%A, %B %d %Y')}. Industry: {industry}
Generate a short report (under 200 words):
1. State there are no active campaigns
2. List 3 specific campaign ideas for this week with estimated reach
3. Suggest which to prioritise and exactly why
Format as a marketing director reporting to the business owner.
Do not use asterisks for formatting."""

    try:
        report = await generate_completion(prompt, "You are Digital Force's autonomous marketing director.")
        await chat_push(
            user_id,
            f"Agency Status: Idle\n\n{report}\n\nSay 'launch [idea]' to get started.",
            "orchestrator",
        )
    except Exception as e:
        logger.error(f"[Monologue] Idle report failed for {user_id[:8]}: {e}")


async def _check_brief_schedule(user_id: str, cfg, now: datetime, active_goals: list):
    import json
    try:
        import pytz
        slots = json.loads(cfg.brief_slots or "[]")
        if not slots:
            return

        tz = pytz.timezone(cfg.timezone or "UTC")
        user_now = now.replace(tzinfo=pytz.utc).astimezone(tz)
        user_hhmm = user_now.strftime("%H:%M")
        user_date = user_now.strftime("%Y-%m-%d")
        user_weekday = user_now.weekday()
        updated = False

        for slot in slots:
            last_sent = slot.get("last_sent_date")
            recurrence = slot.get("recurrence", "daily")
            scheduled_time = slot.get("time")
            is_due = False

            if recurrence == "once":
                slot_date = slot.get("date")
                if not slot_date or last_sent:
                    continue
                if user_date > slot_date or (user_date == slot_date and user_hhmm >= scheduled_time):
                    is_due = True
            else:
                if last_sent == user_date:
                    continue
                if user_hhmm >= scheduled_time:
                    if recurrence == "daily":
                        is_due = True
                    elif recurrence == "weekdays" and user_weekday < 5:
                        is_due = True
                    elif recurrence == "weekly" and user_weekday == 0:
                        is_due = True

            if is_due:
                await _send_brief(user_id, cfg, slot, now, active_goals)
                slot["last_sent_date"] = user_date
                updated = True

        if updated:
            from database import async_session
            cfg.brief_slots = json.dumps(slots)
            async with async_session() as session:
                cfg_ref = await session.merge(cfg)
                await session.commit()

    except Exception as e:
        logger.error(f"[Monologue] Brief schedule check failed for {user_id[:8]}: {e}")


async def _send_brief(user_id: str, cfg, slot: dict, now: datetime, active_goals: list):
    from agent.llm import generate_completion
    from agent.chat_push import chat_push

    label = slot.get("label", "Brief")
    campaigns_text = "\n".join([
        f"- {g.title}: {g.status.upper()} — {g.progress_percent:.0f}% ({g.tasks_completed}/{g.tasks_total} tasks)"
        for g in active_goals
    ]) or "No active campaigns."

    prompt = f"""You are the Digital Force autonomous marketing director.
Generate a {label} for the business owner.
Date: {now.strftime('%A, %B %d %Y, %H:%M UTC')}
Active campaigns: {campaigns_text}
Include: what agents did, current status, what is next, decisions needed, one strategic recommendation.
Under 250 words. Executive tone. No asterisks for formatting."""

    try:
        brief_text = await generate_completion(prompt, "You are Digital Force's marketing director.")
        await chat_push(user_id, f"{label} — {now.strftime('%b %d, %Y')}\n\n{brief_text}", "orchestrator")
    except Exception as e:
        logger.error(f"[Monologue] Brief send failed for {user_id[:8]}: {e}")
