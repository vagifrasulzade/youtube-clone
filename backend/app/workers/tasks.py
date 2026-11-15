"""Celery task wrappers. Business logic lives in plain modules (testable directly)."""

from __future__ import annotations

from app.db.session import get_sessionmaker
from app.storage.s3 import StorageError
from app.workers import maintenance
from app.workers.celery_app import celery_app
from app.workers.queue import DELETE_VIDEO_OBJECTS_TASK


@celery_app.task(
    name=DELETE_VIDEO_OBJECTS_TASK,
    autoretry_for=(StorageError,),
    retry_backoff=True,
    max_retries=5,
)
def delete_video_objects(video_id: str) -> int:
    return maintenance.delete_video_objects(video_id)


@celery_app.task(name="app.workers.tasks.cleanup_stale_drafts")
def cleanup_stale_drafts() -> int:
    with get_sessionmaker()() as db:
        return len(maintenance.cleanup_stale_drafts(db))


@celery_app.task(name="app.workers.tasks.watchdog")
def watchdog() -> int:
    with get_sessionmaker()() as db:
        requeued, timed_out = maintenance.watchdog(db)
        return len(requeued) + len(timed_out)
