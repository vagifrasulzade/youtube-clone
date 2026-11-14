"""Lists show only listable videos (acceptance C3) and paginate with cursors."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Video
from app.models.enums import VideoStatus, Visibility
from tests.factories import auth_headers, create_user, create_video

NOW = datetime.now(UTC)


def _published(db: Session, channel, title: str, minutes_ago: int, **fields) -> Video:
    fields.setdefault("visibility", Visibility.PUBLIC)
    fields.setdefault("status", VideoStatus.READY)
    return create_video(
        db, channel, title=title, published_at=NOW - timedelta(minutes=minutes_ago), **fields
    )


@pytest.fixture
def isolated_feed(db_session: Session) -> None:
    """Hide pre-existing listable rows (e.g. dev data) so assertions see only ours."""
    db_session.execute(update(Video).values(is_hidden=True))


def _ids(response) -> list[str]:
    return [item["id"] for item in response.json()["items"]]


def test_home_feed_excludes_everything_not_listable(
    client: TestClient, db_session: Session, isolated_feed
) -> None:
    channel = create_user(db_session).channel
    visible = _published(db_session, channel, "Visible", 1)
    _published(db_session, channel, "Private", 2, visibility=Visibility.PRIVATE)
    _published(db_session, channel, "Unlisted", 3, visibility=Visibility.UNLISTED)
    _published(db_session, channel, "Hidden", 4, is_hidden=True)
    _published(db_session, channel, "Processing", 5, status=VideoStatus.PROCESSING)
    _published(db_session, channel, "Failed", 6, status=VideoStatus.FAILED)

    response = client.get("/api/v1/videos")

    assert _ids(response) == [visible.id]


def test_home_feed_paginates_newest_first_without_duplicates(
    client: TestClient, db_session: Session, isolated_feed
) -> None:
    channel = create_user(db_session).channel
    videos = [_published(db_session, channel, f"V{i}", minutes_ago=i) for i in range(7)]

    seen: list[str] = []
    cursor = None
    for _ in range(5):
        params = {"limit": 3} | ({"cursor": cursor} if cursor else {})
        body = client.get("/api/v1/videos", params=params).json()
        seen += [item["id"] for item in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert seen == [v.id for v in videos]  # newest (0 min ago) first


def test_feed_cards_expose_api_urls_and_channel(
    client: TestClient, db_session: Session, isolated_feed
) -> None:
    user = create_user(db_session)
    video = _published(db_session, user.channel, "Card", 1, duration_seconds=125)

    card = client.get("/api/v1/videos").json()["items"][0]

    assert card["id"] == video.id
    assert card["duration_seconds"] == 125
    assert card["channel"]["handle"] == user.channel.handle


def test_invalid_cursor_is_400(client: TestClient) -> None:
    response = client.get("/api/v1/videos", params={"cursor": "%%%not-base64"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_cursor"


def test_channel_videos_sorting(client: TestClient, db_session: Session) -> None:
    channel = create_user(db_session).channel
    old = _published(db_session, channel, "Old", 30, view_count=500)
    new = _published(db_session, channel, "New", 1, view_count=10)
    mid = _published(db_session, channel, "Mid", 10, view_count=90)
    _published(db_session, channel, "Secret", 2, visibility=Visibility.PRIVATE, view_count=9999)
    url = f"/api/v1/channels/{channel.handle}/videos"

    assert _ids(client.get(url)) == [new.id, mid.id, old.id]
    assert _ids(client.get(url, params={"sort": "oldest"})) == [old.id, mid.id, new.id]
    assert _ids(client.get(url, params={"sort": "popular"})) == [old.id, mid.id, new.id]


def test_popular_sort_paginates(client: TestClient, db_session: Session) -> None:
    channel = create_user(db_session).channel
    expected = [
        _published(db_session, channel, f"P{i}", i, view_count=100 - i).id for i in range(5)
    ]
    url = f"/api/v1/channels/{channel.handle}/videos"

    first = client.get(url, params={"sort": "popular", "limit": 2}).json()
    second = client.get(
        url, params={"sort": "popular", "limit": 2, "cursor": first["next_cursor"]}
    ).json()

    got = [i["id"] for i in first["items"]] + [i["id"] for i in second["items"]]
    assert got == expected[:4]


def test_subscriptions_feed_only_has_followed_channels(
    client: TestClient, db_session: Session, isolated_feed
) -> None:
    followed = create_user(db_session)
    other = create_user(db_session)
    viewer = create_user(db_session)
    mine = _published(db_session, followed.channel, "Followed", 1)
    _published(db_session, other.channel, "Not followed", 2)
    headers = auth_headers(viewer)
    client.put(f"/api/v1/channels/{followed.channel.handle}/subscription", headers=headers)

    feed = client.get("/api/v1/me/feed/subscriptions", headers=headers)
    sidebar = client.get("/api/v1/me/subscriptions", headers=headers)

    assert _ids(feed) == [mine.id]
    assert [c["handle"] for c in sidebar.json()] == [followed.channel.handle]


def test_library_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/me/subscriptions").status_code == 401
    assert client.get("/api/v1/me/feed/subscriptions").status_code == 401


def test_related_videos_exclude_self_and_non_listable(
    client: TestClient, db_session: Session, isolated_feed
) -> None:
    channel = create_user(db_session).channel
    current = _published(db_session, channel, "Plov recipe Baku", 1)
    similar = _published(db_session, channel, "Plov recipe Ganja", 2)
    _published(db_session, channel, "Plov recipe secret", 3, visibility=Visibility.PRIVATE)
    unrelated = _published(db_session, create_user(db_session).channel, "Guitar chords", 4)

    related = client.get(f"/api/v1/videos/{current.id}/related").json()

    ids = [v["id"] for v in related]
    assert current.id not in ids
    assert ids[0] == similar.id  # most similar title first
    assert set(ids) == {similar.id, unrelated.id}
