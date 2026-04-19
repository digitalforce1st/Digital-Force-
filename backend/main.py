"""
Digital Force — Main FastAPI Application
"""

import sys
import asyncio

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("🚀 Digital Force starting up...")
    await init_db()
    logger.info("✅ Database initialized")

    # Ensure Qdrant collections exist
    try:
        from rag.retriever import ensure_collections
        await ensure_collections()
        logger.info("✅ Qdrant collections ready")
    except Exception as e:
        logger.warning(f"⚠️  Qdrant not available: {e}")

    # Ensure media directories exist
    Path(settings.media_upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.media_processed_dir).mkdir(parents=True, exist_ok=True)
    logger.info("✅ Media directories ready")

    logger.info(f"🧠 LLM cascade: Groq Keys: {[bool(settings.groq_api_key_1), bool(settings.groq_api_key_2), bool(settings.groq_api_key_3)]}")
    logger.info(f"📡 Publishing: Buffer={bool(settings.buffer_access_token)} | Facebook={bool(settings.facebook_access_token)}")

    # 👻 Start the Ghost Browser (Persistent Session Playwright)
    from agent.browser.ghost import ghost
    await ghost.start()

    # 🧠 Start the Internal Monologue Worker — replaces agency_daemon.py
    # Non-blocking. Paginated. Randomized sleep. The agent is now truly alive.
    from langclaw_agents.monologue_worker import internal_monologue
    asyncio.create_task(internal_monologue())
    logger.info("🧠 Internal Monologue Worker started — Digital Force 2.0 is alive")

    # 📧 Start the Inbox Poller — listining for user email replies
    from agent.tools.email_inbox import poll_email_inbox
    asyncio.create_task(poll_email_inbox())
    logger.info("📧 IMAP Inbox Poller scheduled")

    logger.info("✨ Digital Force is ready.")

    yield

    logger.info("👋 Digital Force shutting down...")
    
    # Clean up browser persistence
    await ghost.stop()


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

# Routers
app.include_router(auth_router)
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


@app.get("/api/health")
async def health():
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
            "buffer": bool(settings.buffer_access_token),
            "facebook": bool(settings.facebook_access_token),
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
