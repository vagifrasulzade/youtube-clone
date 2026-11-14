"""Helpers for tests that upload to real MinIO with a presigned POST policy."""

from __future__ import annotations

from io import BytesIO
from typing import Any

import httpx2
from PIL import Image

from app.core.config import get_settings
from app.storage import s3

# Minimal ISO-BMFF header: a real MP4 starts with an `ftyp` box.
FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 1024


def storage_upload_url() -> str:
    """What nginx proxies /storage/upload to in production (internal endpoint + bucket)."""
    settings = get_settings()
    return f"{settings.s3_endpoint_url}/{settings.uploads_bucket}"


def post_to_storage(
    fields: dict[str, str], data: bytes, *, filename: str = "clip.mp4"
) -> httpx2.Response:
    content_type = fields.get("Content-Type", "application/octet-stream")
    files = {"file": (filename, data, content_type)}  # S3 requires `file` as the last field
    return httpx2.post(storage_upload_url(), data=fields, files=files, timeout=30)


def create_upload(client: Any, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    body = {
        "filename": "holiday_clip.mp4",
        "content_type": "video/mp4",
        "size_bytes": len(FAKE_MP4),
    }
    body.update(overrides)
    response = client.post("/api/v1/videos", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def object_bytes(bucket: str, key: str) -> bytes:
    return s3.get_client().get_object(Bucket=bucket, Key=key)["Body"].read()


def image_bytes(fmt: str = "PNG", size: tuple[int, int] = (1000, 500)) -> bytes:
    out = BytesIO()
    Image.new("RGB", size, color=(200, 30, 30)).save(out, format=fmt)
    return out.getvalue()


def make_ready_video(db, channel, storage_cleanup: list[str], **fields: Any):
    """A processed video whose playback file and thumbnail really exist in MinIO."""
    from datetime import UTC, datetime

    from app.models import Video
    from app.models.enums import VideoStatus, Visibility
    from app.storage import keys

    fields.setdefault("title", "Ready video")
    fields.setdefault("visibility", Visibility.PUBLIC)
    video = Video(channel_id=channel.id, status=VideoStatus.READY, **fields)
    db.add(video)
    db.flush()
    settings = get_settings()
    video.playback_key = keys.video_playback(video.id)
    video.thumbnail_key = keys.video_thumbnail(video.id, "auto_2")
    video.published_at = datetime.now(UTC)
    s3.put_bytes(
        settings.media_bucket, video.playback_key, PLAYBACK_BYTES, content_type="video/mp4"
    )
    s3.put_bytes(
        settings.media_bucket, video.thumbnail_key, image_bytes("JPEG"), content_type="image/jpeg"
    )
    db.flush()
    storage_cleanup.append(video.id)
    return video


# 1000 deterministic bytes: enough to check Range arithmetic exactly.
PLAYBACK_BYTES = bytes(range(250)) * 4
