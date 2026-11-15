"""Protected media delivery (acceptance B1, B2, C1-C5) against real MinIO."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import VideoPermission
from app.models.enums import RoleName, Visibility
from app.services.media_tokens import create_media_session, create_media_token
from tests.factories import auth_headers, create_user
from tests.storage_helpers import PLAYBACK_BYTES, make_ready_video


@pytest.fixture
def owner(db_session: Session):
    return create_user(db_session)


def media_cookie(user) -> dict[str, str]:
    """The HttpOnly media cookie the browser receives at sign-in (binds media URLs)."""
    value = create_media_session(user.id, datetime.now(UTC) + timedelta(hours=1))
    return {"Cookie": f"yt_media={value}"}


def _stream_path(video_id: str, user=None) -> str:
    token = create_media_token(video_id, user.id if user else None)
    return f"/api/v1/media/videos/{video_id}/stream?t={token}"


# --- Range / streaming (B1) -------------------------------------------------------


def test_full_stream_of_a_public_video(client: TestClient, owner, db_session, storage_cleanup):
    video = make_ready_video(db_session, owner.channel, storage_cleanup)

    response = client.get(_stream_path(video.id))

    assert response.status_code == 200
    assert response.content == PLAYBACK_BYTES
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"


@pytest.mark.parametrize(
    ("range_header", "start", "end"),
    [("bytes=0-99", 0, 99), ("bytes=900-", 900, 999), ("bytes=-10", 990, 999)],
)
def test_range_requests_return_206_with_exact_bytes(
    client: TestClient, owner, db_session, storage_cleanup, range_header, start, end
):
    """B1: seeking works because partial content is served correctly."""
    video = make_ready_video(db_session, owner.channel, storage_cleanup)

    response = client.get(_stream_path(video.id), headers={"Range": range_header})

    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes {start}-{end}/{len(PLAYBACK_BYTES)}"
    assert response.content == PLAYBACK_BYTES[start : end + 1]


def test_unsatisfiable_range_returns_416(client: TestClient, owner, db_session, storage_cleanup):
    video = make_ready_video(db_session, owner.channel, storage_cleanup)

    response = client.get(_stream_path(video.id), headers={"Range": "bytes=5000-6000"})

    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(PLAYBACK_BYTES)}"


# --- visibility on media (C1-C5) --------------------------------------------------


def test_private_stream_is_404_for_anonymous_and_strangers(
    client: TestClient, owner, db_session, storage_cleanup
):
    """C2: not 403, so the video's existence is not revealed."""
    video = make_ready_video(
        db_session, owner.channel, storage_cleanup, visibility=Visibility.PRIVATE
    )
    stranger = create_user(db_session)

    assert client.get(_stream_path(video.id)).status_code == 404
    assert client.get(_stream_path(video.id, stranger)).status_code == 404


@pytest.mark.parametrize("who", ["owner", "granted", "moderator", "admin"])
def test_private_stream_is_served_to_allowed_viewers(
    client: TestClient, owner, db_session, storage_cleanup, who
):
    video = make_ready_video(
        db_session, owner.channel, storage_cleanup, visibility=Visibility.PRIVATE
    )
    viewer = {
        "owner": lambda: owner,
        "granted": lambda: create_user(db_session),
        "moderator": lambda: create_user(db_session, role=RoleName.MODERATOR),
        "admin": lambda: create_user(db_session, role=RoleName.ADMIN),
    }[who]()
    if who == "granted":
        db_session.add(VideoPermission(video_id=video.id, user_id=viewer.id))
        db_session.flush()

    assert (
        client.get(_stream_path(video.id, viewer), headers=media_cookie(viewer)).status_code == 200
    )


def test_revoking_a_grant_stops_the_next_range_request(
    client: TestClient, owner, db_session, storage_cleanup
):
    """C4: the token identifies the viewer; the grant is re-checked on every request."""
    video = make_ready_video(
        db_session, owner.channel, storage_cleanup, visibility=Visibility.PRIVATE
    )
    friend = create_user(db_session)
    db_session.add(VideoPermission(video_id=video.id, user_id=friend.id))
    db_session.flush()
    path = _stream_path(video.id, friend)
    assert (
        client.get(path, headers={"Range": "bytes=0-9", **media_cookie(friend)}).status_code == 206
    )

    db_session.execute(delete(VideoPermission).where(VideoPermission.video_id == video.id))
    db_session.flush()

    assert (
        client.get(path, headers={"Range": "bytes=10-19", **media_cookie(friend)}).status_code
        == 404
    )


def test_hidden_video_media_is_404_for_the_public(
    client: TestClient, owner, db_session, storage_cleanup
):
    """C5"""
    video = make_ready_video(db_session, owner.channel, storage_cleanup, is_hidden=True)

    assert client.get(_stream_path(video.id)).status_code == 404
    assert client.get(f"/api/v1/media/videos/{video.id}/thumbnail").status_code == 404
    assert client.get(_stream_path(video.id, owner), headers=media_cookie(owner)).status_code == 200


def test_a_media_token_is_bound_to_one_video(
    client: TestClient, owner, db_session, storage_cleanup
):
    private = make_ready_video(
        db_session, owner.channel, storage_cleanup, visibility=Visibility.PRIVATE
    )
    other = make_ready_video(db_session, owner.channel, storage_cleanup)
    token_for_other = create_media_token(other.id, owner.id)

    response = client.get(
        f"/api/v1/media/videos/{private.id}/stream?t={token_for_other}", headers=media_cookie(owner)
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_media_token"


def test_tampered_media_token_is_rejected(client: TestClient, owner, db_session, storage_cleanup):
    video = make_ready_video(db_session, owner.channel, storage_cleanup)

    response = client.get(f"/api/v1/media/videos/{video.id}/stream?t=not.a.token")

    assert response.status_code == 401


# --- thumbnails & channel images --------------------------------------------------


def test_public_thumbnail_is_cacheable_private_one_is_not(
    client: TestClient, owner, db_session, storage_cleanup
):
    public = make_ready_video(db_session, owner.channel, storage_cleanup)
    private = make_ready_video(
        db_session, owner.channel, storage_cleanup, visibility=Visibility.PRIVATE
    )

    public_response = client.get(f"/api/v1/media/videos/{public.id}/thumbnail")
    private_anonymous = client.get(f"/api/v1/media/videos/{private.id}/thumbnail")
    token = create_media_token(private.id, owner.id)
    private_owner = client.get(
        f"/api/v1/media/videos/{private.id}/thumbnail?t={token}", headers=media_cookie(owner)
    )

    assert public_response.status_code == 200
    assert public_response.headers["cache-control"] == "no-cache"  # revalidate: review L7
    assert private_anonymous.status_code == 404
    assert private_owner.status_code == 200
    assert private_owner.headers["cache-control"] == "private, no-store"


def test_unknown_channel_image_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/media/channels/not-a-uuid/avatar").status_code == 404


# --- accel mode (production path through nginx) -----------------------------------


def test_accel_mode_hands_an_internal_presigned_path_to_nginx(
    client: TestClient, owner, db_session, storage_cleanup, monkeypatch: pytest.MonkeyPatch
):
    """B2: the browser never sees the storage URL; nginx follows X-Accel-Redirect."""
    monkeypatch.setattr(get_settings(), "media_delivery", "accel")
    video = make_ready_video(db_session, owner.channel, storage_cleanup)

    response = client.get(_stream_path(video.id), headers={"Range": "bytes=0-9"})

    target = response.headers["x-accel-redirect"]
    assert response.status_code == 200
    assert response.content == b""
    assert target.startswith(f"/_media/{get_settings().media_bucket}/videos/{video.id}/")
    assert "X-Amz-Signature" in parse_qs(urlsplit(target).query)


# --- detail endpoint --------------------------------------------------------------


def test_detail_returns_api_media_urls_never_storage_urls(
    client: TestClient, owner, db_session, storage_cleanup
):
    video = make_ready_video(db_session, owner.channel, storage_cleanup)

    response = client.get(f"/api/v1/videos/{video.id}")

    body = response.json()
    assert response.status_code == 200
    assert body["stream_url"].startswith(f"/api/v1/media/videos/{video.id}/stream?t=")
    assert body["thumbnail_url"].startswith(f"/api/v1/media/videos/{video.id}/thumbnail")
    assert body["channel"]["handle"] == owner.channel.handle
    assert body["can_edit"] is False
    endpoint_host = get_settings().s3_endpoint_url.split("://", 1)[1]
    assert endpoint_host not in response.text
    assert not re.search(r"X-Amz-", response.text)


def test_detail_of_private_video_is_404_for_strangers(
    client: TestClient, owner, db_session, storage_cleanup
):
    video = make_ready_video(
        db_session, owner.channel, storage_cleanup, visibility=Visibility.PRIVATE
    )

    anonymous = client.get(f"/api/v1/videos/{video.id}")
    stranger = client.get(
        f"/api/v1/videos/{video.id}", headers=auth_headers(create_user(db_session))
    )
    mine = client.get(f"/api/v1/videos/{video.id}", headers=auth_headers(owner))

    assert anonymous.status_code == stranger.status_code == 404
    assert mine.status_code == 200
    assert mine.json()["can_edit"] is True


def test_detail_of_unknown_or_malformed_id_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/videos/doesnotexis").status_code == 404
    assert client.get("/api/v1/videos/../../etc").status_code == 404


def test_a_copied_media_link_does_not_unlock_a_private_video(
    client: TestClient, owner, db_session, storage_cleanup
):
    """Review M1: the URL names the owner, but another browser lacks the owner's cookie."""
    video = make_ready_video(
        db_session, owner.channel, storage_cleanup, visibility=Visibility.PRIVATE
    )
    copied = _stream_path(video.id, owner)
    someone_else = create_user(db_session)

    assert client.get(copied, headers=media_cookie(owner)).status_code == 200
    assert client.get(copied).status_code == 404  # no cookie: anonymous
    assert client.get(copied, headers=media_cookie(someone_else)).status_code == 404


def test_a_copied_link_to_a_public_video_still_plays(
    client: TestClient, owner, db_session, storage_cleanup
):
    video = make_ready_video(db_session, owner.channel, storage_cleanup)

    assert client.get(_stream_path(video.id, owner)).status_code == 200
