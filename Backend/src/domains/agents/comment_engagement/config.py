# ═══════════════════════════════════════════════════════════════
# agents / comment_engagement / config.py
#
# PURPOSE: Comment Engagement Agent settings.
#          Meta API creds, escalation keywords, poll interval.
#
# USED BY: handler.py, meta_client.py, worker.py, api.py
# ═══════════════════════════════════════════════════════════════

from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "Comment Engagement Agent"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/digital_fte"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Meta (Instagram / Facebook) — same token shape as content_scheduling's SocialAccount
    META_ACCESS_TOKEN: str = ""

    # LLM (shared client — see fte_sdk/llm/client.py)
    LLM_API_KEY: str = ""

    # Escalation — comments containing these are NEVER auto-replied,
    # always flagged for a human instead (safety-first, per architecture doc).
    ESCALATION_KEYWORDS: list[str] = [
        "refund", "scam", "fraud", "worst", "complaint",
        "cancel my order", "disappointed", "legal", "sue",
    ]

    # Rule-based reply triggers — simple keyword → templated reply,
    # no LLM call needed for these (fast + free + predictable).
    PRICE_KEYWORDS: list[str] = ["price", "kitna", "kitne ka", "cost", "rate"]

    # Background comment-poll interval (checks Meta for new comments
    # on tracked posts). Mirrors content_scheduling's scheduler pattern.
    POLL_INTERVAL_SECONDS: int = 120

    # Auth (dashboard API)
    AUTH_ENABLED: bool = True
    API_KEYS: list[str] = ["dev-key-change-me"]

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8004

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
