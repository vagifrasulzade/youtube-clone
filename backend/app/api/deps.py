"""Shared FastAPI dependencies: database, Redis, authentication and roles."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis import Redis
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.redis import get_redis
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User
from app.models.enums import ROLE_LEVELS, RoleName

DbSession = Annotated[Session, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis)]

# auto_error=False: we raise our own 401 envelope; also adds "Authorize" to Swagger UI.
_bearer = HTTPBearer(auto_error=False, description="Access token from /auth/login")


def get_optional_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User | None:
    """The caller, or None when anonymous.

    A *present but invalid/expired* token is a 401 (the client should refresh), never
    a silent downgrade to anonymous. Role and ban status are read from the database on
    every request, so a ban or role change takes effect immediately.
    """
    if credentials is None:
        return None
    user_id = decode_access_token(credentials.credentials)
    user = db.get(User, user_id)
    if user is None:
        raise UnauthorizedError("Invalid access token", code="invalid_token")
    if user.is_banned:
        raise ForbiddenError("This account has been suspended", code="account_banned")
    return user


def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise UnauthorizedError()
    return user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def has_role(user: User, minimum: RoleName) -> bool:
    return user.role.level >= ROLE_LEVELS[minimum]


def require_role(minimum: RoleName) -> Callable[[User], User]:
    def dependency(user: CurrentUser) -> User:
        if not has_role(user, minimum):
            raise ForbiddenError(f"Requires {minimum.value} role", code="insufficient_role")
        return user

    return dependency


ModeratorUser = Annotated[User, Depends(require_role(RoleName.MODERATOR))]
AdminUser = Annotated[User, Depends(require_role(RoleName.ADMIN))]
