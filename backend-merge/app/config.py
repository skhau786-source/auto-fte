from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Digital FTE Automation Service"
    ENV: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/digital_fte_db"

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""

    REDIS_URL: str = "redis://localhost:6379/0"

    # AI Post Generation & Tone
    GROQ_API_KEY: str = ""
    HUGGINGFACE_API_TOKEN: str = ""

    # Instagram / Meta Graph API
    INSTAGRAM_APP_ID: str = ""
    INSTAGRAM_APP_SECRET: str = ""
    INSTAGRAM_REDIRECT_URI: str = ""
    GRAPH_API_VERSION: str = "v21.0"
    INSTAGRAM_WEBHOOK_VERIFY_TOKEN: str = "digital_fte_secret_token"

    # SMTP Email Notifications (Gmail App Password)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAILS_FROM_EMAIL: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
