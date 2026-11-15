"""Reports, hide/restore and the audit log (acceptance C5, E4)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ModerationAction, Video
from app.models.enums import RoleName, VideoStatus, Visibility
from tests.factories import auth_headers, create_user, create_video


@pytest.fixture
def video(db_session: Session) -> Video:
    owner = create_user(db_session)
    return create_video(
        db_session, owner.channel, status=VideoStatus.READY, visibility=Visibility.PUBLIC
    )


@pytest.fixture
def moderator(db_session: Session):
    return auth_headers(create_user(db_session, role=RoleName.MODERATOR))


def _report(client: TestClient, video_id: str, headers: dict, reason: str = "spam"):
    return client.post(
        f"/api/v1/videos/{video_id}/reports",
        json={"reason": reason, "details": "Link farm"},
        headers=headers,
    )


def _actions(db: Session) -> list[str]:
    return [
        a.action.value for a in db.scalars(select(ModerationAction).order_by(ModerationAction.id))
    ]


def test_user_reports_a_video_once(client: TestClient, db_session: Session, video) -> None:
    reporter = auth_headers(create_user(db_session))

    first = _report(client, video.id, reporter)
    second = _report(client, video.id, reporter, reason="other")

    assert first.status_code == 201
    assert first.json()["status"] == "open"
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "already_reported"


def test_reporting_requires_login_and_visibility(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session)
    private = create_video(
        db_session, owner.channel, status=VideoStatus.READY, visibility=Visibility.PRIVATE
    )

    assert _report(client, private.id, {}).status_code == 401
    assert _report(client, private.id, auth_headers(create_user(db_session))).status_code == 404


def test_invalid_reason_is_rejected(client: TestClient, db_session: Session, video) -> None:
    response = _report(client, video.id, auth_headers(create_user(db_session)), reason="meh")

    assert response.status_code == 422


def test_regular_users_cannot_moderate(client: TestClient, db_session: Session, video) -> None:
    """E4"""
    user = auth_headers(create_user(db_session))
    report_id = _report(client, video.id, user).json()["id"]
    note = {"note": "x"}

    assert client.get("/api/v1/moderation/reports", headers=user).status_code == 403
    assert (
        client.post(
            f"/api/v1/moderation/videos/{video.id}/hide", json=note, headers=user
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/moderation/reports/{report_id}/dismiss", json=note, headers=user
        ).status_code
        == 403
    )
    assert client.get("/api/v1/moderation/actions").status_code == 401


def test_resolve_with_hide_hides_video_and_closes_all_its_reports(
    client: TestClient, db_session: Session, video, moderator
) -> None:
    first = _report(client, video.id, auth_headers(create_user(db_session))).json()
    second = _report(client, video.id, auth_headers(create_user(db_session))).json()

    response = client.post(
        f"/api/v1/moderation/reports/{first['id']}/resolve",
        json={"hide_video": True, "note": "Spam confirmed"},
        headers=moderator,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "resolved"
    queue = client.get("/api/v1/moderation/reports", headers=moderator).json()
    assert second["id"] not in {r["id"] for r in queue["items"]}
    # C5: hidden for the public, still visible to the owner's Studio and staff
    assert client.get(f"/api/v1/videos/{video.id}").status_code == 404
    assert client.get(f"/api/v1/videos/{video.id}", headers=moderator).status_code == 200
    assert _actions(db_session) == ["resolve_report", "hide_video"]


def test_closed_report_cannot_be_closed_again(
    client: TestClient, db_session: Session, video, moderator
) -> None:
    report = _report(client, video.id, auth_headers(create_user(db_session))).json()
    url = f"/api/v1/moderation/reports/{report['id']}"
    client.post(f"{url}/dismiss", json={"note": "Not spam"}, headers=moderator)

    again = client.post(f"{url}/resolve", json={"note": "x"}, headers=moderator)

    assert again.status_code == 409


def test_hide_and_restore_are_audited(
    client: TestClient, db_session: Session, video, moderator
) -> None:
    hide = client.post(
        f"/api/v1/moderation/videos/{video.id}/hide", json={"note": "Violence"}, headers=moderator
    )
    hidden_feed = client.get("/api/v1/videos").json()["items"]
    restore = client.post(
        f"/api/v1/moderation/videos/{video.id}/restore",
        json={"note": "Appeal ok"},
        headers=moderator,
    )

    assert hide.json()["is_hidden"] is True
    assert video.id not in {v["id"] for v in hidden_feed}
    assert restore.json()["is_hidden"] is False
    log = client.get("/api/v1/moderation/actions", headers=moderator).json()["items"]
    assert [a["action"] for a in log[:2]] == ["restore_video", "hide_video"]
    assert log[1]["details"]["title"] == video.title  # snapshot survives later deletion
    assert log[1]["reason"] == "Violence"


def test_admin_can_moderate_too(client: TestClient, db_session: Session, video) -> None:
    admin = auth_headers(create_user(db_session, role=RoleName.ADMIN))

    response = client.post(
        f"/api/v1/moderation/videos/{video.id}/hide", json={"note": "x"}, headers=admin
    )

    assert response.status_code == 200
