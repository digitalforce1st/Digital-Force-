"""
Digital Force 2.0 — Internal Monologue Worker
==============================================
The "Living Organism" heartbeat that replaces the old crashing agency_daemon.py.

KEY DIFFERENCES from the old daemon:
  - OLD: Queried ALL users into RAM simultaneously → OOM crash.
  - NEW: Paginated, non-blocking. Processes one user at a time in isolation.

  - OLD: Hardcoded 5-minute cron interval → felt robotic and mechanical.
  - NEW: Randomized sleep delay (180–480s) → feels organic and alive.

  - OLD: Ran blocking research inline on the main web thread → froze the API.
  - NEW: Runs as a standalone asyncio.Task, completely isolated from the HTTP thread.

  - OLD: Always pushed research briefs every 2 hours regardless of relevance.
  - NEW: Builds a "queue of thoughts" in Postgres. Only pushes to the user's
    Chat Hub when a thought exceeds the RELEVANCE_THRESHOLD.

Architecture:
  main.py ──► asyncio.create_task(internal_monologue()) ──► infinite loop
              (Does NOT block HTTP requests. Fully isolated.)

The Relevance Threshold:
  Every background research output is scored 0-100 by the LLM.
  Only scores >= RELEVANCE_THRESHOLD (default: 75) trigger a chat push.
  Lower scores are silently logged for future Qdrant episodic memory.
"""

import asyncio
import logging
import random
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
MIN_SLEEP_SECONDS   = 180   # Minimum idle period between cycles (3 min)
MAX_SLEEP_SECONDS   = 480   # Maximum idle period between cycles (8 min)
RELEVANCE_THRESHOLD = 75    # Score (0-100) above which we interrupt the user
PROACTIVE_HOURS     = 2     # Hours between proactive research per user
IDLE_THRESHOLD_HRS  = 24    # Hours of inactivity before idle report is sent
PAGE_SIZE           = 10    # Max users processed per cycle to prevent OOM


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

async def internal_monologue():
    """
    Entry point — called from main.py lifespan as asyncio.create_task().
    Runs indefinitely with randomized sleep. Fully non-blocking.
    """
    logger.info("🧠 [Monologue] Digital Force Internal Monologue Worker started — agents are now alive")
    await asyncio.sleep(15)  # Allow DB/server to fully initialize

    while True:
        try:
            await _run_monologue_cycle()
        except Exception as e:
            logger.error(f"[Monologue] Unhandled cycle error: {e}", exc_info=True)

        # Randomized sleep — the agent feels organic, not mechanical
        sleep_duration = random.randint(MIN_SLEEP_SECONDS, MAX_SLEEP_SECONDS)
        logger.debug(f"[Monologue] Sleeping for {sleep_duration}s before next thought cycle...")
        await asyncio.sleep(sleep_duration)


# ═══════════════════════════════════════════════════════════════════════════════
# ONE MONOLOGUE CYCLE
# ═══════════════════════════════════════════════════════════════════════════════

async def _run_monologue_cycle():
    """One full internal monologue cycle. Paginated, non-blocking."""
    from database import async_session, AgencySettings
    from sqlalchemy import select

    logger.info("[Monologue] ── Starting thought cycle ──")
    now = datetime.utcnow()

    # ── Phase 1: Process active goals for ALL users (paginated) ───────────────
    await _phase_execute_goals(now)
    await _phase_retry_failed_posts(now)

    # ── Phase 2: Autonomous thinking for users with autonomous_mode=True ──────
    # PAGINATION: Load users in batches of PAGE_SIZE to avoid OOM crashes
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
            break  # No more users to process

        for agency_cfg in batch:
            try:
                await _process_user_thought(agency_cfg, now)
            except Exception as e:
                logger.error(f"[Monologue] Error processing user {agency_cfg.user_id}: {e}")

        offset += PAGE_SIZE
        # Yield control back to the event loop between batches
        await asyncio.sleep(0)

    logger.info("[Monologue] ── Thought cycle complete ──")


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — GOAL EXECUTION & RECOVERY
# ═══════════════════════════════════════════════════════════════════════════════

async def _phase_execute_goals(now: datetime):
    """Pick up stalled/pending goals and fire their orchestration. All users."""
    from database import async_session, Goal
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(
            select(Goal).where(
                Goal.status.in_(["planning", "executing", "awaiting_approval"])
            ).limit(20)  # Process up to 20 goals per cycle
        )
        goals = result.scalars().all()

    for goal in goals:
        try:
            if goal.status == "planning":
                age = (now - goal.created_at).total_seconds()
                if age > 600 and not goal.plan:
                    logger.info(f"[Monologue] Goal {goal.id[:8]} stuck in planning >10min — retrying")
                    await _retry_planning(goal)

            elif goal.status == "awaiting_approval":
                if goal.updated_at and (now - goal.updated_at).total_seconds() > 3600:
                    await _nudge_approval(goal, now)

            elif goal.status == "executing":
                if goal.updated_at and (now - goal.updated_at).total_seconds() > 900:
                    await _push_execution_status(goal)

        except Exception as e:
            logger.error(f"[Monologue] Error handling goal {goal.id}: {e}")


async def _retry_planning(goal):
    """Re-trigger Langclaw orchestration for a stuck goal."""
    from langclaw_agents.orchestrator_app import run_orchestration
    asyncio.create_task(run_orchestration(goal.id, trigger_source="monologue_retry"))


async def _nudge_approval(goal, now: datetime):
    """Remind user that a plan is waiting for their approval. Throttled to once/hour."""
    from agent.chat_push import chat_push

    if not hasattr(_nudge_approval, "_cache"):
        _nudge_approval._cache = {}
    last = _nudge_approval._cache.get(goal.id)
    if last and (now - last).total_seconds() < 3600:
        return
    _nudge_approval._cache[goal.id] = now

    await chat_push(
        goal.created_by,
        f"📋 **\"{goal.title}\"** is ready and waiting for your approval. "
        f"Reply 'approve' or open the Goals page to review the plan.",
        "orchestrator",
        goal.id,
    )


async def _push_execution_status(goal):
    """Push a factual status update for a running goal."""
    from agent.chat_push import chat_push

    pct = goal.progress_percent or 0
    done = goal.tasks_completed or 0
    total = goal.tasks_total or 0

    if pct >= 100:
        msg = f"✅ Campaign **\"{goal.title}\"** complete! All {total} tasks finished."
    else:
        msg = (
            f"📊 **\"{goal.title}\"** is running. "
            f"Progress: {pct:.0f}% ({done}/{total} tasks). "
            f"I'll update you at the next milestone."
        )
    await chat_push(goal.created_by, msg, "monitor", goal.id)


async def _phase_retry_failed_posts(now: datetime):
    """Sweep for failed posts and re-queue them for the Publisher."""
    from database import async_session, PublishedPost, AgentTask
    from sqlalchemy import select
    import uuid

    async with async_session() as session:
        result = await session.execute(
            select(PublishedPost).where(PublishedPost.status == "failed").limit(10)
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
                    description=f"Auto-Retry: Publish failed content on {post.platform}",
                    status="queued",
                    platform=post.platform,
                    connection_id=post.connection_id,
                )
                session.add(new_task)
                logger.info(f"[Monologue] Re-queued failed post {post.id[:8]}")

        if failed_posts:
            await session.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — PER-USER INTERNAL MONOLOGUE (Autonomous Thinking)
# ═══════════════════════════════════════════════════════════════════════════════

async def _process_user_thought(cfg, now: datetime):
    """
    The 'internal thought' process for a single autonomous user.
    Runs background research and only surfaces insights above the relevance threshold.
    """
    user_id = cfg.user_id

    # ── Idle detection ────────────────────────────────────────────────────────
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
        last_ran = cfg.daemon_last_ran
        hours_idle = (now - last_ran).total_seconds() / 3600 if last_ran else IDLE_THRESHOLD_HRS + 1
        if hours_idle >= IDLE_THRESHOLD_HRS:
            await _push_idle_report(user_id, cfg, now)

    # ── Proactive internal research (throttled to every PROACTIVE_HOURS) ──────
    last_research = cfg.last_proactive_research
    hours_since = (now - last_research).total_seconds() / 3600 if last_research else PROACTIVE_HOURS + 1
    if hours_since >= PROACTIVE_HOURS:
        await _run_background_thought(user_id, cfg, now)
        async with async_session() as session:
            s = await session.get(type(cfg), cfg.id)
            if s:
                s.last_proactive_research = now
                s.daemon_last_ran = now
                await session.commit()

    # ── Scheduled briefs ──────────────────────────────────────────────────────
    await _check_brief_schedule(user_id, cfg, now, active_goals)


async def _run_background_thought(user_id: str, cfg, now: datetime):
    """
    The 'subconscious' background researcher.
    Generates a research brief, scores its relevance (0-100), and only
    pushes it to the user's chat if it exceeds RELEVANCE_THRESHOLD.
    Below-threshold insights are sent silently to Qdrant as episodic memory.
    """
    from agent.llm import generate_completion, generate_json
    from agent.chat_push import chat_push
    from database import async_session, Goal, ChatMessage
    from sqlalchemy import select, desc

    logger.info(f"[Monologue] Running background thought for user {user_id[:8]}...")

    async with async_session() as session:
        goals_result = await session.execute(
            select(Goal).where(Goal.created_by == user_id)
            .order_by(desc(Goal.created_at)).limit(5)
        )
        past_goals = goals_result.scalars().all()

        chat_result = await session.execute(
            select(ChatMessage).where(ChatMessage.user_id == user_id)
            .order_by(desc(ChatMessage.created_at)).limit(15)
        )
        recent_chats = chat_result.scalars().all()

    past_campaigns_text = "\n".join([
        f"- {g.title} ({g.status})" for g in past_goals
    ]) or "No past campaigns."

    industry = cfg.industry or "technology and business"

    research_prompt = f"""You are a proactive marketing research agent with live web access.
Industry: {industry}
Brand: {cfg.brand_voice or 'Not specified'}
Past campaigns: {past_campaigns_text}
Date: {now.strftime('%A, %B %d %Y')}

Identify 2-3 trending opportunities in {industry} RIGHT NOW.
Then score your own finding: how urgent and relevant is this insight to this business?
Respond with JSON only:
{{
  "research_brief": "The full insight brief (max 200 words)",
  "headline": "One-line summary",
  "relevance_score": 85,
  "relevance_reason": "Why this is urgent/timely"
}}"""

    try:
        result = await generate_json(research_prompt, "You are a world-class marketing analyst.")
        brief = result.get("research_brief", "")
        score = int(result.get("relevance_score", 0))
        headline = result.get("headline", "Proactive Research Brief")

        if score >= RELEVANCE_THRESHOLD:
            # This thought is important — interrupt the user organically
            logger.info(f"[Monologue] High-relevance thought ({score}/100) — pushing to chat for {user_id[:8]}")
            await chat_push(
                user_id,
                f"💡 **{headline}** _(Relevance: {score}/100)_\n\n{brief}\n\n"
                f"_Reply 'launch [idea]' to act on this, or I'll keep it queued._",
                "researcher",
            )
        else:
            # Low-relevance — silently vectorize into episodic memory for future use
            logger.info(f"[Monologue] Low-relevance thought ({score}/100) — vectorizing silently")
            await _store_silent_thought(user_id, brief, score, now)

    except Exception as e:
        logger.error(f"[Monologue] Background thought failed for {user_id[:8]}: {e}")


async def _store_silent_thought(user_id: str, thought_text: str, score: int, now: datetime):
    """
    Silently embed a below-threshold thought into Qdrant episodic memory.
    The agent 'remembers' it without bothering the user.
    """
    try:
        from rag.pipeline import ingest_text
        await ingest_text(
            text=f"[Background Thought - {now.strftime('%Y-%m-%d')}] Score:{score}/100\n{thought_text}",
            source_type="internal_thought",
            metadata={
                "user_id": user_id,
                "category": "episodic_memory",
                "relevance_score": score,
                "timestamp": now.isoformat(),
            }
        )
    except Exception as e:
        logger.warning(f"[Monologue] Silent thought storage failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# IDLE REPORT & BRIEF SCHEDULER (Preserved from agency_daemon.py)
# ═══════════════════════════════════════════════════════════════════════════════

async def _push_idle_report(user_id: str, cfg, now: datetime):
    """Push an opportunity report when the agency has been idle."""
    from agent.llm import generate_completion
    from agent.chat_push import chat_push

    industry = cfg.industry or "technology and business"
    prompt = f"""The Digital Force agency has been idle — no active campaigns.
Today is {now.strftime('%A, %B %d %Y')}. Industry: {industry}
Generate a short report (under 200 words):
1. State there are no active campaigns
2. List 3 specific campaign ideas for this week
3. Suggest which one to prioritise and why
Format as a marketing director reporting to the business owner."""

    try:
        report = await generate_completion(prompt, "You are Digital Force's autonomous marketing director.")
        await chat_push(
            user_id,
            f"🟡 **Agency Status: Idle**\n\n{report}\n\n"
            f"_Say 'launch [idea]' to get started._",
            "orchestrator",
        )
    except Exception as e:
        logger.error(f"[Monologue] Idle report failed for {user_id[:8]}: {e}")


async def _check_brief_schedule(user_id: str, cfg, now: datetime, active_goals: list):
    """Check if any brief slots are due and send them. Preserved from original daemon."""
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
    """Generate and send a scheduled brief."""
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
Include: what agents did, current status, what's next, decisions needed (flagged clearly), one strategic recommendation.
Under 250 words. Executive tone."""

    try:
        brief_text = await generate_completion(prompt, "You are Digital Force's marketing director.")
        await chat_push(user_id, f"📋 **{label} — {now.strftime('%b %d, %Y')}**\n\n{brief_text}", "orchestrator")
    except Exception as e:
        logger.error(f"[Monologue] Brief send failed for {user_id[:8]}: {e}")
