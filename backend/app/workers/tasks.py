"""Celery task wrappers. Business logic lives in plain modules (testable directly)."""

from __future__ import annotations

from typing import Any

from celery.signals import worker_init

from app.db.session import get_sessionmaker
from app.storage.s3 import StorageError
from app.workers import maintenance, processing
from app.workers.celery_app import celery_app
from app.workers.queue import DELETE_VIDEO_OBJECTS_TASK, PROCESS_VIDEO_TASK

PROCESS_MAX_RETRIES = 3


@worker_init.connect
def _purge_scratch(**_kwargs: Any) -> None:
    """Leftovers of a killed worker are removed at start-up (and by the watchdog)."""
    processing.purge_stale_workdirs()


@celery_app.task(name=PROCESS_VIDEO_TASK, bind=True, max_retries=PROCESS_MAX_RETRIES)
def process_video(self, video_id: str) -> str:
    """Only storage outages are retried (backoff 30 s, 60 s, 120 s); invalid media fails
    at once inside the pipeline. Duplicate deliveries are no-ops thanks to the claim."""
    with get_sessionmaker()() as db:
        try:
            return processing.process_video(db, video_id)
        except processing.TransientError as exc:
            if self.request.retries >= PROCESS_MAX_RETRIES:
                processing.give_up(db, video_id)
                return processing.Outcome.FAILED
            raise self.retry(exc=exc, countdown=30 * 2**self.request.retries) from exc


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
    processing.purge_stale_workdirs()
    with get_sessionmaker()() as db:
        requeued, timed_out = maintenance.watchdog(db)
        return len(requeued) + len(timed_out)
