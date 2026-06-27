"""app/config.py — Pydantic-Settings; reads from .env automatically."""
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME    : str  = "NexusCRM"
    APP_VERSION : str  = "2.4.0"
    DEBUG       : bool = True
    SECRET_KEY  : str  = "change-me-in-production"

    # PostgreSQL — asyncpg for FastAPI, psycopg2 for Alembic CLI
    DATABASE_URL      : str = "postgresql+asyncpg://postgres:16082003@localhost:5432/postgres"
    SYNC_DATABASE_URL : str = "postgresql+psycopg2://postgres:16082003@localhost:5432/postgres"

settings = Settings()
