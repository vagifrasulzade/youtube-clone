"""Application errors and the uniform JSON error envelope.

Every error response has the shape::

    {"error": {"code": "<machine_code>", "message": "<human text>", "details": <any|null>}}
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for errors that are part of the API contract."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "Bad request"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details
        self.headers = headers
        super().__init__(self.message)


class BadRequestError(AppError):
    pass


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "not_authenticated"
    message = "Authentication required"

    def __init__(self, message: str | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("headers", {"WWW-Authenticate": "Bearer"})
        super().__init__(message, **kwargs)


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    message = "You do not have permission to perform this action"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "Resource not found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "Conflict with the current state of the resource"


class PayloadTooLargeError(AppError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "payload_too_large"
    message = "Payload too large"


class UnsupportedMediaError(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "unsupported_media_type"
    message = "Unsupported file type"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    message = "Too many requests, try again later"

    def __init__(self, retry_after: int, message: str | None = None) -> None:
        super().__init__(message, headers={"Retry-After": str(retry_after)})


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"
    message = "Service temporarily unavailable"


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


_HTTP_CODES = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "not_authenticated",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
}


async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, exc.details),
        headers=exc.headers,
    )


async def _validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Only location, message and type: never echo the submitted input (may contain passwords).
    details = [
        {
            "loc": list(err.get("loc", ())),
            "message": err.get("msg", ""),
            "type": err.get("type", ""),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=error_body("validation_error", "Request validation failed", details),
    )


async def _http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(_HTTP_CODES.get(exc.status_code, "http_error"), message),
        headers=getattr(exc, "headers", None),
    )


async def _unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_body("internal_error", "Internal server error"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    # Starlette dispatches by exception class, so each handler receives its own type.
    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_error_handler)
