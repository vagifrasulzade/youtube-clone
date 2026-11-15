"""Likes / dislikes (acceptance D1): one per user, counters equal the rows."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Video, VideoReaction
from app.models.enums import VideoStatus, Visibility
from tests.factories import auth_headers, create_user, create_video


def _ready(db: Session, **fields):
    owner = create_user(db)
    fields.setdefault("visibility", Visibility.PUBLIC)
    return create_video(db, owner.channel, status=VideoStatus.READY, **fields)


def _assert_counters_match_rows(db: Session, video: Video) -> None:
    db.expire_all()
    fresh = db.get(Video, video.id)
    assert fresh is not None
    likes = db.scalar(
        select(func.count()).where(VideoReaction.video_id == video.id, VideoReaction.value == 1)
    )
    dislikes = db.scalar(
        select(func.count()).where(VideoReaction.video_id == video.id, VideoReaction.value == -1)
    )
    assert (fresh.like_count, fresh.dislike_count) == (likes, dislikes)


def test_like_then_switch_to_dislike_then_remove(client: TestClient, db_session: Session) -> None:
    video = _ready(db_session)
    headers = auth_headers(create_user(db_session))
    url = f"/api/v1/videos/{video.id}/reaction"

    liked = client.put(url, json={"value": "like"}, headers=headers)
    assert liked.json() == {"like_count": 1, "dislike_count": 0, "my_reaction": "like"}
    _assert_counters_match_rows(db_session, video)

    switched = client.put(url, json={"value": "dislike"}, headers=headers)
    assert switched.json() == {"like_count": 0, "dislike_count": 1, "my_reaction": "dislike"}
    _assert_counters_match_rows(db_session, video)

    removed = client.delete(url, headers=headers)
    assert removed.json() == {"like_count": 0, "dislike_count": 0, "my_reaction": None}
    _assert_counters_match_rows(db_session, video)


def test_repeating_a_like_is_idempotent(client: TestClient, db_session: Session) -> None:
    video = _ready(db_session)
    headers = auth_headers(create_user(db_session))
    url = f"/api/v1/videos/{video.id}/reaction"

    for _ in range(3):
        response = client.put(url, json={"value": "like"}, headers=headers)

    assert response.json()["like_count"] == 1
    _assert_counters_match_rows(db_session, video)


def test_counters_aggregate_many_users(client: TestClient, db_session: Session) -> None:
    video = _ready(db_session)
    url = f"/api/v1/videos/{video.id}/reaction"
    for value in ["like", "like", "like", "dislike"]:
        client.put(url, json={"value": value}, headers=auth_headers(create_user(db_session)))

    response = client.get(f"/api/v1/videos/{video.id}")

    assert (response.json()["like_count"], response.json()["dislike_count"]) == (3, 1)
    _assert_counters_match_rows(db_session, video)


def test_detail_shows_my_reaction(client: TestClient, db_session: Session) -> None:
    video = _ready(db_session)
    headers = auth_headers(create_user(db_session))
    client.put(f"/api/v1/videos/{video.id}/reaction", json={"value": "dislike"}, headers=headers)

    assert client.get(f"/api/v1/videos/{video.id}", headers=headers).json()["my_reaction"] == (
        "dislike"
    )


def test_reacting_requires_authentication(client: TestClient, db_session: Session) -> None:
    video = _ready(db_session)

    response = client.put(f"/api/v1/videos/{video.id}/reaction", json={"value": "like"})

    assert response.status_code == 401


def test_cannot_react_to_a_private_video_without_access(
    client: TestClient, db_session: Session
) -> None:
    video = _ready(db_session, visibility=Visibility.PRIVATE)

    response = client.put(
        f"/api/v1/videos/{video.id}/reaction",
        json={"value": "like"},
        headers=auth_headers(create_user(db_session)),
    )

    assert response.status_code == 404


def test_invalid_reaction_value_is_rejected(client: TestClient, db_session: Session) -> None:
    video = _ready(db_session)

    response = client.put(
        f"/api/v1/videos/{video.id}/reaction",
        json={"value": "love"},
        headers=auth_headers(create_user(db_session)),
    )

    assert response.status_code == 422
