"""Signed media tokens for <video>/<img> URLs (docs/video-storage.md § 5).

Media elements cannot send an Authorization header, so media URLs carry a short-lived
token that IDENTIFIES the viewer. It grants nothing by itself: every media request
re-runs the access policy against the database, so revoking a grant or hiding a
video takes effect on the very next request (acceptance C4).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import UnauthorizedError
from app.models import User

MEDIA_TOKEN_TYPE = "media"  # noqa: S105 - token type claim, not a secret
MEDIA_SESSION_TYPE = "media_session"
_ALGORITHM = "HS256"


def create_media_token(video_id: str, user_id: uuid.UUID | None) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "typ": MEDIA_TOKEN_TYPE,
        "vid": video_id,
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.media_token_ttl_seconds)).timestamp()),
    }
    if user_id is not None:
        payload["sub"] = str(user_id)
    return jwt.encode(payload, settings.media_token_secret.get_secret_value(), _ALGORITHM)


def create_media_session(user_id: uuid.UUID, expires_at: datetime) -> str:
    """Value of the HttpOnly media cookie set at sign-in/refresh (path: the media API).

    A media URL that names a user only acts for that user when this browser also holds
    that user's media cookie, so a copied link does not unlock private videos for
    whoever receives it (security review M1).
    """
    settings = get_settings()
    payload = {
        "typ": MEDIA_SESSION_TYPE,
        "sub": str(user_id),
        "iss": settings.jwt_issuer,
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.media_token_secret.get_secret_value(), _ALGORITHM)


def _media_session_user_id(cookie: str | None) -> str | None:
    if not cookie:
        return None
    settings = get_settings()
    try:
        payload = jwt.decode(
            cookie,
            settings.media_token_secret.get_secret_value(),
            algorithms=[_ALGORITHM],
            issuer=settings.jwt_issuer,
            options={"require": ["typ", "sub", "iss", "exp"]},
        )
    except jwt.PyJWTError:
        return None
    return str(payload["sub"]) if payload.get("typ") == MEDIA_SESSION_TYPE else None


def viewer_from_media_token(
    db: Session, token: str | None, video_id: str, session_cookie: str | None = None
) -> User | None:
    """The viewer a media token identifies (None = anonymous).

    A token minted for a user counts only together with that user's media cookie;
    otherwise the request is treated as anonymous (public videos still play).
    """
    if not token:
        return None
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.media_token_secret.get_secret_value(),
            algorithms=[_ALGORITHM],
            issuer=settings.jwt_issuer,
            options={"require": ["typ", "vid", "iss", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Media link expired", code="media_token_expired") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid media link", code="invalid_media_token") from exc

    if payload.get("typ") != MEDIA_TOKEN_TYPE or payload.get("vid") != video_id:
        raise UnauthorizedError("Invalid media link", code="invalid_media_token")
    subject = payload.get("sub")
    if subject is None or _media_session_user_id(session_cookie) != str(subject):
        return None
    try:
        user = db.get(User, uuid.UUID(str(subject)))
    except ValueError as exc:
        raise UnauthorizedError("Invalid media link", code="invalid_media_token") from exc
    if user is None or user.is_banned:
        return None  # no special rights; the access policy decides as for anonymous
    return user
