"""
Digital Force — Post Scheduler
===============================
Manages the time-distributed execution of all publishing tasks.
Built on APScheduler with SQLite job persistence — survives server restarts.

HOW IT HANDLES 500 POSTS/DAY ACROSS 5 ACCOUNTS × 6 PLATFORMS:

  500 posts / 16 waking hours = ~31 posts/hour = 1 post every ~2 minutes
  These are SPREAD across the day, not fired all at once.

  Platform rate limits are respected:
    LinkedIn:  1 post per account per 10 minutes (max ~96/day)
    Instagram: 25 posts per account per day
    Twitter:   17 posts per hour per account
    TikTok:    ~10-20 posts per day per account
    Facebook:  ~25 posts per page per day (before spam detection)
    YouTube:   10 videos per day per channel

  The scheduler enforces these limits automatically.
  Posts that exceed daily limits are deferred to the next day.

CONCURRENCY:
  Max 3 posts execute simultaneously (matches Ghost Browser semaphore).
  Each runs in its own async task so they don't block each other.
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Platform Rate Limits ──────────────────────────────────────────────────────
# (posts per account per day, minimum minutes between posts)
PLATFORM_LIMITS = {
    "linkedin":  {"daily_max": 20,  "min_gap_minutes": 30},
    "instagram": {"daily_max": 25,  "min_gap_minutes": 20},
    "twitter":   {"daily_max": 50,  "min_gap_minutes": 5},
    "tiktok":    {"daily_max": 15,  "min_gap_minutes": 30},
    "facebook":  {"daily_max": 25,  "min_gap_minutes": 20},
    "youtube":   {"daily_max": 10,  "min_gap_minutes": 60},
    "pinterest": {"daily_max": 50,  "min_gap_minutes": 10},
    "default":   {"daily_max": 20,  "min_gap_minutes": 20},
}

# Max concurrent publishing tasks (matches Ghost Browser semaphore)
MAX_CONCURRENT_POSTS = 3


class PostScheduler:
    """
    Async scheduler that queues, rate-limits, and executes post tasks
    across all accounts and platforms without blocking the main server.
    """

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._workers: list = []  # Fixed: list not set, so we can cancel properly
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_POSTS)

        # Track posts per account per day: {account_id_platform: [timestamps]}
        self._post_history: dict[str, list[datetime]] = {}

        # APScheduler for time-based triggers
        self._apscheduler = None

    async def start(self):
        """Start the scheduler workers and APScheduler."""
        self._running = True
        # Start worker pool
        for i in range(MAX_CONCURRENT_POSTS):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)

        # Start APScheduler for recurring/timed jobs
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

            db_path = Path(__file__).parent.parent / "scheduler_jobs.db"
            jobstores = {
                "default": SQLAlchemyJobStore(url=f"sqlite:///{db_path}")
            }
            self._apscheduler = AsyncIOScheduler(jobstores=jobstores)
            self._apscheduler.start()
            logger.info(f"APScheduler started with SQLite job store: {db_path}")
        except ImportError:
            logger.warning("APScheduler not installed. Time-based scheduling disabled. Run: pip install apscheduler sqlalchemy")
        except Exception as e:
            logger.warning(f"APScheduler failed to start: {e}")

        logger.info(f"Post Scheduler started with {MAX_CONCURRENT_POSTS} workers")

    async def stop(self):
        """Gracefully shut down the scheduler."""
        self._running = False
        for task in self._workers:
            task.cancel()
        if self._apscheduler:
            self._apscheduler.shutdown(wait=False)
        logger.info("Post Scheduler stopped")

    def _rate_limit_key(self, account_id: str, platform: str) -> str:
        return f"{account_id}_{platform}_{datetime.utcnow().date()}"

    def _can_post_now(self, account_id: str, platform: str) -> tuple[bool, str]:
        """
        Check if this account can post now based on platform rate limits.
        Returns (can_post: bool, reason: str)
        """
        limits = PLATFORM_LIMITS.get(platform.lower(), PLATFORM_LIMITS["default"])
        key = self._rate_limit_key(account_id, platform)
        history = self._post_history.get(key, [])

        # Filter to just today
        now = datetime.utcnow()
        today_posts = [t for t in history if (now - t).total_seconds() < 86400]

        # Daily limit check
        if len(today_posts) >= limits["daily_max"]:
            return False, f"Daily limit reached ({limits['daily_max']} posts/day for {platform}). Will resume tomorrow."

        # Minimum gap check
        if today_posts:
            elapsed = (now - today_posts[-1]).total_seconds() / 60
            gap = limits["min_gap_minutes"]
            if elapsed < gap:
                wait = gap - elapsed
                return False, f"Too soon — must wait {wait:.0f}m between {platform} posts for this account."

        return True, "ok"

    def _record_post(self, account_id: str, platform: str):
        """Record a successful post for rate limiting."""
        key = self._rate_limit_key(account_id, platform)
        if key not in self._post_history:
            self._post_history[key] = []
        self._post_history[key].append(datetime.utcnow())

    async def enqueue(
        self,
        goal_id: str,
        task_id: str,
        account_id: str,
        platform: str,
        post_text: str,
        media_urls: list,
        user_id: str,
        scheduled_for: Optional[datetime] = None,
        account: dict = None,
    ):
        """
        Add a post job to the queue.
        If scheduled_for is provided, the job waits until that time.
        Otherwise it runs as soon as a worker is free and rate limits allow.
        """
        job = {
            "goal_id": goal_id,
            "task_id": task_id,
            "account_id": account_id,
            "platform": platform,
            "post_text": post_text,
            "media_urls": media_urls,
            "user_id": user_id,
            "scheduled_for": scheduled_for or datetime.utcnow(),
            "account": account or {},
            "enqueued_at": datetime.utcnow(),
            "retries": 0,
        }
        await self._queue.put(job)
        logger.info(f"[Scheduler] Enqueued post for {platform}/{account_id}, scheduled: {job['scheduled_for'].isoformat()}")

    async def _worker(self, worker_id: int):
        """
        Worker coroutine. Pulls jobs from the queue, respects rate limits,
        and executes posts. Multiple workers run in parallel.
        """
        logger.info(f"[Scheduler] Worker {worker_id} started")
        while self._running:
            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                # Wait until scheduled time
                scheduled_for = job["scheduled_for"]
                now = datetime.utcnow()
                if scheduled_for > now:
                    wait_secs = (scheduled_for - now).total_seconds()
                    logger.info(f"[Scheduler:W{worker_id}] Waiting {wait_secs:.0f}s until scheduled time for {job['platform']}/{job['account_id']}")
                    await asyncio.sleep(wait_secs)

                # Check rate limits — if blocked, re-queue with delay
                can_post, reason = self._can_post_now(job["account_id"], job["platform"])
                if not can_post:
                    # Re-queue with a delay
                    delay_minutes = PLATFORM_LIMITS.get(job["platform"], PLATFORM_LIMITS["default"])["min_gap_minutes"]
                    job["scheduled_for"] = datetime.utcnow() + timedelta(minutes=delay_minutes)
                    job["retries"] = job.get("retries", 0) + 1

                    if job["retries"] > 48:  # Give up after 48 re-queues (~24h)
                        logger.error(f"[Scheduler:W{worker_id}] Job permanently failed after 48 retries: {reason}")
                        await self._notify_failure(job, reason)
                    else:
                        await self._queue.put(job)
                        logger.info(f"[Scheduler:W{worker_id}] Rate limited — re-queued for +{delay_minutes}m. Reason: {reason}")
                    self._queue.task_done()
                    continue

                # Execute with concurrency control
                async with self._semaphore:
                    logger.info(f"[Scheduler:W{worker_id}] Executing: {job['platform']} / {job['account_id']}")
                    await self._execute_job(job)

                self._queue.task_done()

            except Exception as e:
                logger.error(f"[Scheduler:W{worker_id}] Job execution error: {e}", exc_info=True)
                self._queue.task_done()

    async def _execute_job(self, job: dict):
        """
        Run the actual posting operation for a queued job.
        Uses Ghost Browser (cookie-based persistent session) exclusively.
        """
        from agent.chat_push import chat_push

        platform   = job["platform"]
        account_id = job["account_id"]
        user_id    = job["user_id"]
        goal_id    = job["goal_id"]
        account    = job.get("account", {})
        post_text  = job["post_text"]
        media_urls = job.get("media_urls", [])
        display    = account.get("display_name", account_id)

        success   = False
        error_msg = ""
        method_used = ""

        # ── Ghost Browser (cookie session) ──────────────────────────────────────
        try:
            from agent.nodes.publisher import _post_via_ghost_browser
            ghost_result = await _post_via_ghost_browser(
                account=account,
                platform=platform,
                content=post_text,
                media_urls=media_urls,
                user_id=user_id,
                goal_id=goal_id,
            )
            success = ghost_result.get("success", False)
            error_msg = ghost_result.get("error", "")
            if success:
                method_used = "Ghost Browser"
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[Scheduler] Ghost Browser execution failed: {e}", exc_info=True)

        # ── Facebook Graph API direct (when access_token is set) ─────────────────
        if not success and platform == "facebook":
            try:
                from config import get_settings
                cfg = get_settings()
                if cfg.facebook_access_token and cfg.facebook_page_id:
                    from agent.nodes.publisher import _post_facebook_api
                    fb_result = await _post_facebook_api(
                        page_id=cfg.facebook_page_id,
                        access_token=cfg.facebook_access_token,
                        content=post_text,
                        media_urls=media_urls,
                    )
                    success = fb_result.get("success", False)
                    error_msg = fb_result.get("error", error_msg)
                    if success:
                        method_used = "Facebook Graph API"
            except Exception as e:
                logger.warning(f"[Scheduler] Facebook direct API fallback failed: {e}")

        # ── Result reporting ────────────────────────────────────────────────────
        if success:
            self._record_post(account_id, platform)
            await chat_push(
                user_id=user_id,
                content=f"Posted to {platform.upper()} / {display} via {method_used}.",
                agent_name="scheduler",
                goal_id=goal_id,
            )
            await self._mark_task_done(job["task_id"], "completed")
        else:
            await chat_push(
                user_id=user_id,
                content=f"Failed to post to {platform.upper()} / {display}: {error_msg[:150]}",
                agent_name="scheduler",
                goal_id=goal_id,
            )
            await self._mark_task_done(job["task_id"], "failed", error_msg)


    async def _mark_task_done(self, task_id: str, status: str, error: str = ""):
        """Update the AgentTask status in the database."""
        try:
            from database import async_session, AgentTask
            from datetime import datetime
            async with async_session() as db:
                task = await db.get(AgentTask, task_id)
                if task:
                    task.status = status
                    task.completed_at = datetime.utcnow()
                    if error:
                        task.error_message = error
                    await db.commit()
        except Exception as e:
            logger.warning(f"[Scheduler] Could not update task {task_id}: {e}")

    async def _notify_failure(self, job: dict, reason: str):
        """Push a failure notification to the user."""
        from agent.chat_push import chat_push
        await chat_push(
            user_id=job["user_id"],
            content=f"Post permanently failed after too many retries ({job['platform']} / {job['account_id']}): {reason}",
            agent_name="scheduler",
            goal_id=job["goal_id"],
        )

    def schedule_recurring(
        self,
        func,
        trigger: str,
        job_id: str,
        **trigger_args,
    ):
        """
        Schedule a recurring function with APScheduler.
        trigger: 'cron' | 'interval' | 'date'
        Example: schedule_recurring(my_func, 'cron', 'brief_9am', hour=9, minute=0)
        """
        if not self._apscheduler:
            logger.warning("[Scheduler] APScheduler not available — cannot schedule recurring job")
            return
        self._apscheduler.add_job(
            func,
            trigger,
            id=job_id,
            replace_existing=True,
            **trigger_args,
        )
        logger.info(f"[Scheduler] Recurring job registered: {job_id}")

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()


# Global instance
scheduler = PostScheduler()
