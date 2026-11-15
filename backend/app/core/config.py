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
    # Binds media URLs to the browser that obtained them (security review M1).
    media_cookie_name: str = "yt_media"
    # True when served over HTTPS. Browsers drop Secure cookies on plain-HTTP origins.
    cookie_secure: bool = False

    # Argon2id parameters (RFC 9106 "second recommended" profile by default).
    argon2_time_cost: int = Field(default=3, ge=1)
    argon2_memory_cost_kib: int = Field(default=64 * 1024, ge=8)
    argon2_parallelism: int = Field(default=4, ge=1)

    # Separate secret for media URLs (see docs/video-storage.md § 5).
    media_token_secret: SecretStr = SecretStr(_DEV_MEDIA_SECRET)

    rate_limit_enabled: bool = True

    # --- object storage (MinIO, S3 API) ---
    # Internal endpoint used by the API and worker (never shown to clients).
    s3_endpoint_url: str = "http://127.0.0.1:9000"
    s3_region: str = "us-east-1"
    s3_access_key: SecretStr = SecretStr("")
    s3_secret_key: SecretStr = SecretStr("")
    uploads_bucket: str = "yt-uploads"
    media_bucket: str = "yt-media"
    # Where the browser POSTs uploads. Production: same-origin path proxied by nginx.
    # The POST policy signature does not cover the URL, so this can differ from the
    # internal endpoint.
    s3_public_upload_url: str = "/storage/upload"

    # --- upload limits (docs/video-storage.md § 6) ---
    max_upload_bytes: int = Field(default=2 * 1024**3, ge=1024)
    max_video_duration_seconds: int = Field(default=2 * 3600, ge=1)
    upload_policy_ttl_seconds: int = Field(default=2 * 3600, ge=60)
    max_avatar_bytes: int = Field(default=2 * 1024**2, ge=1024)
    max_banner_bytes: int = Field(default=6 * 1024**2, ge=1024)
    max_thumbnail_bytes: int = Field(default=2 * 1024**2, ge=1024)

    # --- video processing (docs/video-storage.md § 4) ---
    # Parent directory of the worker's per-task temp dirs (None: the system default).
    # Production uses a disk-backed volume: a tmpfs would count against the worker's
    # memory limit, and a 2 GiB upload plus its output would not fit.
    processing_workdir: str | None = None
    processing_timeout_seconds: int = Field(default=25 * 60, ge=10)  # < 30 min soft limit

    # --- media delivery (docs/video-storage.md § 5) ---
    # accel: FastAPI authorizes, nginx streams from MinIO (X-Accel-Redirect) - production.
    # proxy: FastAPI streams from MinIO itself (dev/tests without nginx). Same authz path.
    media_delivery: Literal["accel", "proxy"] = "proxy"
    media_token_ttl_seconds: int = Field(default=4 * 3600, ge=60)
    internal_presign_ttl_seconds: int = Field(default=60, ge=5)

    # api: serves HTTP and signs tokens. worker: processes media and must NOT hold the
    # token secrets, so a compromised ffmpeg cannot forge sessions (security review M2).
    process_role: Literal["api", "worker"] = "api"

    # Password of the demo accounts created by `python -m app.cli.seed`. deploy.sh
    # generates a random one; in production the seed refuses to run without it (H1).
    demo_password: SecretStr | None = None

    @model_validator(mode="after")
    def _refuse_insecure_production(self) -> Self:
        if self.env != "production":
            return self
        storage_secret = self.s3_secret_key.get_secret_value()
        if not storage_secret or storage_secret.startswith("change-me"):
            raise ValueError("S3_SECRET_KEY must be set to a real value in production")
        if not self.rate_limit_enabled:
            raise ValueError("RATE_LIMIT_ENABLED cannot be disabled in production")
        if self.process_role == "worker":
            return self  # token secrets are deliberately absent from the worker
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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
