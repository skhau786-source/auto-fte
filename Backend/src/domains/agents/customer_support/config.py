# ═══════════════════════════════════════════════════════════════
# agents / customer_support / config.py
#
# PURPOSE: Settings for Customer Support Agent (Phase 4).
# ═══════════════════════════════════════════════════════════════

from functools import lru_cache

from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Customer Support Agent"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8005

    # Database & Redis
    DATABASE_URL: str = (
        "postgresql+asyncpg://fte_user:fte_password@localhost:5432/fte_db"
    )
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM Settings
    # Read GEMINI_API_KEY from the shared .env file.
    LLM_API_KEY: str = Field(
        default="",
        validation_alias="GEMINI_API_KEY",
    )
    LLM_MODEL: str = "gemini-3.5-flash-lite"

    # Shopify Storefront API
    SHOPIFY_STOREFRONT_API_URL: str = (
        "https://{shop}/api/2024-01/graphql.json"
    )
    STOREFRONT_ACCESS_TOKEN: str = ""

    # Support Rules
    HANDOFF_KEYWORDS: list[str] = [
        "refund",
        "cancel my order",
        "cancel order",
        "return policy",
        "scam",
        "fraud",
        "sue",
        "legal",
        "talk to human",
        "speak to representative",
    ]

    OUT_OF_SCOPE_KEYWORDS: list[str] = [
        "refund",
        "cancel",
        "chargeback",
        "lawyer",
    ]

    MAX_RAG_PRODUCTS: int = 5

    # Knowledge base (owner ke uploaded documents) se jawab
    KB_ENABLED: bool = True
    KB_TOP_K: int = 3
    KB_MIN_SCORE: float = 0.3   # query ke meaningful words ka kitna hissa match ho

    SUPPORTED_LANGUAGES: list[str] = [
        "en",
        "roman_urdu",
        "urdu",
    ]

    # Security
    AUTH_ENABLED: bool = False
    API_KEYS: list[str] = ["dev-key-123"]

    # CORS
    # Shared .env uses a comma-separated string.
    CORS_ORIGINS: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        """Return CORS origins as a clean list."""
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]

        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return cached customer support settings."""
    return Settings()