"""View counting (acceptance D4), watch history and liked videos."""

from __future__ import annotations

from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.redis import get_redis
from app.main import app
from app.models import Video, VideoView
from app.models.enums import VideoStatus, Visibility
from tests.factories import auth_headers, create_user, create_video


def _ready(db: Session, **fields) -> Video:
    fields.setdefault("visibility", Visibility.PUBLIC)
    return create_video(db, create_user(db).channel, status=VideoStatus.READY, **fields)


def _views(db: Session, video: Video) -> tuple[int, int]:
    db.expire_all()
    rows = db.scalar(select(func.count()).where(VideoView.video_id == video.id)) or 0
    return db.get(Video, video.id).view_count, rows  # type: ignore[union-attr]


def test_a_viewer_is_counted_once_per_day(client: TestClient, db_session: Session) -> None:
    video = _ready(db_session)
    headers = auth_headers(create_user(db_session))

    first = client.post(f"/api/v1/videos/{video.id}/views", headers=headers)
    second = client.post(f"/api/v1/videos/{video.id}/views", headers=headers)

    assert first.json() == {"counted": True}
    assert second.json() == {"counted": False}
    assert _views(db_session, video) == (1, 1)


def test_different_viewers_are_counted_separately(client: TestClient, db_session: Session) -> None:
    video = _ready(db_session)
    for _ in range(3):
        client.post(
            f"/api/v1/videos/{video.id}/views", headers=auth_headers(create_user(db_session))
        )
    client.post(f"/api/v1/videos/{video.id}/views")  # anonymous, keyed by hashed IP
    client.post(f"/api/v1/videos/{video.id}/views")

    assert _views(db_session, video) == (4, 4)


def test_views_are_not_counted_when_dedupe_is_unavailable(
    client: TestClient, db_session: Session
) -> None:
    video = _ready(db_session)
    broken = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2, socket_timeout=0.2)
    app.dependency_overrides[get_redis] = lambda: broken

    response = client.post(f"/api/v1/videos/{video.id}/views")

    assert response.status_code in {202, 503}  # limiter may fail closed first
    assert _views(db_session, video) == (0, 0)


def test_private_video_views_are_404_for_strangers(client: TestClient, db_session: Session) -> None:
    video = _ready(db_session, visibility=Visibility.PRIVATE)

    assert client.post(f"/api/v1/videos/{video.id}/views").status_code == 404


def test_history_lists_watched_videos_newest_first(client: TestClient, db_session: Session) -> None:
    first, second = _ready(db_session, title="First"), _ready(db_session, title="Second")
    headers = auth_headers(create_user(db_session))
    client.post(f"/api/v1/videos/{first.id}/views", headers=headers)
    client.post(f"/api/v1/videos/{second.id}/views", headers=headers)

    history = client.get("/api/v1/me/history", headers=headers).json()

    assert [v["id"] for v in history] == [second.id, first.id]


def test_clearing_history_keeps_view_counts(client: TestClient, db_session: Session) -> None:
    video = _ready(db_session)
    headers = auth_headers(create_user(db_session))
    client.post(f"/api/v1/videos/{video.id}/views", headers=headers)

    assert client.delete("/api/v1/me/history", headers=headers).status_code == 204
    assert client.get("/api/v1/me/history", headers=headers).json() == []
    assert _views(db_session, video)[0] == 1


def test_liked_videos(client: TestClient, db_session: Session) -> None:
    liked, disliked = _ready(db_session), _ready(db_session)
    headers = auth_headers(create_user(db_session))
    client.put(f"/api/v1/videos/{liked.id}/reaction", json={"value": "like"}, headers=headers)
    client.put(f"/api/v1/videos/{disliked.id}/reaction", json={"value": "dislike"}, headers=headers)

    assert [v["id"] for v in client.get("/api/v1/me/liked", headers=headers).json()] == [liked.id]
