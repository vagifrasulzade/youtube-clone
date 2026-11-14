"""Video upload lifecycle: draft + presigned POST policy, then upload-complete.

Flow (docs/video-storage.md § 2):
1. `create_draft` validates the declared file, inserts a private draft and returns a
   POST policy. MinIO itself enforces the exact key, Content-Type and size range.
2. The browser uploads straight to storage (bytes never pass through the API).
3. `complete_upload` checks the object really exists, its real size and its magic
   bytes, then marks the video `queued` and enqueues processing after commit.
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, PayloadTooLargeError, UnsupportedMediaError
from app.models import User, Video
from app.models.enums import VideoStatus
from app.services import access
from app.storage import keys, s3
from app.workers import queue

logger = logging.getLogger(__name__)

# Declared MIME type -> allowed file extensions.
ALLOWED_VIDEO_TYPES: dict[str, frozenset[str]] = {
    "video/mp4": frozenset({".mp4", ".m4v"}),
    "video/quicktime": frozenset({".mov"}),
    "video/webm": frozenset({".webm"}),
    "video/x-matroska": frozenset({".mkv"}),
    "video/x-msvideo": frozenset({".avi"}),
    "video/avi": frozenset({".avi"}),
}

# ISO-BMFF (MP4/MOV) boxes that may legitimately start a file.
_ISO_BMFF_BOXES = {b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip"}


@dataclass(frozen=True)
class UploadTicket:
    video: Video
    url: str
    fields: dict[str, str]
    expires_at: datetime
    max_bytes: int


def sanitize_filename(name: str) -> str:
    """Display-only: basename, no control characters, bounded length. Never used in keys."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(ch for ch in base if unicodedata.category(ch)[0] != "C").strip()
    return cleaned[:255] or "video"


def default_title(filename: str) -> str:
    stem = PurePosixPath(filename).stem.replace("_", " ").strip()
    return stem[:100] or "Untitled video"


def sniff_container(head: bytes) -> str | None:
    """Recognize the container from its first bytes (ffprobe re-checks it later)."""
    if len(head) >= 8 and head[4:8] in _ISO_BMFF_BOXES:
        return "mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "matroska"  # WebM / MKV (EBML)
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "avi"
    return None


def create_draft(
    db: Session,
    user: User,
    *,
    filename: str,
    content_type: str,
    size_bytes: int,
    title: str | None,
) -> UploadTicket:
    settings = get_settings()
    if size_bytes > settings.max_upload_bytes:
        raise PayloadTooLargeError(
            "The file is larger than the upload limit",
            code="file_too_large",
            details={"max_bytes": settings.max_upload_bytes},
        )
    clean_name = sanitize_filename(filename)
    content_type = content_type.strip().lower()
    allowed_extensions = ALLOWED_VIDEO_TYPES.get(content_type)
    extension = PurePosixPath(clean_name).suffix.lower()
    if allowed_extensions is None or extension not in allowed_extensions:
        raise UnsupportedMediaError(
            "Upload an MP4, MOV, WebM, MKV or AVI video",
            details={"allowed": sorted(ALLOWED_VIDEO_TYPES)},
        )

    video = Video(
        channel_id=user.channel.id,
        title=title or default_title(clean_name),
        original_filename=clean_name,
        source_size_bytes=size_bytes,
    )
    db.add(video)
    db.flush()  # assigns the id
    video.source_key = keys.video_source(video.id)

    policy = s3.presign_upload(
        settings.uploads_bucket,
        video.source_key,
        content_type=content_type,
        max_bytes=settings.max_upload_bytes,
        expires_in=settings.upload_policy_ttl_seconds,
    )
    db.commit()
    logger.info("Upload draft created", extra={"video_id": video.id, "size": size_bytes})
    return UploadTicket(
        video=video,
        url=settings.s3_public_upload_url,  # never the internal storage endpoint
        fields=policy.fields,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.upload_policy_ttl_seconds),
        max_bytes=settings.max_upload_bytes,
    )


def _reject_upload(db: Session, video: Video, reason: str) -> None:
    video.status = VideoStatus.FAILED
    video.processing_error = reason
    db.commit()
    try:
        s3.delete(get_settings().uploads_bucket, video.source_key or keys.video_source(video.id))
    except s3.StorageError:
        logger.warning("Could not delete rejected upload; lifecycle rule will expire it")


def complete_upload(db: Session, user: User, video_id: str) -> Video:
    settings = get_settings()
    video = access.get_owned_video(db, video_id, user)
    if video.status != VideoStatus.AWAITING_UPLOAD:
        raise ConflictError("This upload was already completed", code="invalid_state")

    source_key = video.source_key or keys.video_source(video.id)
    info = s3.head(settings.uploads_bucket, source_key)
    if info is None:
        raise ConflictError("No uploaded file found for this video", code="upload_not_found")
    if info.size > settings.max_upload_bytes:  # defense in depth: the policy already caps it
        _reject_upload(db, video, "The file is larger than the upload limit")
        raise PayloadTooLargeError(code="file_too_large")

    head = s3.read_range(settings.uploads_bucket, source_key, 0, 63)
    if sniff_container(head) is None:
        _reject_upload(db, video, "The file is not a supported video format")
        raise UnsupportedMediaError("The file is not a supported video", code="not_a_video")

    video.source_size_bytes = info.size
    video.status = VideoStatus.QUEUED
    db.commit()
    queue.enqueue_video_processing(video.id)  # after commit (CLAUDE.md rule 6)
    return video
