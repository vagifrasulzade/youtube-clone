"""Fixed-window rate limiting on Redis (INCR + EXPIRE).

Used on sensitive endpoints (login, register, refresh, uploads, comments, reports,
search). If Redis is unavailable the request fails with 503: auth endpoints must
not silently run without brute-force protection.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.errors import RateLimitedError, ServiceUnavailableError
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


def hit(redis: Redis, key: str, *, limit: int, window_seconds: int) -> None:
    """Count one request for `key`; raise RateLimitedError when over `limit` per window."""
    if not get_settings().rate_limit_enabled:
        return
    now = time.time()
    bucket = int(now // window_seconds)
    redis_key = f"rl:{key}:{bucket}"
    try:
        pipe = redis.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds)
        count, _ = pipe.execute()
    except RedisError as exc:
        logger.error("Rate limiter unavailable", exc_info=True)
        raise ServiceUnavailableError() from exc
    if int(count) > limit:
        retry_after = max(1, math.ceil((bucket + 1) * window_seconds - now))
        raise RateLimitedError(retry_after=retry_after)


def client_ip(request: Request) -> str:
    # uvicorn runs with --proxy-headers behind nginx, so this is the real client IP.
    return request.client.host if request.client else "unknown"


def hashed(value: str) -> str:
    """Keys derived from user input (e.g. email) are hashed: no PII in Redis keys."""
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def limit_by_ip(scope: str, *, limit: int, window_seconds: int) -> Callable[..., None]:
    """FastAPI dependency factory: `dependencies=[Depends(limit_by_ip("login", ...))]`."""

    def dependency(request: Request, redis: Annotated[Redis, Depends(get_redis)]) -> None:
        hit(redis, f"{scope}:ip:{client_ip(request)}", limit=limit, window_seconds=window_seconds)

    return dependency
