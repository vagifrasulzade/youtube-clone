"""Enqueue background work. Call ONLY after the database transaction has committed,
so the worker never sees a row that does not exist yet (CLAUDE.md rule 6)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PROCESS_VIDEO_TASK = "app.workers.tasks.process_video"
DELETE_VIDEO_OBJECTS_TASK = "app.workers.tasks.delete_video_objects"


def enqueue_video_processing(video_id: str) -> bool:
    """Returns False if the broker is unreachable; the video then stays `queued` and the
    periodic watchdog re-enqueues it, so nothing is lost."""
    from app.workers.celery_app import celery_app

    try:
        celery_app.send_task(PROCESS_VIDEO_TASK, args=[video_id])
    except Exception:  # broker down: recoverable by the watchdog
        logger.exception("Could not enqueue video processing", extra={"video_id": video_id})
        return False
    return True


def enqueue_video_deletion(video_id: str) -> bool:
    from app.workers.celery_app import celery_app

    try:
        celery_app.send_task(DELETE_VIDEO_OBJECTS_TASK, args=[video_id])
    except Exception:
        logger.exception("Could not enqueue object deletion", extra={"video_id": video_id})
        return False
    return True
