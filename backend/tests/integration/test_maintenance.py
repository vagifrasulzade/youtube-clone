"""Housekeeping jobs: stale drafts (A5), watchdog, idempotent object deletion."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Video
from app.models.enums import VideoStatus
from app.storage import keys, s3
from app.workers import maintenance
from tests.factories import create_user, create_video

LATER = datetime.now(UTC) + timedelta(days=2)


def test_stale_drafts_are_removed_and_storage_cleanup_enqueued(
    db_session: Session, enqueued: list[tuple[str, str]]
) -> None:
    channel = create_user(db_session).channel
    draft = create_video(db_session, channel, status=VideoStatus.AWAITING_UPLOAD)
    queued = create_video(db_session, channel, status=VideoStatus.QUEUED)

    removed = maintenance.cleanup_stale_drafts(db_session, now=LATER)

    assert draft.id in removed
    assert queued.id not in removed
    assert ("delete", draft.id) in enqueued
    db_session.expire_all()
    assert db_session.get(Video, draft.id) is None
    assert db_session.get(Video, queued.id) is not None


def test_recent_drafts_are_kept(db_session: Session) -> None:
    draft = create_video(
        db_session, create_user(db_session).channel, status=VideoStatus.AWAITING_UPLOAD
    )

    assert draft.id not in maintenance.cleanup_stale_drafts(db_session)


def test_watchdog_requeues_stuck_queued_and_fails_timed_out_processing(
    db_session: Session, enqueued: list[tuple[str, str]]
) -> None:
    channel = create_user(db_session).channel
    stuck = create_video(db_session, channel, status=VideoStatus.QUEUED)
    hung = create_video(
        db_session,
        channel,
        status=VideoStatus.PROCESSING,
        processing_started_at=datetime.now(UTC) - timedelta(hours=1),
    )
    ready = create_video(db_session, channel, status=VideoStatus.READY)

    requeued, timed_out = maintenance.watchdog(db_session, now=LATER)

    assert stuck.id in requeued
    assert ("process", stuck.id) in enqueued
    assert timed_out == [hung.id]
    db_session.expire_all()
    failed = db_session.get(Video, hung.id)
    assert failed is not None
    assert failed.status == VideoStatus.FAILED
    assert "did not finish" in (failed.processing_error or "")
    assert db_session.get(Video, ready.id).status == VideoStatus.READY  # type: ignore[union-attr]


def test_deleting_video_objects_is_idempotent(storage_cleanup: list[str]) -> None:
    settings = get_settings()
    video_id = "delTestVid1"
    storage_cleanup.append(video_id)
    s3.put_bytes(
        settings.media_bucket, keys.video_playback(video_id), b"x", content_type="video/mp4"
    )
    s3.put_bytes(
        settings.media_bucket,
        keys.video_thumbnail(video_id, "auto_1"),
        b"y",
        content_type="image/jpeg",
    )
    s3.put_bytes(
        settings.uploads_bucket, keys.video_source(video_id), b"z", content_type="video/mp4"
    )

    first = maintenance.delete_video_objects(video_id)
    second = maintenance.delete_video_objects(video_id)

    assert first == 2
    assert second == 0
    assert s3.head(settings.media_bucket, keys.video_playback(video_id)) is None
    assert s3.head(settings.uploads_bucket, keys.video_source(video_id)) is None


def test_celery_beat_schedules_the_housekeeping_tasks() -> None:
    from app.workers.celery_app import celery_app

    tasks = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}

    assert tasks == {"app.workers.tasks.cleanup_stale_drafts", "app.workers.tasks.watchdog"}
