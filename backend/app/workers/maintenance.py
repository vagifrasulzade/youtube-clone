"""Housekeeping jobs run by Celery beat (docs/architecture.md § 2.6).

Plain functions taking a session, so they can be tested directly; app.workers.tasks
wraps them as Celery tasks.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Video
from app.models.enums import VideoStatus
from app.storage import keys, s3
from app.workers import queue

logger = logging.getLogger(__name__)

STALE_DRAFT_AGE = timedelta(hours=24)
QUEUED_RETRY_AGE = timedelta(minutes=10)
PROCESSING_TIMEOUT = timedelta(minutes=40)  # above the task's hard time limit


def delete_video_objects(video_id: str) -> int:
    """Remove every stored object of a video. Idempotent: safe to run again."""
    settings = get_settings()
    removed = s3.delete_prefix(settings.media_bucket, keys.video_prefix(video_id))
    s3.delete(settings.uploads_bucket, keys.video_source(video_id))  # no-op if already gone
    return removed


def cleanup_stale_drafts(db: Session, now: datetime | None = None) -> list[str]:
    """Drafts whose upload never completed within 24 h are removed (acceptance A5).
    Their raw bytes, if any, are also expired by the bucket lifecycle rule."""
    cutoff = (now or datetime.now(UTC)) - STALE_DRAFT_AGE
    ids = list(
        db.scalars(
            delete(Video)
            .where(Video.status == VideoStatus.AWAITING_UPLOAD, Video.created_at < cutoff)
            .returning(Video.id)
        )
    )
    db.commit()
    for video_id in ids:
        queue.enqueue_video_deletion(video_id)
    if ids:
        logger.info("Removed stale drafts", extra={"count": len(ids)})
    return ids


def watchdog(db: Session, now: datetime | None = None) -> tuple[list[str], list[str]]:
    """Recover from lost messages and crashed workers.

    - `queued` for more than 10 minutes: enqueue again (claiming is idempotent).
    - `processing` for longer than the hard time limit: mark failed with a reason.
    """
    now = now or datetime.now(UTC)
    requeued = list(
        db.scalars(
            select(Video.id).where(
                Video.status == VideoStatus.QUEUED, Video.updated_at < now - QUEUED_RETRY_AGE
            )
        )
    )
    timed_out = list(
        db.scalars(
            update(Video)
            .where(
                Video.status == VideoStatus.PROCESSING,
                Video.processing_started_at < now - PROCESSING_TIMEOUT,
            )
            .values(
                status=VideoStatus.FAILED,
                processing_error="Processing did not finish in time; please upload again",
            )
            .returning(Video.id)
        )
    )
    db.commit()
    for video_id in requeued:
        queue.enqueue_video_processing(video_id)
    if requeued or timed_out:
        logger.warning(
            "Watchdog acted", extra={"requeued": len(requeued), "timed_out": len(timed_out)}
        )
    return requeued, timed_out
