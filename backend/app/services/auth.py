"""Registration, login and the refresh-token session lifecycle.

Session model (docs/security.md § 2):
- Login issues a short-lived access JWT plus an opaque refresh token. Only the token's
  SHA-256 is stored; tokens of one login form a *family*.
- Every refresh rotates the token. Presenting an already-rotated token after the grace
  window means it was stolen or replayed, so the whole family is revoked.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BadRequestError, ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import (
    burn_password_check,
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.models import Channel, RefreshToken, User

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "invalid_credentials"


@dataclass(frozen=True)
class IssuedSession:
    user: User
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_token_id: uuid.UUID
    refresh_expires_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


def _banned_error() -> ForbiddenError:
    return ForbiddenError("This account has been suspended", code="account_banned")


# --- registration & login -----------------------------------------------------


def register(db: Session, *, email: str, password: str, handle: str, display_name: str) -> User:
    """Create a user and their channel. Email/handle arrive normalized (lowercase)."""
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise ConflictError("An account with this email already exists", code="email_taken")
    if db.scalar(select(Channel.id).where(Channel.handle == handle)) is not None:
        raise ConflictError("This handle is already taken", code="handle_taken")

    user = User(email=email, password_hash=hash_password(password))
    user.channel = Channel(handle=handle, name=display_name)
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:  # concurrent registration with the same email/handle
        db.rollback()
        raise ConflictError("Email or handle already taken", code="account_exists") from exc
    db.refresh(user)
    logger.info("User registered", extra={"user_id": str(user.id)})
    return user


def authenticate(db: Session, *, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        burn_password_check(password)  # same timing as a wrong password: no enumeration
        raise UnauthorizedError("Incorrect email or password", code=INVALID_CREDENTIALS)
    if not verify_password(user.password_hash, password):
        raise UnauthorizedError("Incorrect email or password", code=INVALID_CREDENTIALS)
    if user.is_banned:
        raise _banned_error()

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = _now()
    return user


# --- sessions -----------------------------------------------------------------


def _store_refresh_token(
    db: Session, user_id: uuid.UUID, family_id: uuid.UUID, user_agent: str | None
) -> tuple[RefreshToken, str]:
    raw = new_refresh_token()
    row = RefreshToken(
        user_id=user_id,
        family_id=family_id,
        token_hash=hash_token(raw),
        expires_at=_now() + timedelta(days=get_settings().refresh_token_ttl_days),
        user_agent=(user_agent or "")[:300] or None,
    )
    db.add(row)
    db.flush()
    return row, raw


def issue_session(
    db: Session, user: User, *, user_agent: str | None, family_id: uuid.UUID | None = None
) -> IssuedSession:
    row, raw = _store_refresh_token(db, user.id, family_id or uuid.uuid4(), user_agent)
    access_token, expires_in = create_access_token(user.id)
    return IssuedSession(
        user=user,
        access_token=access_token,
        expires_in=expires_in,
        refresh_token=raw,
        refresh_token_id=row.id,
        refresh_expires_at=row.expires_at,
    )


def revoke_family(db: Session, family_id: uuid.UUID) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


def revoke_all_sessions(db: Session, user_id: uuid.UUID) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


def rotate_session(db: Session, raw_token: str, *, user_agent: str | None) -> IssuedSession:
    invalid = UnauthorizedError("Session expired, please sign in again", code="invalid_refresh")
    row = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw_token))
        .with_for_update()  # serializes concurrent refreshes of the same token
    )
    if row is None:
        raise invalid

    now = _now()
    if row.revoked_at is not None:
        grace = timedelta(seconds=get_settings().refresh_reuse_grace_seconds)
        if row.replaced_by_id is not None and now - row.revoked_at <= grace:
            # Another tab rotated this token a moment ago; the browser already holds the
            # new cookie. Not an attack: reject without revoking the family.
            raise UnauthorizedError("Session was just refreshed", code="refresh_superseded")
        logger.warning(
            "Refresh token reuse detected; revoking session family",
            extra={"user_id": str(row.user_id), "family_id": str(row.family_id)},
        )
        revoke_family(db, row.family_id)
        db.commit()
        raise invalid
    if row.expires_at <= now:
        raise invalid

    user = db.get(User, row.user_id)
    if user is None:
        raise invalid
    if user.is_banned:
        revoke_family(db, row.family_id)
        db.commit()
        raise _banned_error()

    session = issue_session(db, user, user_agent=user_agent, family_id=row.family_id)
    row.revoked_at = now
    row.replaced_by_id = session.refresh_token_id
    return session


def logout(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if row is not None:
        revoke_family(db, row.family_id)


def change_password(db: Session, user: User, *, current_password: str, new_password: str) -> None:
    if not verify_password(user.password_hash, current_password):
        raise BadRequestError("Current password is incorrect", code="wrong_password")
    if verify_password(user.password_hash, new_password):
        raise BadRequestError("New password must differ from the current one", code="same_password")
    user.password_hash = hash_password(new_password)
    revoke_all_sessions(db, user.id)
