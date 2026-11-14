"""Subscriptions (acceptance D3) and the channel page header."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Channel, Subscription
from app.models.enums import VideoStatus, Visibility
from tests.factories import auth_headers, create_user, create_video


def _subscriber_rows(db: Session, channel: Channel) -> int:
    return db.scalar(select(func.count()).where(Subscription.channel_id == channel.id)) or 0


def test_subscribe_and_unsubscribe_are_idempotent(client: TestClient, db_session: Session) -> None:
    creator = create_user(db_session)
    headers = auth_headers(create_user(db_session))
    url = f"/api/v1/channels/{creator.channel.handle}/subscription"

    first = client.put(url, headers=headers)
    again = client.put(url, headers=headers)

    assert first.json() == {"subscribed": True, "subscriber_count": 1}
    assert again.json() == {"subscribed": True, "subscriber_count": 1}
    assert _subscriber_rows(db_session, creator.channel) == 1

    gone = client.delete(url, headers=headers)
    gone_again = client.delete(url, headers=headers)

    assert gone.json() == {"subscribed": False, "subscriber_count": 0}
    assert gone_again.json() == {"subscribed": False, "subscriber_count": 0}
    assert _subscriber_rows(db_session, creator.channel) == 0


def test_cannot_subscribe_to_own_channel(client: TestClient, db_session: Session) -> None:
    creator = create_user(db_session)

    response = client.put(
        f"/api/v1/channels/{creator.channel.handle}/subscription", headers=auth_headers(creator)
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "self_subscription"


def test_subscribe_requires_authentication(client: TestClient, db_session: Session) -> None:
    creator = create_user(db_session)

    assert client.put(f"/api/v1/channels/{creator.channel.handle}/subscription").status_code == 401


def test_unknown_channel_is_404(client: TestClient, db_session: Session) -> None:
    headers = auth_headers(create_user(db_session))

    assert client.put("/api/v1/channels/nobody_here/subscription", headers=headers).status_code == (
        404
    )
    assert client.get("/api/v1/channels/nobody_here").status_code == 404


def test_channel_page_counts_only_listable_videos(client: TestClient, db_session: Session) -> None:
    creator = create_user(db_session)
    viewer = create_user(db_session)
    channel = creator.channel
    create_video(db_session, channel, status=VideoStatus.READY, visibility=Visibility.PUBLIC)
    create_video(db_session, channel, status=VideoStatus.READY, visibility=Visibility.PRIVATE)
    create_video(db_session, channel, status=VideoStatus.READY, visibility=Visibility.UNLISTED)
    create_video(db_session, channel, status=VideoStatus.PROCESSING, visibility=Visibility.PUBLIC)
    client.put(f"/api/v1/channels/{channel.handle}/subscription", headers=auth_headers(viewer))

    page = client.get(f"/api/v1/channels/{channel.handle}", headers=auth_headers(viewer)).json()

    assert page["video_count"] == 1
    assert page["subscriber_count"] == 1
    assert page["is_subscribed"] is True
    assert page["is_owner"] is False


def test_detail_shows_subscription_state(client: TestClient, db_session: Session) -> None:
    creator = create_user(db_session)
    video = create_video(
        db_session, creator.channel, status=VideoStatus.READY, visibility=Visibility.PUBLIC
    )
    headers = auth_headers(create_user(db_session))
    client.put(f"/api/v1/channels/{creator.channel.handle}/subscription", headers=headers)

    body = client.get(f"/api/v1/videos/{video.id}", headers=headers).json()

    assert body["is_subscribed"] is True
    assert body["channel"]["subscriber_count"] == 1
