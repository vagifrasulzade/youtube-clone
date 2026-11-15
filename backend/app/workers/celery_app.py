"""Celery application (broker: Redis). Tasks live in app.workers.tasks."""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("youtube_clone", broker=settings.redis_url, include=["app.workers.tasks"])
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_backend=None,  # results are written to PostgreSQL, not to Celery
    task_ignore_result=True,
    task_acks_late=True,  # a crashed worker's task is redelivered
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # CPU-heavy tasks: take one at a time
    # Global limits (docs/video-storage.md section 3): a runaway task is stopped, and the
    # watchdog fails 'processing' rows older than the hard limit (review L4).
    task_soft_time_limit=30 * 60,
    task_time_limit=35 * 60,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    beat_schedule={
        "cleanup-stale-drafts": {
            "task": "app.workers.tasks.cleanup_stale_drafts",
            "schedule": 3600.0,
        },
        "watchdog": {"task": "app.workers.tasks.watchdog", "schedule": 300.0},
    },
)
