"""Admin dashboard API and its guardrails (acceptance E3, E4)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models import ModerationAction, User
from app.models.enums import ROLE_IDS, RoleName, VideoStatus, Visibility
from app.services import admin as admin_service
from tests.factories import auth_headers, create_user, create_video


@pytest.fixture
def admin(db_session: Session) -> User:
    return create_user(db_session, role=RoleName.ADMIN)


def _role(client: TestClient, actor: User, target: User, role: str):
    return client.patch(
        f"/api/v1/admin/users/{target.id}/role", json={"role": role}, headers=auth_headers(actor)
    )


def _ban(client: TestClient, actor: User, target: User):
    return client.post(
        f"/api/v1/admin/users/{target.id}/ban",
        json={"reason": "abuse"},
        headers=auth_headers(actor),
    )


@pytest.mark.parametrize("role", [RoleName.USER, RoleName.MODERATOR])
def test_non_admins_get_403_on_every_admin_route(
    client: TestClient, db_session: Session, role: RoleName
) -> None:
    headers = auth_headers(create_user(db_session, role=role))
    target = create_user(db_session)

    assert client.get("/api/v1/admin/stats", headers=headers).status_code == 403
    assert client.get("/api/v1/admin/users", headers=headers).status_code == 403
    assert client.get("/api/v1/admin/videos", headers=headers).status_code == 403
    assert (
        client.patch(
            f"/api/v1/admin/users/{target.id}/role", json={"role": "admin"}, headers=headers
        ).status_code
        == 403
    )


def test_stats(client: TestClient, db_session: Session, admin: User) -> None:
    create_video(db_session, admin.channel, status=VideoStatus.READY, view_count=7)

    body = client.get("/api/v1/admin/stats", headers=auth_headers(admin)).json()

    assert body["users"] >= 1
    assert body["videos_by_status"]["ready"] >= 1
    assert body["views_total"] >= 7
    assert set(body) >= {"open_reports", "storage_bytes", "signups_7d", "banned_users"}


def test_admin_promotes_and_demotes_with_audit(
    client: TestClient, db_session: Session, admin: User
) -> None:
    target = create_user(db_session)

    promoted = _role(client, admin, target, "moderator")
    demoted = _role(client, admin, target, "user")

    assert promoted.json()["role"] == "moderator"
    assert demoted.json()["role"] == "user"
    log = db_session.scalars(select(ModerationAction).order_by(ModerationAction.id)).all()
    assert [(a.details["old_role"], a.details["new_role"]) for a in log] == [
        ("user", "moderator"),
        ("moderator", "user"),
    ]


def test_admin_cannot_change_own_role(client: TestClient, admin: User) -> None:
    response = _role(client, admin, admin, "user")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "self_role_change"


def test_one_admin_may_demote_another_while_two_exist(
    client: TestClient, db_session: Session, admin: User
) -> None:
    other = create_user(db_session, role=RoleName.ADMIN)

    assert _role(client, admin, other, "user").status_code == 200


def test_last_admin_cannot_be_demoted(db_session: Session, admin: User) -> None:
    """Defense in depth below the API's self-check: the service refuses to remove the
    final admin whoever asks (e.g. a racing demotion)."""
    db_session.execute(
        update(User)
        .where(User.id != admin.id, User.role_id == ROLE_IDS[RoleName.ADMIN])
        .values(role_id=ROLE_IDS[RoleName.USER])
    )
    actor = create_user(db_session, role=RoleName.MODERATOR)

    with pytest.raises(ConflictError) as exc_info:
        admin_service.change_role(db_session, actor, admin.id, RoleName.USER)

    assert exc_info.value.code == "last_admin"


def test_ban_locks_the_user_out_immediately(
    client: TestClient, db_session: Session, admin: User
) -> None:
    """E3"""
    target = create_user(db_session)
    target_headers = auth_headers(target)
    assert client.get("/api/v1/auth/me", headers=target_headers).status_code == 200

    banned = _ban(client, admin, target)

    assert banned.status_code == 200
    assert banned.json()["banned_at"] is not None
    assert client.get("/api/v1/auth/me", headers=target_headers).status_code == 403
    unbanned = client.post(
        f"/api/v1/admin/users/{target.id}/unban",
        json={"note": "appeal"},
        headers=auth_headers(admin),
    )
    assert unbanned.json()["banned_at"] is None
    assert client.get("/api/v1/auth/me", headers=target_headers).status_code == 200


def test_ban_guardrails(client: TestClient, db_session: Session, admin: User) -> None:
    other_admin = create_user(db_session, role=RoleName.ADMIN)

    assert _ban(client, admin, admin).json()["error"]["code"] == "self_ban"
    assert _ban(client, admin, other_admin).json()["error"]["code"] == "ban_admin"


def test_user_search_and_filters(client: TestClient, db_session: Session, admin: User) -> None:
    findme = create_user(db_session, email="findme@example.com")
    headers = auth_headers(admin)

    by_email = client.get("/api/v1/admin/users", params={"q": "findme"}, headers=headers).json()
    by_handle = client.get(
        "/api/v1/admin/users", params={"q": findme.channel.handle}, headers=headers
    ).json()

    assert [u["id"] for u in by_email["items"]] == [str(findme.id)]
    assert [u["id"] for u in by_handle["items"]] == [str(findme.id)]


def test_admin_video_list_includes_every_state(
    client: TestClient, db_session: Session, admin: User
) -> None:
    owner = create_user(db_session)
    private = create_video(
        db_session, owner.channel, title="Admin sees me", visibility=Visibility.PRIVATE
    )

    body = client.get(
        "/api/v1/admin/videos", params={"q": "Admin sees"}, headers=auth_headers(admin)
    ).json()

    assert [v["id"] for v in body["items"]] == [private.id]


def test_admin_deleting_someone_elses_video_is_audited(
    client: TestClient, db_session: Session, admin: User
) -> None:
    video = create_video(db_session, create_user(db_session).channel, status=VideoStatus.READY)

    response = client.delete(f"/api/v1/videos/{video.id}", headers=auth_headers(admin))

    assert response.status_code == 204
    action = db_session.scalars(select(ModerationAction)).one()
    assert action.action.value == "delete_video"
    assert action.details["title"] == video.title


def test_the_api_cannot_create_admins(client: TestClient, db_session: Session, admin: User) -> None:
    """Review L3: admins come from the server-side CLI only."""
    target = create_user(db_session)

    response = _role(client, admin, target, "admin")

    assert response.status_code == 422


def test_create_admin_cli_promotes_an_existing_account(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import nullcontext

    from app.cli import create_admin

    target = create_user(db_session, email="future-admin@example.com")
    monkeypatch.setattr(create_admin, "get_sessionmaker", lambda: lambda: nullcontext(db_session))

    def no_prompt() -> str:
        raise AssertionError("an existing account must not be asked for a password")

    assert create_admin.main(["Future-Admin@example.com"], reader=no_prompt) == 0
    db_session.refresh(target)
    assert target.role.name == RoleName.ADMIN
    # A new email without a password (cancelled / mismatched entries): nothing is created.
    assert create_admin.main(["nobody@example.com"], reader=lambda: None) == 1
    assert db_session.scalar(select(User).where(User.email == "nobody@example.com")) is None


def test_audit_log_never_stores_email_addresses(
    client: TestClient, db_session: Session, admin: User
) -> None:
    """Review L2: moderators can read the audit log, so it keeps handles, not emails."""
    target = create_user(db_session, email="private-person@example.com")
    _ban(client, admin, target)
    _role(client, admin, create_user(db_session), "moderator")

    details = [str(a.details) for a in db_session.scalars(select(ModerationAction))]

    assert details
    assert all("@" not in d for d in details)


def test_create_admin_cli_creates_a_new_admin_with_a_password(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import nullcontext

    from app.cli import create_admin
    from app.core.security import verify_password

    monkeypatch.setattr(create_admin, "get_sessionmaker", lambda: lambda: nullcontext(db_session))
    create_user(db_session, handle="newboss")  # the default handle is taken: a number is added

    assert create_admin.main(["NewBoss@Example.com"], reader=lambda: "strong-pass-123") == 0

    user = db_session.scalar(select(User).where(User.email == "newboss@example.com"))
    assert user is not None
    assert user.role.name == RoleName.ADMIN
    assert user.channel.handle == "newboss2"
    assert verify_password(user.password_hash, "strong-pass-123")


def test_create_admin_cli_accepts_a_handle_and_enforces_the_rules(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import nullcontext

    from app.cli import create_admin

    monkeypatch.setattr(create_admin, "get_sessionmaker", lambda: lambda: nullcontext(db_session))

    assert (
        create_admin.main(["boss@example.com", "@TheBoss"], reader=lambda: "strong-pass-123") == 0
    )
    boss = db_session.scalar(select(User).where(User.email == "boss@example.com"))
    assert boss is not None
    assert boss.channel.handle == "theboss"

    for argv, password in [
        (["weak@example.com"], "short"),  # under 8 characters
        (["same@example.com"], "same@example.com"),  # equals the email
        (["bad@example.com", "no spaces!"], "strong-pass-123"),  # invalid handle
        (["not-an-email"], "strong-pass-123"),
        (["taken@example.com", "theboss"], "strong-pass-123"),  # handle already used
    ]:
        assert create_admin.main(argv, reader=lambda p=password: p) == 1, argv
        email = argv[0]
        assert db_session.scalar(select(User).where(User.email == email)) is None
    assert create_admin.main([]) == 2
