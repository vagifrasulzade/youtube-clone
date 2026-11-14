"""Application settings.

Values come from environment variables. In local development they may also come
from ``backend/.env`` (git-ignored). In Docker, docker-compose injects them.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    app_name: str = "YouTube Clone API"
    api_prefix: str = "/api/v1"

    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = "postgresql+psycopg://youtube:youtube@localhost:5432/youtube"
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)

    redis_url: str = "redis://localhost:6379/0"

    # Only needed in development (Vite dev server). Production is same-origin behind nginx.
    cors_origins: list[str] = Field(default_factory=list)


@lru_cache
def get_settings() -> Settings:
    return Settings()
