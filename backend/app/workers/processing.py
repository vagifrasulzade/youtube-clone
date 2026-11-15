"""Video processing pipeline (docs/video-storage.md § 3-4).

`process_video(db, video_id)` may run any number of times for the same id:

- It claims the row with a conditional UPDATE (`queued` -> `processing`). If no row
  matches, another worker has it or it is already done, so it returns without work.
- Every later state change is again conditional on `status = 'processing'`, so a video
  deleted meanwhile (or failed by the watchdog) is never brought back.

Invalid media fails at once with a reason the owner sees in Studio. A storage outage
releases the claim (back to `queued`) and raises TransientError so the task can retry.
"""

from __future__ import annotations

import errno
import logging
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from celery.exceptions import SoftTimeLimitExceeded
from redis import RedisError
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.redis import get_redis
from app.models import Video
from app.models.enums import VideoStatus
from app.storage import keys, s3
from app.storage.s3 import StorageError
from app.workers import ffmpeg, queue

logger = logging.getLogger(__name__)

THUMBNAIL_POINTS = (("auto_1", 0.25), ("auto_2", 0.50), ("auto_3", 0.75))
DEFAULT_THUMBNAIL = "auto_2"
PROGRESS_TTL_SECONDS = 3600
GAVE_UP_REASON = "Processing failed because storage was unavailable; please try again later"
WORKDIR_PREFIX = "proc-"
# Older than the Celery hard time limit (35 min): no live task can own such a dir.
STALE_WORKDIR_AGE_SECONDS = 40 * 60
DURATION_TOLERANCE_SECONDS = 1.0  # container vs. stream rounding


class Outcome(StrEnum):
    READY = "ready"
    FAILED = "failed"
    SKIPPED = "skipped"


class TransientError(Exception):
    """Storage trouble: the claim was released, so the task may retry later."""


@dataclass(frozen=True)
class Outputs:
    playback_size: int
    duration: float
    width: int
    height: int


def progress_key(video_id: str) -> str:
    return f"proc:{video_id}"


def process_video(db: Session, video_id: str) -> Outcome:
    if not _claim(db, video_id):
        logger.info("Video is not queued; nothing to do", extra={"video_id": video_id})
        if db.get(Video, video_id) is None:
            # Deleted while a retry waited: an earlier attempt may have uploaded some
            # output after the deletion task ran. The deletion is idempotent.
            queue.enqueue_video_deletion(video_id)
        return Outcome.SKIPPED

    settings = get_settings()
    try:
        with tempfile.TemporaryDirectory(
            prefix=WORKDIR_PREFIX, dir=settings.processing_workdir
        ) as workdir:
            outputs = _build_and_upload(video_id, Path(workdir))
    except ffmpeg.MediaError as exc:
        logger.info("Media rejected", extra={"video_id": video_id, "reason": str(exc)})
        return _fail(db, video_id, str(exc))
    except StorageError as exc:
        logger.warning("Storage unavailable during processing", extra={"video_id": video_id})
        _release(db, video_id)
        raise TransientError(video_id) from exc
    except OSError as exc:
        if exc.errno != errno.ENOSPC:
            logger.exception("Processing crashed", extra={"video_id": video_id})
            return _fail(db, video_id, "Processing failed unexpectedly; please upload again")
        logger.error("Scratch disk full during processing", extra={"video_id": video_id})
        _release(db, video_id)  # not the uploader's fault: try again later
        raise TransientError(video_id) from exc
    except SoftTimeLimitExceeded:
        return _fail(db, video_id, "Processing the file took too long")
    except Exception:  # a bug must not leave the row stuck in 'processing'
        logger.exception("Processing crashed", extra={"video_id": video_id})
        return _fail(db, video_id, "Processing failed unexpectedly; please upload again")
    finally:
        _clear_progress(video_id)

    return _publish(db, video_id, outputs)


def give_up(db: Session, video_id: str) -> None:
    """Retries are exhausted: fail the video instead of leaving it queued forever.
    Only a still-released (`queued`) row: a duplicate delivery may have claimed it."""
    db.execute(
        update(Video)
        .where(Video.id == video_id, Video.status == VideoStatus.QUEUED)
        .values(status=VideoStatus.FAILED, processing_error=GAVE_UP_REASON)
    )
    db.commit()


def _claim(db: Session, video_id: str) -> bool:
    claimed = db.scalar(
        update(Video)
        .where(Video.id == video_id, Video.status == VideoStatus.QUEUED)
        .values(
            status=VideoStatus.PROCESSING,
            processing_started_at=func.now(),
            processing_error=None,
        )
        .returning(Video.id)
    )
    db.commit()
    return claimed is not None


def _release(db: Session, video_id: str) -> None:
    db.execute(
        update(Video)
        .where(Video.id == video_id, Video.status == VideoStatus.PROCESSING)
        .values(status=VideoStatus.QUEUED, processing_started_at=None)
    )
    db.commit()


def _fail(db: Session, video_id: str, reason: str) -> Outcome:
    db.execute(
        update(Video)
        .where(Video.id == video_id, Video.status == VideoStatus.PROCESSING)
        .values(status=VideoStatus.FAILED, processing_error=reason[:500])
    )
    db.commit()
    return Outcome.FAILED


def purge_stale_workdirs(now: float | None = None) -> int:
    """Remove temp dirs left behind by a killed worker (OOM, hard time limit, SIGKILL on
    stop): the scratch volume survives restarts, unlike a tmpfs. Only dirs older than any
    task can live are removed, so this is safe while other workers share the volume."""
    root = Path(get_settings().processing_workdir or tempfile.gettempdir())
    cutoff = (now if now is not None else time.time()) - STALE_WORKDIR_AGE_SECONDS
    removed = 0
    for candidate in root.glob(f"{WORKDIR_PREFIX}*"):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISDIR(info.st_mode) and info.st_mtime < cutoff:  # never follows symlinks
            shutil.rmtree(candidate, ignore_errors=True)
            removed += 1
    if removed:
        logger.warning("Removed stale processing directories", extra={"count": removed})
    return removed


def _build_and_upload(video_id: str, workdir: Path) -> Outputs:
    started = time.monotonic()
    settings = get_settings()
    source_key = keys.video_source(video_id)
    meta = s3.head(settings.uploads_bucket, source_key)
    if meta is None:
        raise ffmpeg.MediaError("The uploaded file is no longer available; please upload again")
    if meta.size > settings.max_upload_bytes:
        raise ffmpeg.MediaError("The file is larger than the upload limit")

    source = workdir / "source"
    s3.download_file(settings.uploads_bucket, source_key, str(source))
    info = ffmpeg.probe(source)
    limit = settings.max_video_duration_seconds
    if info.duration > limit:
        raise ffmpeg.MediaError(f"The video is longer than the {_limit_label(limit)} limit")

    playback = workdir / "playback.mp4"
    remaining = settings.processing_timeout_seconds - (time.monotonic() - started)
    ffmpeg.make_playback(
        source,
        playback,
        info,
        timeout=max(1, int(remaining)),  # download + probe already used part of the budget
        on_progress=lambda percent: _report_progress(video_id, percent),
        # The header's duration can lie: also cap what ffmpeg actually writes.
        max_seconds=limit + DURATION_TOLERANCE_SECONDS,
        max_bytes=settings.max_upload_bytes,
    )
    result = ffmpeg.probe(playback)  # what viewers get: final size and duration
    if result.duration > limit + DURATION_TOLERANCE_SECONDS / 2:
        raise ffmpeg.MediaError(f"The video is longer than the {_limit_label(limit)} limit")
    if playback.stat().st_size >= settings.max_upload_bytes:
        raise ffmpeg.MediaError("The converted video is larger than the size limit")

    bucket = settings.media_bucket
    s3.upload_file(bucket, keys.video_playback(video_id), str(playback), content_type="video/mp4")
    for choice, fraction in THUMBNAIL_POINTS:
        frame = workdir / f"thumb-{choice}.jpg"
        ffmpeg.extract_frame(playback, frame, result.duration * fraction)
        s3.upload_file(
            bucket, keys.video_thumbnail(video_id, choice), str(frame), content_type="image/jpeg"
        )
    return Outputs(
        playback_size=playback.stat().st_size,
        duration=result.duration,
        width=result.width,
        height=result.height,
    )


def _limit_label(seconds: int) -> str:
    return f"{seconds // 60}-minute" if seconds % 60 == 0 else f"{seconds}-second"


def _publish(db: Session, video_id: str, outputs: Outputs) -> Outcome:
    published = db.scalar(
        update(Video)
        .where(Video.id == video_id, Video.status == VideoStatus.PROCESSING)
        .values(
            status=VideoStatus.READY,
            playback_key=keys.video_playback(video_id),
            # An owner's custom thumbnail, uploaded while processing, is kept.
            thumbnail_key=func.coalesce(
                Video.thumbnail_key, keys.video_thumbnail(video_id, DEFAULT_THUMBNAIL)
            ),
            duration_seconds=max(1, round(outputs.duration)),
            width=outputs.width,
            height=outputs.height,
            playback_size_bytes=outputs.playback_size,
            processing_error=None,
            published_at=func.coalesce(Video.published_at, func.now()),
        )
        .returning(Video.id)
    )
    db.commit()
    settings = get_settings()
    if published is None:
        # Deleted or failed while we worked: remove exactly what this run uploaded.
        logger.info("Video changed meanwhile; output discarded", extra={"video_id": video_id})
        try:
            s3.delete(settings.media_bucket, keys.video_playback(video_id))
            for choice, _ in THUMBNAIL_POINTS:
                s3.delete(settings.media_bucket, keys.video_thumbnail(video_id, choice))
        except StorageError:  # the retried deletion task removes everything of the video
            queue.enqueue_video_deletion(video_id)
        return Outcome.SKIPPED

    try:  # raw bytes are no longer needed; the lifecycle rule is the fallback
        s3.delete(settings.uploads_bucket, keys.video_source(video_id))
    except StorageError:
        logger.warning("Could not delete the raw upload", extra={"video_id": video_id})
    logger.info("Video ready", extra={"video_id": video_id})
    return Outcome.READY


def _report_progress(video_id: str, percent: int) -> None:
    try:
        get_redis().set(progress_key(video_id), percent, ex=PROGRESS_TTL_SECONDS)
    except RedisError:  # progress is best-effort; the status itself lives in PostgreSQL
        logger.debug("Could not store progress", extra={"video_id": video_id})


def _clear_progress(video_id: str) -> None:
    try:
        get_redis().delete(progress_key(video_id))
    except RedisError:
        logger.debug("Could not clear progress", extra={"video_id": video_id})
