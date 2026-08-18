from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Digital FTE Agent"
    ENV: str = "development"   # production me "production" karo
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = ""

    # ── JWT (team member ke login design se merged) ──
    # Production me SECRET_KEY strong random value (32+ chars) honi chahiye.
    SECRET_KEY: str = "default-dev-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Google OAuth (login) ──
    GOOGLE_CLIENT_ID: str = ""

    # ── CORS ──
    CORS_ORIGINS: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS_ORIGINS comma-separated string ko list me parse karta hai."""
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # ── Email (verification / password reset) ──
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = ""
    FRONTEND_URL: str = ""

    # ── Rate limiting (login brute-force se bachne ke liye) ──
    RATE_LIMIT_LOGIN_MAX_ATTEMPTS: int = 5
    RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = 900  # 15 minute

    # ── Shopify ──
    SHOPIFY_API_KEY: str = ""
    SHOPIFY_API_SECRET: str = ""
    SHOPIFY_SCOPES: str = "read_products,read_orders"
    SHOPIFY_REDIRECT_URI: str = ""
    BACKEND_PUBLIC_URL: str = ""
    FRONTEND_SUCCESS_URL: str = ""

    # ── AI Post Generation ──
    HUGGINGFACE_API_TOKEN: str = ""
    GROQ_API_KEY: str = ""

    # ── Instagram Integration ──
    INSTAGRAM_APP_ID: str = ""
    INSTAGRAM_APP_SECRET: str = ""
    INSTAGRAM_REDIRECT_URI: str = "http://localhost:8000/instagram/callback"


    @model_validator(mode="after")
    def validate_production(self):
        """Production me unsafe settings hone par app start hi nahi hota."""
        if self.ENV == "production":
            if not self.SECRET_KEY or self.SECRET_KEY == "default-dev-secret" or len(self.SECRET_KEY) < 32:
                raise ValueError("SECRET_KEY must be a strong random value (32+ chars) in production")
            if self.CORS_ORIGINS == "*":
                raise ValueError("CORS_ORIGINS cannot be '*' in production - apni website ka domain daalo")
        return self

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
