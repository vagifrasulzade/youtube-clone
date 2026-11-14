"""Private videos: only the owner and users the owner approved (brief + C1, C2, C4)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import VideoStatus, Visibility
from tests.factories import auth_headers, create_user, create_video


@pytest.fixture
def setup(db_session: Session):
    owner = create_user(db_session)
    friend = create_user(db_session)
    stranger = create_user(db_session)
    video = create_video(
        db_session, owner.channel, status=VideoStatus.READY, visibility=Visibility.PRIVATE
    )
    return owner, friend, stranger, video


def test_owner_grants_access_and_the_friend_can_watch(client: TestClient, setup) -> None:
    owner, friend, stranger, video = setup
    detail = f"/api/v1/videos/{video.id}"
    assert client.get(detail, headers=auth_headers(friend)).status_code == 404

    granted = client.post(
        f"{detail}/permissions",
        json={"handle": friend.channel.handle},
        headers=auth_headers(owner),
    )

    assert granted.status_code == 201
    assert client.get(detail, headers=auth_headers(friend)).status_code == 200
    assert client.get(detail, headers=auth_headers(stranger)).status_code == 404
    assert client.get(detail).status_code == 404


def test_revoking_access_takes_effect_immediately(client: TestClient, setup) -> None:
    """C4"""
    owner, friend, _, video = setup
    base = f"/api/v1/videos/{video.id}"
    client.post(
        f"{base}/permissions", json={"handle": friend.channel.handle}, headers=auth_headers(owner)
    )
    assert client.get(base, headers=auth_headers(friend)).status_code == 200

    revoked = client.delete(f"{base}/permissions/{friend.id}", headers=auth_headers(owner))

    assert revoked.status_code == 204
    assert client.get(base, headers=auth_headers(friend)).status_code == 404


def test_owner_lists_grants(client: TestClient, setup) -> None:
    owner, friend, _, video = setup
    base = f"/api/v1/videos/{video.id}/permissions"
    client.post(base, json={"handle": friend.channel.handle}, headers=auth_headers(owner))
    client.post(
        base, json={"handle": friend.channel.handle}, headers=auth_headers(owner)
    )  # idempotent

    listed = client.get(base, headers=auth_headers(owner)).json()

    assert [g["handle"] for g in listed] == [friend.channel.handle]


@pytest.mark.parametrize("method", ["get", "post"])
def test_only_the_owner_manages_grants(client: TestClient, setup, method: str) -> None:
    _, _friend, stranger, video = setup
    url = f"/api/v1/videos/{video.id}/permissions"
    kwargs = {"json": {"handle": stranger.channel.handle}} if method == "post" else {}

    response = getattr(client, method)(url, headers=auth_headers(stranger), **kwargs)

    assert response.status_code == 404  # the private video is not revealed


def test_grantee_cannot_grant_others(client: TestClient, setup) -> None:
    owner, friend, stranger, video = setup
    url = f"/api/v1/videos/{video.id}/permissions"
    client.post(url, json={"handle": friend.channel.handle}, headers=auth_headers(owner))

    response = client.post(
        url, json={"handle": stranger.channel.handle}, headers=auth_headers(friend)
    )

    assert response.status_code == 403  # can see it, but does not own it


def test_unknown_handle_and_self_grant(client: TestClient, setup) -> None:
    owner, _, _, video = setup
    url = f"/api/v1/videos/{video.id}/permissions"

    assert (
        client.post(url, json={"handle": "ghost_user"}, headers=auth_headers(owner)).status_code
        == 404
    )
    assert (
        client.post(
            url, json={"handle": owner.channel.handle}, headers=auth_headers(owner)
        ).status_code
        == 400
    )


def test_shared_with_me_lists_granted_private_videos(client: TestClient, setup) -> None:
    owner, friend, _, video = setup
    client.post(
        f"/api/v1/videos/{video.id}/permissions",
        json={"handle": friend.channel.handle},
        headers=auth_headers(owner),
    )

    shared = client.get("/api/v1/me/shared", headers=auth_headers(friend)).json()

    assert [v["id"] for v in shared] == [video.id]


def test_private_video_never_appears_in_public_lists(client: TestClient, setup) -> None:
    """C3, even for a user who has been granted access."""
    owner, friend, _, video = setup
    client.post(
        f"/api/v1/videos/{video.id}/permissions",
        json={"handle": friend.channel.handle},
        headers=auth_headers(owner),
    )
    headers = auth_headers(friend)

    feed = client.get("/api/v1/videos", headers=headers).json()["items"]
    channel = client.get(f"/api/v1/channels/{owner.channel.handle}/videos", headers=headers).json()

    assert video.id not in {v["id"] for v in feed}
    assert video.id not in {v["id"] for v in channel["items"]}
