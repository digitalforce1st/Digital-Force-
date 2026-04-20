"""
Digital Force — Ghost Browser
Persistent Playwright sessions with per-account isolation and concurrency control.

UPDATED (2.3 — Scale Hardening):
- REMOVED the global lock that serialized ALL browser operations
- Per-account locks: each account session has its own lock so parallel posting works
- Max concurrent contexts limit: prevents RAM exhaustion on slow machines
- Semaphore pool: controls how many browser contexts run simultaneously
- Context reuse: pages share a context (no new Chromium process per page = fast)
- RAM-aware defaults: max 5 concurrent contexts (configurable via GHOST_MAX_CONTEXTS env)
"""

import asyncio
import logging
from pathlib import Path
from playwright.async_api import async_playwright, Playwright, BrowserContext, Page
from typing import Optional
import os

logger = logging.getLogger(__name__)

SESSION_DIR = Path(__file__).parent.parent.parent / "ghost_session_data"

# How many browser contexts can be ACTIVE simultaneously.
# Each context uses ~150-300MB RAM. Default 5 = safe on 4GB. Set higher on beefy machines.
MAX_CONCURRENT_CONTEXTS = int(os.environ.get("GHOST_MAX_CONTEXTS", "5"))


class GhostBrowser:
    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._contexts: dict[str, BrowserContext] = {}
        self._account_locks: dict[str, asyncio.Lock] = {}  # Per-account lock (not global)
        self._semaphore: Optional[asyncio.Semaphore] = None  # Concurrency limiter
        self._global_lock = asyncio.Lock()  # Only for context dict mutation

    async def start(self):
        """Initialise the Playwright engine. Non-fatal if Playwright isn't installed."""
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_CONTEXTS)
        try:
            self._playwright = await async_playwright().start()
            logger.info(
                f"Ghost Browser started. Max concurrent contexts: {MAX_CONCURRENT_CONTEXTS}"
            )
        except Exception as e:
            logger.warning(f"Ghost Browser unavailable (Playwright failed): {e}")
            self._playwright = None

    async def stop(self):
        """Cleanly close all open browser contexts."""
        logger.info("Ghost Browser shutting down...")
        async with self._global_lock:
            for ctx_key, ctx in list(self._contexts.items()):
                try:
                    await ctx.close()
                except Exception:
                    pass
            self._contexts.clear()
        if self._playwright:
            await self._playwright.stop()

    def _get_account_lock(self, account_id: str) -> asyncio.Lock:
        """Get or create a per-account lock. Thread-safe via simple dict check."""
        if account_id not in self._account_locks:
            self._account_locks[account_id] = asyncio.Lock()
        return self._account_locks[account_id]

    async def get_page(
        self,
        account_id: str = "default",
        proxy_url: Optional[str] = None,
        headless: bool = True,
    ) -> Page:
        """
        Get a new page tab from the persistent context for this account.

        KEY CHANGES vs old version:
        - Uses per-account lock (not global) → different accounts post in PARALLEL
        - Semaphore limits total concurrent contexts (RAM protection)
        - Context persists between calls → no cold-start per page
        - Callers MUST call page.close() when done

        Args:
            account_id: Unique session ID — one isolated Chromium profile per account
            proxy_url: Optional HTTP/SOCKS proxy string
            headless: False for auth flows (WhatsApp, Instagram login) — headed avoids detection
        """
        if not self._playwright:
            raise RuntimeError("Ghost Browser is not running.")

        ctx_key = f"{account_id}__{'headed' if not headless else 'headless'}"
        account_lock = self._get_account_lock(ctx_key)

        async with account_lock:
            if ctx_key not in self._contexts:
                # Wait for a free slot before opening a new context
                await self._semaphore.acquire()

                try:
                    profile_dir = SESSION_DIR / account_id
                    profile_dir.mkdir(parents=True, exist_ok=True)

                    launch_options = {
                        "user_data_dir": str(profile_dir),
                        "headless": headless,
                        "user_agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/122.0.0.0 Safari/537.36"
                        ),
                        "viewport": {"width": 1920, "height": 1080},
                        "locale": "en-US",
                        "args": [
                            "--disable-blink-features=AutomationControlled",
                            "--disable-infobars",
                            "--no-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                            "--disable-extensions",
                            "--disable-background-networking",
                        ],
                    }

                    if proxy_url:
                        launch_options["proxy"] = {"server": proxy_url}

                    context = await self._playwright.chromium.launch_persistent_context(
                        **launch_options
                    )
                    async with self._global_lock:
                        self._contexts[ctx_key] = context

                    mode = "HEADED" if not headless else "headless"
                    logger.info(f"Ghost Browser: new {mode} context for '{account_id}' (active: {len(self._contexts)}/{MAX_CONCURRENT_CONTEXTS})")

                except Exception as e:
                    self._semaphore.release()
                    raise e

        # Open a new tab in the existing context (fast — no new process)
        page = await self._contexts[ctx_key].new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return page

    async def release_context(self, account_id: str):
        """
        Close and release a context back to the pool.
        Call this when a session is done and we want to free the semaphore slot.
        NOTE: In normal posting, we keep contexts open (session persistence).
        Only call this to free RAM or force re-auth.
        """
        for suffix in ["__headless", "__headed"]:
            ctx_key = f"{account_id}{suffix}"
            async with self._global_lock:
                if ctx_key in self._contexts:
                    try:
                        await self._contexts[ctx_key].close()
                    except Exception:
                        pass
                    del self._contexts[ctx_key]
                    self._semaphore.release()
                    logger.info(f"Ghost Browser: released context '{ctx_key}'")

    async def close_context(self, account_id: str):
        """Alias for release_context — used by re-auth flows."""
        await self.release_context(account_id)

    @property
    def is_running(self) -> bool:
        return self._playwright is not None

    @property
    def active_context_count(self) -> int:
        return len(self._contexts)


ghost = GhostBrowser()
