"""Role guards: admin ⊇ moderator ⊇ user, enforced server-side from DB state."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import AdminUser, CurrentUser, ModeratorUser
from app.core.errors import register_exception_handlers
from app.db.session import get_db
from app.models.enums import ROLE_IDS, RoleName
from tests.factories import auth_headers, create_user


@pytest.fixture
def guarded_client(db_session: Session) -> Iterator[TestClient]:
    guarded = FastAPI()
    register_exception_handlers(guarded)

    @guarded.get("/user")
    def user_area(user: CurrentUser) -> dict[str, str]:
        return {"ok": user.role.name}

    @guarded.get("/moderation")
    def moderation_area(user: ModeratorUser) -> dict[str, str]:
        return {"ok": user.role.name}

    @guarded.get("/admin")
    def admin_area(user: AdminUser) -> dict[str, str]:
        return {"ok": user.role.name}

    guarded.dependency_overrides[get_db] = lambda: db_session
    with TestClient(guarded) as client:
        yield client


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (RoleName.USER, {"/user": 200, "/moderation": 403, "/admin": 403}),
        (RoleName.MODERATOR, {"/user": 200, "/moderation": 200, "/admin": 403}),
        (RoleName.ADMIN, {"/user": 200, "/moderation": 200, "/admin": 200}),
    ],
)
def test_role_hierarchy(
    guarded_client: TestClient,
    db_session: Session,
    role: RoleName,
    expected: dict[str, int],
) -> None:
    headers = auth_headers(create_user(db_session, role=role))

    actual = {path: guarded_client.get(path, headers=headers).status_code for path in expected}

    assert actual == expected


@pytest.mark.parametrize("path", ["/user", "/moderation", "/admin"])
def test_anonymous_is_rejected_everywhere(guarded_client: TestClient, path: str) -> None:
    assert guarded_client.get(path).status_code == 401


def test_demotion_applies_to_an_existing_token(
    guarded_client: TestClient, db_session: Session
) -> None:
    """The role comes from the database, not from the token."""
    moderator = create_user(db_session, role=RoleName.MODERATOR)
    headers = auth_headers(moderator)
    assert guarded_client.get("/moderation", headers=headers).status_code == 200

    moderator.role_id = ROLE_IDS[RoleName.USER]
    db_session.flush()
    db_session.expire(moderator)

    assert guarded_client.get("/moderation", headers=headers).status_code == 403
