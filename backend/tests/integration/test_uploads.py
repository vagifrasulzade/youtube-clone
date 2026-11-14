"""Upload flow against real MinIO (acceptance criteria A1-A3, B2).

The browser POSTs straight to storage with a policy signed by the API; these tests do
the same, so the limits asserted here are enforced by MinIO itself.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Video
from app.models.enums import VideoStatus, Visibility
from app.storage import s3
from tests.factories import auth_headers, create_user, create_video
from tests.storage_helpers import FAKE_MP4, create_upload, post_to_storage

VIDEOS = "/api/v1/videos"


@pytest.fixture
def owner(db_session: Session):
    return create_user(db_session)


@pytest.fixture
def headers(owner) -> dict[str, str]:
    return auth_headers(owner)


def test_create_upload_returns_private_draft_and_storage_policy(
    client: TestClient, headers: dict[str, str], storage_cleanup: list[str]
) -> None:
    body = create_upload(client, headers)
    storage_cleanup.append(body["video"]["id"])

    video, upload = body["video"], body["upload"]
    assert video["status"] == "awaiting_upload"
    assert video["visibility"] == "private"  # drafts are private until published
    assert video["title"] == "holiday clip"  # defaults to the file name
    assert upload["url"] == "/storage/upload"  # same-origin path, not the storage host
    assert upload["fields"]["key"] == f"{video['id']}/source"
    assert upload["fields"]["Content-Type"] == "video/mp4"
    assert {"policy", "x-amz-signature", "x-amz-credential"} <= set(upload["fields"])


def test_api_responses_never_expose_the_storage_endpoint(
    client: TestClient, headers: dict[str, str], storage_cleanup: list[str]
) -> None:
    """B2"""
    response = client.post(
        VIDEOS,
        json={"filename": "a.mp4", "content_type": "video/mp4", "size_bytes": 10},
        headers=headers,
    )
    storage_cleanup.append(response.json()["video"]["id"])

    endpoint_host = get_settings().s3_endpoint_url.split("://", 1)[1]
    assert endpoint_host not in response.text
    assert "minio" not in response.text.lower()


def test_upload_roundtrip_queues_processing(
    client: TestClient,
    headers: dict[str, str],
    db_session: Session,
    storage_cleanup: list[str],
    enqueued: list[tuple[str, str]],
) -> None:
    """A1 (upload half): the file reaches storage and the video is queued for processing."""
    body = create_upload(client, headers)
    video_id = body["video"]["id"]
    storage_cleanup.append(video_id)

    stored = post_to_storage(body["upload"]["fields"], FAKE_MP4)
    completed = client.post(f"{VIDEOS}/{video_id}/upload-complete", headers=headers)

    assert stored.status_code == 204, stored.text
    assert completed.status_code == 202
    assert completed.json()["status"] == "queued"
    assert enqueued == [("process", video_id)]
    video = db_session.get(Video, video_id)
    assert video is not None
    db_session.refresh(video)
    assert video.status == VideoStatus.QUEUED
    assert video.source_size_bytes == len(FAKE_MP4)


def test_storage_rejects_a_file_larger_than_the_policy_allows(
    client: TestClient,
    headers: dict[str, str],
    storage_cleanup: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A2: the size limit is enforced by MinIO, not only by the UI or the API."""
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 2048)
    body = create_upload(client, headers, size_bytes=1000)  # lies about the size
    storage_cleanup.append(body["video"]["id"])

    response = post_to_storage(body["upload"]["fields"], b"\x00" * 4096)

    assert response.status_code == 400
    assert "EntityTooLarge" in response.text


def test_storage_rejects_a_tampered_object_key(
    client: TestClient, headers: dict[str, str], storage_cleanup: list[str]
) -> None:
    body = create_upload(client, headers)
    storage_cleanup.append(body["video"]["id"])
    fields = {**body["upload"]["fields"], "key": "someone-else/source"}

    response = post_to_storage(fields, FAKE_MP4)

    assert response.status_code == 403


def test_storage_rejects_a_tampered_content_type(
    client: TestClient, headers: dict[str, str], storage_cleanup: list[str]
) -> None:
    body = create_upload(client, headers)
    storage_cleanup.append(body["video"]["id"])
    fields = {**body["upload"]["fields"], "Content-Type": "text/html"}

    response = post_to_storage(fields, b"<script>alert(1)</script>")

    assert response.status_code == 403


def test_declared_size_over_the_limit_is_rejected(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.post(
        VIDEOS,
        json={
            "filename": "huge.mp4",
            "content_type": "video/mp4",
            "size_bytes": get_settings().max_upload_bytes + 1,
        },
        headers=headers,
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("report.pdf", "application/pdf"),
        ("clip.mp4", "image/png"),
        ("payload.exe", "video/mp4"),
        ("clip.webm", "video/mp4"),
    ],
)
def test_unsupported_file_types_are_rejected(
    client: TestClient, headers: dict[str, str], filename: str, content_type: str
) -> None:
    response = client.post(
        VIDEOS,
        json={"filename": filename, "content_type": content_type, "size_bytes": 100},
        headers=headers,
    )

    assert response.status_code == 415


def test_object_key_comes_from_the_server_id_not_the_filename(
    client: TestClient, headers: dict[str, str], storage_cleanup: list[str]
) -> None:
    body = create_upload(client, headers, filename="../../etc/passwd.mp4")
    storage_cleanup.append(body["video"]["id"])

    assert body["upload"]["fields"]["key"] == f"{body['video']['id']}/source"
    assert body["video"]["original_filename"] == "passwd.mp4"


def test_complete_without_an_uploaded_file_conflicts(
    client: TestClient, headers: dict[str, str], storage_cleanup: list[str]
) -> None:
    body = create_upload(client, headers)
    storage_cleanup.append(body["video"]["id"])

    response = client.post(f"{VIDEOS}/{body['video']['id']}/upload-complete", headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "upload_not_found"


def test_complete_twice_conflicts(
    client: TestClient, headers: dict[str, str], storage_cleanup: list[str]
) -> None:
    body = create_upload(client, headers)
    video_id = body["video"]["id"]
    storage_cleanup.append(video_id)
    post_to_storage(body["upload"]["fields"], FAKE_MP4)
    client.post(f"{VIDEOS}/{video_id}/upload-complete", headers=headers)

    response = client.post(f"{VIDEOS}/{video_id}/upload-complete", headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


def test_a_non_video_file_fails_with_a_readable_reason(
    client: TestClient,
    headers: dict[str, str],
    storage_cleanup: list[str],
    enqueued: list[tuple[str, str]],
) -> None:
    """A3: a text file renamed to .mp4 is never published."""
    body = create_upload(client, headers)
    video_id = body["video"]["id"]
    storage_cleanup.append(video_id)
    post_to_storage(body["upload"]["fields"], b"this is just text pretending to be a video")

    response = client.post(f"{VIDEOS}/{video_id}/upload-complete", headers=headers)
    status_response = client.get(f"{VIDEOS}/{video_id}/status", headers=headers)

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "not_a_video"
    assert status_response.json()["status"] == "failed"
    assert "not a supported video" in status_response.json()["error"]
    assert enqueued == []
    settings = get_settings()
    assert s3.head(settings.uploads_bucket, f"{video_id}/source") is None  # rejected bytes gone


def test_other_users_cannot_see_or_complete_a_draft(
    client: TestClient, headers: dict[str, str], db_session: Session, storage_cleanup: list[str]
) -> None:
    body = create_upload(client, headers)
    video_id = body["video"]["id"]
    storage_cleanup.append(video_id)
    stranger = auth_headers(create_user(db_session))

    complete = client.post(f"{VIDEOS}/{video_id}/upload-complete", headers=stranger)
    status_response = client.get(f"{VIDEOS}/{video_id}/status", headers=stranger)

    assert complete.status_code == 404  # a private draft is not revealed
    assert status_response.status_code == 404


def test_upload_requires_authentication(client: TestClient) -> None:
    response = client.post(
        VIDEOS, json={"filename": "a.mp4", "content_type": "video/mp4", "size_bytes": 10}
    )

    assert response.status_code == 401


def test_upload_creation_is_rate_limited(
    client: TestClient, headers: dict[str, str], storage_cleanup: list[str]
) -> None:
    payload = {"filename": "a.mp4", "content_type": "video/mp4", "size_bytes": 10}
    statuses = []
    for _ in range(21):
        response = client.post(VIDEOS, json=payload, headers=headers)
        statuses.append(response.status_code)
        if response.status_code == 201:
            storage_cleanup.append(response.json()["video"]["id"])

    assert statuses == [201] * 20 + [429]


# --- metadata -------------------------------------------------------------------


def test_owner_can_edit_metadata(
    client: TestClient, headers: dict[str, str], storage_cleanup: list[str]
) -> None:
    video_id = create_upload(client, headers)["video"]["id"]
    storage_cleanup.append(video_id)

    response = client.patch(
        f"{VIDEOS}/{video_id}",
        json={"title": "  My trip  ", "description": "Day 1\nDay 2", "visibility": "public"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == "My trip"
    assert response.json()["description"] == "Day 1\nDay 2"
    assert response.json()["visibility"] == "public"


@pytest.mark.parametrize(
    "payload",
    [{"status": "ready"}, {"is_hidden": False}, {"view_count": 1_000_000}, {"title": ""}],
    ids=["status", "is_hidden", "counter", "empty-title"],
)
def test_metadata_update_rejects_protected_or_invalid_fields(
    client: TestClient, headers: dict[str, str], storage_cleanup: list[str], payload: dict
) -> None:
    video_id = create_upload(client, headers)["video"]["id"]
    storage_cleanup.append(video_id)

    response = client.patch(f"{VIDEOS}/{video_id}", json=payload, headers=headers)

    assert response.status_code == 422


def test_non_owner_cannot_edit_a_public_video(
    client: TestClient, owner, db_session: Session
) -> None:
    video = create_video(
        db_session, owner.channel, visibility=Visibility.PUBLIC, status=VideoStatus.READY
    )
    stranger = auth_headers(create_user(db_session))

    response = client.patch(f"{VIDEOS}/{video.id}", json={"title": "pwned"}, headers=stranger)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_owner"
