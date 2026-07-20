from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Digital FTE Auth Service"
    ENV: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str  # postgresql+asyncpg://user:pass@host:5432/dbname
    
    # Google OAuth
    GOOGLE_CLIENT_ID: str

    # Redis (used for logout/token blacklist)
    REDIS_URL: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
