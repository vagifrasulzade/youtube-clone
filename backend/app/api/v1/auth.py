"""Authentication endpoints. Business logic lives in app.services.auth."""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import CurrentUser, DbSession, RedisClient
from app.core import rate_limit
from app.core.config import get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.schemas.auth import ChangePasswordRequest, LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import CurrentUserOut
from app.services import auth as auth_service
from app.services.auth import IssuedSession

router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie_path() -> str:
    return f"{get_settings().api_prefix}/auth"


def _set_refresh_cookie(response: Response, session: IssuedSession) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=session.refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=_cookie_path(),
    )


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=_cookie_path(),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _refresh_cookie(request: Request) -> str | None:
    return request.cookies.get(get_settings().refresh_cookie_name)


def _check_origin(request: Request) -> None:
    """Defense in depth for cookie-authenticated endpoints (SameSite=Strict is the first
    layer): a browser request from another origin is rejected."""
    origin = request.headers.get("origin")
    if origin is None:
        return
    if origin in get_settings().cors_origins:
        return
    if urlsplit(origin).netloc == request.headers.get("host"):
        return
    raise ForbiddenError("Cross-site request rejected", code="bad_origin")


def _token_response(session: IssuedSession) -> TokenResponse:
    return TokenResponse(
        access_token=session.access_token,
        expires_in=session.expires_in,
        user=CurrentUserOut.from_model(session.user),
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Create an account (and its channel) and sign in",
    dependencies=[Depends(rate_limit.limit_by_ip("register", limit=5, window_seconds=3600))],
)
def register(
    body: RegisterRequest, request: Request, response: Response, db: DbSession
) -> TokenResponse:
    user = auth_service.register(
        db,
        email=body.email,
        password=body.password,
        handle=body.handle,
        display_name=body.display_name,
    )
    session = auth_service.issue_session(db, user, user_agent=request.headers.get("user-agent"))
    db.commit()
    _set_refresh_cookie(response, session)
    return _token_response(session)


@router.post(
    "/login",
    summary="Sign in with email and password",
    dependencies=[Depends(rate_limit.limit_by_ip("login", limit=10, window_seconds=60))],
)
def login(
    body: LoginRequest, request: Request, response: Response, db: DbSession, redis: RedisClient
) -> TokenResponse:
    # Per-account limit as well as per-IP: stops slow distributed guessing of one account.
    rate_limit.hit(
        redis, f"login:email:{rate_limit.hashed(body.email)}", limit=5, window_seconds=60
    )
    user = auth_service.authenticate(db, email=body.email, password=body.password)
    session = auth_service.issue_session(db, user, user_agent=request.headers.get("user-agent"))
    db.commit()
    _set_refresh_cookie(response, session)
    return _token_response(session)


@router.post(
    "/refresh",
    summary="Rotate the refresh cookie and get a new access token",
    dependencies=[Depends(rate_limit.limit_by_ip("refresh", limit=30, window_seconds=60))],
)
def refresh(request: Request, response: Response, db: DbSession) -> TokenResponse:
    _check_origin(request)
    raw = _refresh_cookie(request)
    if not raw:
        raise UnauthorizedError("Not signed in", code="invalid_refresh")
    session = auth_service.rotate_session(db, raw, user_agent=request.headers.get("user-agent"))
    db.commit()
    _set_refresh_cookie(response, session)
    return _token_response(session)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="End this session")
def logout(request: Request, db: DbSession) -> Response:
    _check_origin(request)
    auth_service.logout(db, _refresh_cookie(request))
    db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(response)
    return response


@router.get("/me", summary="The signed-in user")
def me(user: CurrentUser) -> CurrentUserOut:
    return CurrentUserOut.from_model(user)


@router.post(
    "/change-password",
    summary="Change password; signs out every other session",
    dependencies=[
        Depends(rate_limit.limit_by_ip("change-password", limit=10, window_seconds=3600))
    ],
)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: CurrentUser,
    db: DbSession,
) -> TokenResponse:
    auth_service.change_password(
        db, user, current_password=body.current_password, new_password=body.new_password
    )
    session = auth_service.issue_session(db, user, user_agent=request.headers.get("user-agent"))
    db.commit()
    _set_refresh_cookie(response, session)
    return _token_response(session)
