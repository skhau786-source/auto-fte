"""
Application configuration via environment variables.

All settings are validated at startup. Missing required variables
raise a clear error message before the server starts.
"""

import logging
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator


class Settings(BaseSettings):
    # ═══════════════════════════════════════════════════════════════
    # Application
    # ═══════════════════════════════════════════════════════════════
    APP_NAME: str = "Digital FTE Auth Service"
    ENV: str = "development"
    DEBUG: bool = True

    @field_validator("ENV")
    @classmethod
    def validate_env(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v.lower() not in allowed:
            raise ValueError(f"ENV must be one of {allowed}, got '{v}'")
        return v.lower()

    # ═══════════════════════════════════════════════════════════════
    # Database
    # ═══════════════════════════════════════════════════════════════
    DATABASE_URL: str

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            # Allow postgresql:// as fallback (alembic uses this)
            if v.startswith("postgresql://"):
                return v
            raise ValueError(
                "DATABASE_URL must start with 'postgresql+asyncpg://' "
                "for async SQLAlchemy. Got: " + v[:30] + "..."
            )
        return v

    # ═══════════════════════════════════════════════════════════════
    # JWT
    # ═══════════════════════════════════════════════════════════════
    SECRET_KEY: str = "default-dev-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ═══════════════════════════════════════════════════════════════
    # Google OAuth
    # ═══════════════════════════════════════════════════════════════
    GOOGLE_CLIENT_ID: str = ""

    # ═══════════════════════════════════════════════════════════════
    # Redis
    # ═══════════════════════════════════════════════════════════════
    REDIS_URL: str = "redis://localhost:6379/0"

    # ═══════════════════════════════════════════════════════════════
    # Shopify API
    # ═══════════════════════════════════════════════════════════════
    SHOPIFY_API_KEY: str = ""
    SHOPIFY_API_SECRET: str = ""
    SHOPIFY_WEBHOOK_SECRET: str = ""
    SHOPIFY_API_VERSION: str = "2024-07"

    # ═══════════════════════════════════════════════════════════════
    # WooCommerce API
    # ═══════════════════════════════════════════════════════════════
    WOOCOMMERCE_API_VERSION: str = "wc/v3"
    WOOCOMMERCE_WEBHOOK_SECRET: str = ""
    WOOCOMMERCE_SYNC_INTERVAL_HOURS: int = 6
    WOOCOMMERCE_LOW_STOCK_THRESHOLD: int = 10

    # ═══════════════════════════════════════════════════════════════
    # Celery
    # ═══════════════════════════════════════════════════════════════
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ═══════════════════════════════════════════════════════════════
    # AI / LLM
    # ═══════════════════════════════════════════════════════════════
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # ═══════════════════════════════════════════════════════════════
    # CORS & Security
    # ═══════════════════════════════════════════════════════════════
    CORS_ORIGINS: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse CORS_ORIGINS comma-separated string into a list."""
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    TRUSTED_HOSTS: str = "localhost,127.0.0.1"

    @property
    def trusted_host_list(self) -> list[str]:
        return [h.strip() for h in self.TRUSTED_HOSTS.split(",") if h.strip()]

    # ═══════════════════════════════════════════════════════════════
    # Inventory Sync
    # ═══════════════════════════════════════════════════════════════
    SYNC_INTERVAL_HOURS: int = 6
    LOW_STOCK_ALERT_THRESHOLD: int = 10
    SYNC_RETRY_MINUTES: int = 5

    # ═══════════════════════════════════════════════════════════════
    # Rate Limiting
    # ═══════════════════════════════════════════════════════════════
    RATE_LIMIT_PER_MINUTE: int = 60

    # ═══════════════════════════════════════════════════════════════
    # Logging
    # ═══════════════════════════════════════════════════════════════
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json | text

    # ═══════════════════════════════════════════════════════════════
    # AI Post Generation (from bilal) — optional, features disabled if empty
    # ═══════════════════════════════════════════════════════════════
    GROQ_API_KEY: str = ""
    HUGGINGFACE_API_TOKEN: str = ""

    # ═══════════════════════════════════════════════════════════════
    # Instagram / Meta Graph API (from bilal)
    # ═══════════════════════════════════════════════════════════════
    INSTAGRAM_APP_ID: str = ""
    INSTAGRAM_APP_SECRET: str = ""
    INSTAGRAM_REDIRECT_URI: str = ""
    GRAPH_API_VERSION: str = "v21.0"
    INSTAGRAM_WEBHOOK_VERIFY_TOKEN: str = "digital_fte_secret_token"

    # ═══════════════════════════════════════════════════════════════
    # SMTP Email Notifications (from bilal)
    # ═══════════════════════════════════════════════════════════════
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAILS_FROM_EMAIL: str = ""

    # ═══════════════════════════════════════════════════════════════
    # Stripe (Payments) — from kulsoom
    # ═══════════════════════════════════════════════════════════════
    # Left blank in dev/test on purpose — SubscriptionService raises a
    # clear StripeNotConfiguredError at call time if a billing endpoint
    # is actually invoked without these set, rather than failing at
    # import/startup (billing is an optional feature per-deployment).
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_SUCCESS_URL: str = "http://localhost:3000/billing/success"
    STRIPE_CANCEL_URL: str = "http://localhost:3000/billing/cancel"

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}, got '{v}'")
        return v.upper()

    # ═══════════════════════════════════════════════════════════════
    # Model Config
    # ═══════════════════════════════════════════════════════════════
    @model_validator(mode="after")
    def validate_production_settings(self):
        """Validate production-specific settings."""
        if self.ENV == "production":
            if not self.SHOPIFY_API_SECRET:
                raise ValueError(
                    "SHOPIFY_API_SECRET is required in production "
                    "— webhook HMAC verification will fail without it"
                )
            if not self.SECRET_KEY or self.SECRET_KEY == "default-dev-secret":
                raise ValueError(
                    "SECRET_KEY must be a strong random value in production"
                )
            if self.CORS_ORIGINS == "*":
                raise ValueError(
                    "CORS_ORIGINS cannot be '*' in production — "
                    "set to your app's exact domain"
                )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
