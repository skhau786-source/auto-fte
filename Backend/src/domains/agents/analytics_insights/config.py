# ═══════════════════════════════════════════════════════════════
# agents / analytics_insights / config.py
#
# PURPOSE: Settings for Analytics & Insights Agent (Phase 3-4).
# ═══════════════════════════════════════════════════════════════

from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Analytics & Insights Agent"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8006

    # Database & Redis
    DATABASE_URL: str = "postgresql+asyncpg://fte_user:fte_password@localhost:5432/fte_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Analytics Settings
    ROLLUP_INTERVAL_SECONDS: int = 3600      # 1 hour periodic rollup
    AGGREGATION_WINDOW_DAYS: int = 30        # 30-day default historical window
    ENABLE_LLM_SUMMARY: bool = False
    LLM_API_KEY: str = ""

    # Security
    AUTH_ENABLED: bool = False
    API_KEYS: list[str] = ["dev-key-123"]
    CORS_ORIGINS: str = "*"

    model_config = ConfigDict(
        env_file=".env",
        extra="ignore"
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
