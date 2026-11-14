"""Application settings.

Values come from environment variables. In local development they may also come
from ``backend/.env`` (git-ignored). In Docker, docker-compose injects them.
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Development-only defaults. Production refuses to start with any of these.
_DEV_JWT_SECRET = "dev-only-jwt-secret-change-me-0000000000000000"  # noqa: S105 - rejected in prod
_DEV_MEDIA_SECRET = "dev-only-media-secret-change-me-00000000000000"  # noqa: S105 - rejected in prod
_MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    app_name: str = "YouTube Clone API"
    api_prefix: str = "/api/v1"

    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = "postgresql+psycopg://youtube:youtube@127.0.0.1:5433/youtube"
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)

    redis_url: str = "redis://127.0.0.1:6380/0"

    # Only needed in development (Vite dev server). Production is same-origin behind nginx.
    cors_origins: list[str] = Field(default_factory=list)

    # --- auth ---
    jwt_secret: SecretStr = SecretStr(_DEV_JWT_SECRET)
    jwt_issuer: str = "youtube-clone"
    access_token_ttl_seconds: int = Field(default=15 * 60, ge=60)
    refresh_token_ttl_days: int = Field(default=30, ge=1)
    # A refresh token presented again within this window after rotation is treated as a
    # benign race (two tabs refreshing at once), not as token theft.
    refresh_reuse_grace_seconds: int = Field(default=10, ge=0)
    # Absolute lifetime of one login (token family), however often it is refreshed.
    refresh_family_max_age_days: int = Field(default=90, ge=1)
    refresh_cookie_name: str = "yt_refresh"
    # True when served over HTTPS. Browsers drop Secure cookies on plain-HTTP origins.
    cookie_secure: bool = False

    # Argon2id parameters (RFC 9106 "second recommended" profile by default).
    argon2_time_cost: int = Field(default=3, ge=1)
    argon2_memory_cost_kib: int = Field(default=64 * 1024, ge=8)
    argon2_parallelism: int = Field(default=4, ge=1)

    # Separate secret for media URLs (see docs/video-storage.md § 5).
    media_token_secret: SecretStr = SecretStr(_DEV_MEDIA_SECRET)

    rate_limit_enabled: bool = True

    @model_validator(mode="after")
    def _refuse_insecure_production(self) -> Self:
        if self.env != "production":
            return self
        for name, value, dev_default in (
            ("JWT_SECRET", self.jwt_secret, _DEV_JWT_SECRET),
            ("MEDIA_TOKEN_SECRET", self.media_token_secret, _DEV_MEDIA_SECRET),
        ):
            secret = value.get_secret_value()
            if secret == dev_default or len(secret) < _MIN_SECRET_LENGTH:
                raise ValueError(
                    f"{name} must be set to a random value of at least "
                    f"{_MIN_SECRET_LENGTH} characters in production"
                )
        if self.jwt_secret.get_secret_value() == self.media_token_secret.get_secret_value():
            raise ValueError("JWT_SECRET and MEDIA_TOKEN_SECRET must differ")
        if not self.rate_limit_enabled:
            raise ValueError("RATE_LIMIT_ENABLED cannot be disabled in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
