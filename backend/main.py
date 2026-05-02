"""
Digital Force — Main FastAPI Application
"""

# ── LangSmith: must be configured BEFORE any langchain imports ──────────────
import os as _os
import dotenv as _dotenv
_dotenv.load_dotenv()  # Ensure .env is loaded early
_ls_key     = _os.getenv("LANGCHAIN_API_KEY", "")
_ls_tracing = _os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
_ls_project = _os.getenv("LANGCHAIN_PROJECT", "digital-force")
if _ls_key and _ls_key != "REPLACE_WITH_YOUR_LANGSMITH_KEY":
    _os.environ["LANGCHAIN_TRACING_V2"]  = "true"
    _os.environ["LANGCHAIN_API_KEY"]     = _ls_key
    _os.environ["LANGCHAIN_PROJECT"]     = _ls_project
    _os.environ["LANGCHAIN_ENDPOINT"]    = "https://api.smith.langchain.com"
    _LANGSMITH_ACTIVE = True
else:
    _os.environ["LANGCHAIN_TRACING_V2"] = "false"
    _LANGSMITH_ACTIVE = False
# ────────────────────────────────────────────────────────────────────────────

import sys
import asyncio
from typing import Set

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from config import get_settings
from database import init_db

# API Routers
from api.auth import router as auth_router
from api.goals import router as goals_router
from api.training import router as training_router
from api.media import router as media_router
from api.stream import router as stream_router
from api.skills import router as skills_router
from api.analytics import router as analytics_router
from api.settings import router as settings_router
from api.chat import router as chat_router
from api.agency import router as agency_router
from api.accounts import router as accounts_router
from api.voice import router as voice_router
from api.whatsapp import router as whatsapp_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)
settings = get_settings()

# ── GC-safe task registry — prevents background workers being silently collected ─
_STARTUP_TASKS: Set[asyncio.Task] = set()


def _safe_startup_task(coro) -> asyncio.Task:
    """Create a startup asyncio task pinned against GC until it completes."""
    task = asyncio.create_task(coro)
    _STARTUP_TASKS.add(task)
    task.add_done_callback(_STARTUP_TASKS.discard)
    return task


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown events.

    SPEED FIX: The server starts accepting requests in < 2 seconds.
    Heavy components (Ghost Browser, Qdrant, Scheduler, Monologue)
    initialize in the background AFTER yield so Ngrok never sees a
    connection timeout during hot-restart.
    """
    logger.info("🚀 Digital Force starting up...")

    # ── FAST PATH: only blocking calls that MUST happen before requests ──────
    await init_db()
    logger.info("✅ Database initialized")

    Path(settings.media_upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.media_processed_dir).mkdir(parents=True, exist_ok=True)

    active_keys = len(settings.all_groq_keys)
    logger.info(f"🧠 LLM: {active_keys} Groq key(s) configured — {active_keys * 100_000:,} tokens/day capacity")

    if _LANGSMITH_ACTIVE:
        logger.info(f"🔭 LangSmith tracing ACTIVE — project: '{_ls_project}' → https://smith.langchain.com")
    else:
        logger.warning("🔭 LangSmith tracing DISABLED — add LANGCHAIN_API_KEY to .env to enable")

    # ── BACKGROUND: Heavy non-blocking initialization ────────────────────────
    # Fire as a background task BEFORE yield so it starts immediately
    async def _background_init():
        await asyncio.sleep(2)  # Let first HTTP requests through cleanly

        try:
            from rag.retriever import ensure_collections
            await ensure_collections()
            logger.info("✅ Qdrant collections ready")
        except Exception as e:
            logger.warning(f"⚠️  Qdrant not available: {e}")

        try:
            from agent.browser.ghost import ghost
            await ghost.start()
            logger.info("✅ Ghost Browser initialized")
        except Exception as e:
            logger.warning(f"⚠️  Ghost Browser unavailable ({e})")

        try:
            from scheduler import scheduler
            await scheduler.start()
            logger.info("📅 Post Scheduler started")
        except Exception as e:
            logger.warning(f"⚠️  Post Scheduler failed ({e})")

        try:
            from langclaw_agents.monologue_worker import internal_monologue
            _safe_startup_task(internal_monologue())
            logger.info("🧠 Monologue Worker running — swarm is alive")
        except Exception as e:
            logger.warning(f"⚠️  Monologue Worker failed ({e})")

        try:
            from agent.tools.email_inbox import poll_email_inbox
            _safe_startup_task(poll_email_inbox())
            logger.info("📧 Email Inbox Poller running")
        except Exception as e:
            logger.warning(f"⚠️  Email Inbox Poller failed ({e})")

        logger.info("🎯 All systems initialized — Digital Force fully operational")

    _safe_startup_task(_background_init())

    yield  # ← ONE yield. Server ready. Background init running concurrently.

    # ── SHUTDOWN ──────────────────────────────────────────────────────────────
    logger.info("👋 Digital Force shutting down...")
    try:
        from agent.browser.ghost import ghost
        await ghost.stop()
    except Exception:
        pass
    try:
        from scheduler import scheduler
        await scheduler.stop()
    except Exception:
        pass


app = FastAPI(
    title="Digital Force API",
    description="Autonomous Social Media Intelligence Agency — v2.0",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Custom robust CORS Middleware to bypass Ngrok header stripping 400 errors
from starlette.middleware.cors import CORSMiddleware as StarletteCORSMiddleware
from starlette.responses import PlainTextResponse

class CustomCORSMiddleware(StarletteCORSMiddleware):
    def is_allowed_origin(self, origin: str) -> bool:
        # Override strict array matching to bypass trailing slash or port anomalies.
        # This forces the middleware to dynamically echo whatever Origin the browser sends,
        # which flawlessly satisfies the strict browser 'credentials' policy!
        return True

    def preflight_response(self, request_headers):
        requested_origin = request_headers.get("origin")
        requested_method = request_headers.get("access-control-request-method")
        
        # If Ngrok stripped the method, assume POST
        if not requested_method:
            requested_method = "POST"
            
        # Bypass 400 checks and artificially inject the origin
        if not requested_origin:
            requested_origin = "*"
            
        headers = {
            "Access-Control-Allow-Origin": requested_origin,
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS, PUT, DELETE, PATCH",
            "Access-Control-Allow-Headers": request_headers.get("access-control-request-headers", "*"),
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "600",
        }
        return PlainTextResponse("OK", status_code=200, headers=headers)

app.add_middleware(
    CustomCORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for media
media_dir = Path(settings.media_upload_dir)
media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")

# Static files for QR codes (WhatsApp auth)
qr_dir = Path("./media/qr_codes")
qr_dir.mkdir(parents=True, exist_ok=True)
app.mount("/qr", StaticFiles(directory=str(qr_dir)), name="qr_codes")

from api.publishing_pool import router as publishing_pool_router

# Routers
app.include_router(auth_router)
app.include_router(publishing_pool_router)
app.include_router(goals_router)
app.include_router(training_router)
app.include_router(media_router)
app.include_router(stream_router)
app.include_router(skills_router)
app.include_router(analytics_router)
app.include_router(settings_router)
app.include_router(chat_router)
app.include_router(agency_router)
app.include_router(accounts_router)
app.include_router(voice_router)
app.include_router(whatsapp_router)


@app.get("/api/health")
async def health():
    from agent.browser.ghost import ghost
    try:
        from database import async_session, PlatformConnection
        from sqlalchemy import select, func
        async with async_session() as db:
            count = await db.scalar(select(func.count(PlatformConnection.id)).where(
                PlatformConnection.connection_status == "connected"
            ))
            ghost_accounts = int(count or 0)
    except Exception:
        ghost_accounts = 0

    return {
        "status": "online",
        "service": "Digital Force",
        "version": "2.0.0",
        "architecture": "langclaw-hub-spoke",
        "llm": {
            "groq_1": bool(settings.groq_api_key_1),
            "groq_2": bool(settings.groq_api_key_2),
            "groq_3": bool(settings.groq_api_key_3),
        },
        "publishing": {
            "ghost_browser": ghost.is_running,
            "ghost_authenticated_accounts": ghost_accounts,
            "facebook": bool(settings.facebook_access_token),
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
