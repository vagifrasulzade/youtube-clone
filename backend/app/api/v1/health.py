"""Liveness and readiness probes (used by Docker health checks and deploy.sh)."""

import logging
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import DbSession, RedisClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["health"])

CheckResult = Literal["ok", "error"]


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, CheckResult]


@router.get("/live", summary="Process is up")
def live() -> LivenessResponse:
    return LivenessResponse()


@router.get(
    "/ready",
    summary="Dependencies are reachable",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
def ready(db: DbSession, redis: RedisClient, response: Response) -> ReadinessResponse:
    checks: dict[str, CheckResult] = {}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except SQLAlchemyError:
        logger.warning("Readiness: database check failed", exc_info=True)
        checks["database"] = "error"

    try:
        redis.ping()
        checks["redis"] = "ok"
    except RedisError:
        logger.warning("Readiness: redis check failed", exc_info=True)
        checks["redis"] = "error"

    healthy = all(result == "ok" for result in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ok" if healthy else "degraded", checks=checks)
