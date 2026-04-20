"""
Digital Force — Ghost Browser
Persistent headless Playwright session that holds authenticated state
to allow agents to bypass CAPTCHAs and login walls seamlessly.
"""

import asyncio
import logging
from pathlib import Path
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page
from typing import Optional

logger = logging.getLogger(__name__)

# Where we store persistent cookies/session state
SESSION_DIR = Path(__file__).parent.parent.parent / "ghost_session_data"

class GhostBrowser:
    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._contexts: dict[str, BrowserContext] = {}
        self._lock = asyncio.Lock()
        
    async def start(self):
        """Initialise the Playwright engine without immediately launching browsers."""
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        try:
            self._playwright = await async_playwright().start()
            logger.info("👻 Ghost Browser Playwright engine started (waiting for context requests).")
        except Exception as e:
            # Non-fatal: Ghost Browser is optional. Agents that need it will
            # receive a clear error. We must NOT crash the entire backend here.
            logger.warning(f"⚠️  Ghost Browser unavailable (Playwright failed to start): {e}")
            logger.warning("   Web scraping via headless browser will be disabled this session.")
            self._playwright = None
            
    async def stop(self):
        """Cleanly shutdown all browser contexts."""
        logger.info("👻 Ghost Browser shutting down all contexts...")
        for account_id, ctx in self._contexts.items():
            await ctx.close()
            logger.info(f"Closed context for {account_id}")
        self._contexts.clear()
        if self._playwright:
            await self._playwright.stop()
            
    async def get_page(self, account_id: str = "default", proxy_url: Optional[str] = None) -> Page:
        """
        Retrieves a new tab in the persistent context isolated for this account.
        Spawns the context automatically if it doesn't exist yet!
        Callers MUST ensure they close the page when done: `await page.close()`
        """
        async with self._lock:
            if not self._playwright:
                raise RuntimeError("GhostBrowser Playwright engine is not running.")
            
            if account_id not in self._contexts:
                profile_dir = SESSION_DIR / account_id
                profile_dir.mkdir(parents=True, exist_ok=True)
                
                launch_options = {
                    "user_data_dir": str(profile_dir),
                    "headless": True,
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "viewport": {"width": 1920, "height": 1080},
                    "locale": "en-US",
                    "args": [
                        "--disable-blink-features=AutomationControlled", # Anti-bot mitigation
                        "--disable-infobars",
                        "--no-sandbox", # CRITICAL FOR 6GB RAM - Disables Chrome's memory-heavy process isolation
                        "--disable-dev-shm-usage", # Prevents Chrome from crashing due to tight shared memory limits
                    ]
                }
                
                if proxy_url:
                    launch_options["proxy"] = {"server": proxy_url}
                    logger.info(f"👻 Provisioning Proxy for {account_id}: {proxy_url.split('@')[-1] if '@' in proxy_url else proxy_url}")
                
                context = await self._playwright.chromium.launch_persistent_context(**launch_options)
                self._contexts[account_id] = context
                logger.info(f"👻 Launched new persistent isolated context for: {account_id}")

            # Grab the specific requested context
            page = await self._contexts[account_id].new_page()
            # Anti-bot bypass injection
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return page

    @property
    def is_running(self) -> bool:
        """True if the Playwright engine was successfully initialised and is available."""
        return self._playwright is not None


# Global instance managed by FastAPI Lifespan
ghost = GhostBrowser()
