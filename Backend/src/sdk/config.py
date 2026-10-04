# ═══════════════════════════════════════════════════════════════
# src / sdk / config.py
#
# PURPOSE: Centralized configuration using Pydantic Settings.
#          Combines FTE Agent core settings with Auth, Email,
#          JWT, and Multi-platform E-commerce settings.
# ═══════════════════════════════════════════════════════════════

from pydantic_settings import BaseSettings
from pydantic import ConfigDict, model_validator
from functools import lru_cache
from typing import Optional, List


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Digital FTE Agent"
    APP_VERSION: str = "1.0.0"
    ENV: str = "development"
    DEBUG: bool = True

    # Database — shared PostgreSQL for all agents (Async)
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/digital_fte"

    # Redis / Event Bus — inter-agent communication
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: Optional[str] = None

    # Orchestrator — agent registry + heartbeat
    ORCHESTRATOR_URL: str = "http://localhost:8000"
    AGENT_TOKEN: str = ""

    # ── JWT & Auth Settings ───────────────────────────────────────
    SECRET_KEY: str = "default-dev-secret-change-in-production-32chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""

    # CORS
    CORS_ORIGINS: str = "*"

    @property
    def cors_origin_list(self) -> List[str]:
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # Email (SMTP)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = ""
    FRONTEND_URL: str = "http://localhost:3000"

    # Rate Limiting
    RATE_LIMIT_LOGIN_MAX_ATTEMPTS: int = 5
    RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = 900

    # Public website chat (anjaan visitors, bina login) — /api/v1/public/stores/{key}/chat
    PUBLIC_CHAT_ENABLED: bool = True
    PUBLIC_CHAT_MAX_QUERY_CHARS: int = 1000
    PUBLIC_CHAT_SESSION_TTL_DAYS: int = 30
    PUBLIC_CHAT_CHAT_PER_IP_PER_MINUTE: int = 30
    PUBLIC_CHAT_CHAT_PER_SESSION_PER_MINUTE: int = 10
    PUBLIC_CHAT_POLL_PER_IP_PER_MINUTE: int = 120
    PUBLIC_CHAT_POLL_PER_SESSION_PER_MINUTE: int = 30
    PUBLIC_CHAT_NEW_SESSIONS_PER_IP_PER_HOUR: int = 20
    # True sirf tab jab app trusted reverse proxy ke peeche ho (warna X-Forwarded-For spoof ho sakta hai)
    TRUST_PROXY_HEADERS: bool = False

    # LLM API — content gen, comment engagement, customer support
    # Default: Google Gemini (gemini-2.0-flash-exp is fast + cheap, good for our use cases)
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gemini-2.0-flash-exp"

    # Encryption — protects ALL platform tokens at rest (Fernet)
    ENCRYPTION_KEY: str = ""

    # ─── Platform: Shopify ────────────────────────────────────────
    SHOPIFY_API_KEY: str = ""
    SHOPIFY_API_SECRET: str = ""
    SHOPIFY_SCOPES: str = "read_products,read_orders"
    SHOPIFY_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/shopify/callback"
    BACKEND_PUBLIC_URL: str = "http://localhost:8000"
    FRONTEND_SUCCESS_URL: str = "http://localhost:3000/dashboard"

    # ─── Platform: WooCommerce ────────────────────────────────────
    WOOCOMMERCE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/woocommerce/callback"

    # ─── Platform: BigCommerce ────────────────────────────────────
    BIGCOMMERCE_CLIENT_ID: str = ""
    BIGCOMMERCE_CLIENT_SECRET: str = ""
    BIGCOMMERCE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/bigcommerce/callback"

    # ─── Platform: Amazon SP-API ──────────────────────────────────
    AMAZON_CLIENT_ID: str = ""
    AMAZON_CLIENT_SECRET: str = ""
    AMAZON_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/amazon/callback"
    AMAZON_REFRESH_TOKEN: str = ""

    # ─── Platform: Daraz / Lazada ─────────────────────────────────
    DARAZ_APP_KEY: str = ""
    DARAZ_APP_SECRET: str = ""
    DARAZ_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/daraz/callback"

    # ─── Content Generation: Image Models ─────────────────────────
    GEMINI_API_KEY: str = ""
    DALLE_API_KEY: str = ""
    IMAGE_MODEL_DEFAULT: str = "gemini-2.0-flash-exp"

    # ─── Content Scheduling: Social Platforms ─────────────────────
    TIKTOK_CLIENT_KEY: str = ""
    TIKTOK_CLIENT_SECRET: str = ""
    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_CLIENT_SECRET: str = ""

    # Sync defaults
    LOW_STOCK_THRESHOLD: int = 10
    ORDERS_SYNC_DAYS: int = 90

    @model_validator(mode="after")
    def validate_production(self):
        if self.ENV == "production":
            if not self.SECRET_KEY or self.SECRET_KEY == "default-dev-secret-change-in-production-32chars" or len(self.SECRET_KEY) < 32:
                raise ValueError("SECRET_KEY must be a strong random value (32+ chars) in production")
            if self.CORS_ORIGINS == "*":
                raise ValueError("CORS_ORIGINS cannot be '*' in production")
        return self

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
