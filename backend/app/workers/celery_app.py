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
    broker_connection_retry_on_startup=True,
    timezone="UTC",
)
