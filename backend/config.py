"""
Digital Force — Central Configuration
All environment variables, loaded once, cached globally.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from typing import Optional
import os


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────
    app_name: str = "Digital Force"
    app_version: str = "2.0.0"
    environment: str = "development"  # development | staging | production
    debug: bool = True
    base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"

    # ── Security ─────────────────────────────────────────
    jwt_secret_key: str = "CHANGE-THIS-IN-PRODUCTION-USE-256-BIT-KEY"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440   # 24 hours
    encryption_key: str = "CHANGE-THIS-32-BYTE-KEY-IN-PROD!!"

    # ── Database ─────────────────────────────────────────
    # PostgreSQL for production, SQLite for dev
    database_url: str = "sqlite+aiosqlite:///./digitalforce.db"
    # PostgreSQL example:
    # database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/digitalforce"

    # ── Redis ─────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_password: Optional[str] = None

    # ── AI Ecosystem: Groq Key Cluster (up to 10 keys = 30 cascade slots) ─────
    # Add keys as GROQ_API_KEY_1 through GROQ_API_KEY_10 in your .env
    # Each key = 100k tokens/day free. 10 keys = 1M tokens/day = ~666 content pieces/day
    groq_api_key_1: str = ""
    groq_api_key_2: str = ""
    groq_api_key_3: str = ""
    groq_api_key_4: str = ""
    groq_api_key_5: str = ""
    groq_api_key_6: str = ""
    groq_api_key_7: str = ""
    groq_api_key_8: str = ""
    groq_api_key_9: str = ""
    groq_api_key_10: str = ""

    # Groq models (best → fast → stable)
    groq_primary_model: str = "llama-3.3-70b-versatile"
    groq_secondary_model: str = "llama-3.1-8b-instant"
    groq_fallback_model: str = "gemma2-9b-it"

    groq_max_tokens: int = 4096
    groq_temperature: float = 0.7

    # ── Additional AI Providers (optional — extend capacity beyond Groq) ─────
    openai_api_key: str = ""        # GPT-4o-mini: cheap, high-cap, reliable
    together_api_key: str = ""      # Llama/Mixtral: cheap bulk inference
    gemini_api_key: str = ""        # Gemini 1.5 Flash: generous free tier

    @property
    def all_groq_keys(self) -> list[str]:
        """Returns all configured Groq API keys as a flat list, filtering empties."""
        return [k for k in [
            self.groq_api_key_1, self.groq_api_key_2, self.groq_api_key_3,
            self.groq_api_key_4, self.groq_api_key_5, self.groq_api_key_6,
            self.groq_api_key_7, self.groq_api_key_8, self.groq_api_key_9,
            self.groq_api_key_10,
        ] if k]

    # ── Vector DB: Qdrant ─────────────────────────────────
    qdrant_url: str = ""                          # Cloud: https://xxx.qdrant.io
    qdrant_api_key: str = ""
    qdrant_local_path: str = "./qdrant_data"     # Local fallback
    # Collections
    qdrant_knowledge_collection: str = "df-knowledge"
    qdrant_media_collection: str = "df-media"
    qdrant_brand_collection: str = "df-brand"
    qdrant_dimension: int = 384                  # all-MiniLM-L6-v2

    # ── Publishing: Buffer API ────────────────────────────
    buffer_access_token: str = ""
    buffer_api_url: str = "https://api.bufferapp.com/1"

    # ── Publishing: Facebook Graph API ───────────────────
    facebook_page_id: str = ""
    facebook_access_token: str = ""
    facebook_api_version: str = "v21.0"

    # ── Image Generation ──────────────────────────────────
    stability_api_key: str = ""               # Stable Diffusion alternative

    # ── Image Storage ─────────────────────────────────────
    # Local storage (default) or S3/R2
    storage_backend: str = "local"           # local | s3 | r2
    media_upload_dir: str = "./media/uploads"
    media_processed_dir: str = "./media/processed"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    r2_account_id: str = ""
    r2_access_key: str = ""
    r2_secret_key: str = ""
    r2_bucket: str = ""

    # ── Email (for approval notifications) ───────────────
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_name: str = "Digital Force"
    smtp_from_email: str = "noreply@digitalforce.ai"
    target_notification_emails: str = ""
    admin_whatsapp_number: str = ""

    # ── SkillForge (E2B Sandbox) ──────────────────────────
    e2b_api_key: str = ""
    skillforge_enabled: bool = True

    # ── Web Research ──────────────────────────────────────
    tavily_api_key: str = ""                  # Tavily Search API
    serpapi_key: str = ""                     # SerpAPI alternative

    # ── Agent Configuration ───────────────────────────────
    proxy_provider_api: str = ""
    agent_max_iterations: int = 10
    agent_timeout_seconds: int = 300
    approval_token_expires_hours: int = 48

    # ── CORS ─────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def qdrant_use_cloud(self) -> bool:
        return bool(self.qdrant_url and self.qdrant_api_key)

    class Config:
        env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton — loaded once at startup."""
    s = Settings()
    try:
        override_file = os.path.join(os.path.dirname(__file__), "settings_override.json")
        if os.path.exists(override_file):
            import json
            with open(override_file, "r") as f:
                data = json.load(f)
            for k, v in data.items():
                if hasattr(s, k):
                    setattr(s, k, v)
    except Exception:
        pass
    return s
