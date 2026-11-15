"""Processing failure paths that need no ffmpeg (review findings on stage 5).

The guarantees under test: a video never stays stuck in `processing`, transient trouble
is retried, and nothing of a deleted video is left in storage.
"""

from __future__ import annotations

import dataclasses
import errno
import os
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Video
from app.models.enums import VideoStatus
from app.storage import keys, s3
from app.storage.s3 import StorageError
from app.workers import ffmpeg, processing
from tests.factories import create_user, create_video
from tests.storage_helpers import FAKE_MP4


@pytest.fixture
def video(
    db_session: Session, storage_cleanup: list[str], monkeypatch: pytest.MonkeyPatch
) -> Video:
    monkeypatch.setattr(processing, "_clear_progress", lambda _video_id: None)
    video = create_video(db_session, create_user(db_session).channel, status=VideoStatus.QUEUED)
    storage_cleanup.append(video.id)
    s3.put_bytes(
        get_settings().uploads_bucket,
        keys.video_source(video.id),
        FAKE_MP4,
        content_type="video/mp4",
    )
    return video


def _probe_ok(*_args: object, **_kwargs: object) -> ffmpeg.ProbeResult:
    return ffmpeg.ProbeResult(
        formats=frozenset({"mp4"}), duration=2.0, width=320, height=240,
        video_codec="h264", pix_fmt="yuv420p", audio_codec=None,
    )  # fmt: skip


def _fake_playback(_src: Path, dst: Path, *_args: object, **_kwargs: object) -> None:
    dst.write_bytes(b"x" * 100)


def _raise(exc: BaseException) -> Callable[..., None]:
    def raiser(*_args: object, **_kwargs: object) -> None:
        raise exc

    return raiser


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (SoftTimeLimitExceeded(), "Processing the file took too long"),
        (RuntimeError("bug"), "Processing failed unexpectedly; please upload again"),
        (ffmpeg.MediaError("The video could not be converted"), "The video could not be converted"),
    ],
)
def test_errors_while_converting_end_in_failed(
    db_session: Session,
    video: Video,
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
    reason: str,
) -> None:
    monkeypatch.setattr(ffmpeg, "probe", _probe_ok)
    monkeypatch.setattr(ffmpeg, "make_playback", _raise(error))

    assert processing.process_video(db_session, video.id) == processing.Outcome.FAILED

    db_session.refresh(video)
    assert video.status == VideoStatus.FAILED
    assert video.processing_error == reason


def test_thumbnail_failure_ends_in_failed(
    db_session: Session, video: Video, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ffmpeg, "probe", _probe_ok)
    monkeypatch.setattr(ffmpeg, "make_playback", _fake_playback)
    monkeypatch.setattr(
        ffmpeg, "extract_frame", _raise(ffmpeg.MediaError("Could not generate a thumbnail"))
    )

    assert processing.process_video(db_session, video.id) == processing.Outcome.FAILED

    db_session.refresh(video)
    assert video.processing_error == "Could not generate a thumbnail"


def test_lying_duration_header_is_caught_on_the_output(
    db_session: Session, video: Video, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review M1: the source header claims 0.5 s, the converted file really is 2 s."""
    monkeypatch.setattr(get_settings(), "max_video_duration_seconds", 1)
    durations = iter([0.5, 2.0])
    caps: dict[str, object] = {}

    def probe(*_args: object, **_kwargs: object) -> ffmpeg.ProbeResult:
        return dataclasses.replace(_probe_ok(), duration=next(durations))

    def capped_playback(_src: Path, dst: Path, *_args: object, **kwargs: object) -> None:
        caps.update(kwargs)
        dst.write_bytes(b"x" * 100)

    monkeypatch.setattr(ffmpeg, "probe", probe)
    monkeypatch.setattr(ffmpeg, "make_playback", capped_playback)

    assert processing.process_video(db_session, video.id) == processing.Outcome.FAILED

    db_session.refresh(video)
    assert video.processing_error == "The video is longer than the 1-second limit"
    assert caps["max_seconds"] == pytest.approx(2.0)
    assert caps["max_bytes"] == get_settings().max_upload_bytes


def test_full_scratch_disk_is_retried_not_failed(
    db_session: Session, video: Video, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(s3, "download_file", _raise(OSError(errno.ENOSPC, "No space left")))

    with pytest.raises(processing.TransientError):
        processing.process_video(db_session, video.id)

    db_session.refresh(video)
    assert video.status == VideoStatus.QUEUED


def test_give_up_leaves_a_video_claimed_by_another_worker_alone(
    db_session: Session, video: Video
) -> None:
    video.status = VideoStatus.PROCESSING
    db_session.flush()

    processing.give_up(db_session, video.id)

    db_session.refresh(video)
    assert video.status == VideoStatus.PROCESSING


def test_retry_for_a_deleted_video_enqueues_storage_cleanup(
    db_session: Session, enqueued: list[tuple[str, str]]
) -> None:
    assert processing.process_video(db_session, "AAAAAAAAAAA") == processing.Outcome.SKIPPED

    assert ("delete", "AAAAAAAAAAA") in enqueued


def test_discard_falls_back_to_the_deletion_task(
    db_session: Session,
    video: Video,
    monkeypatch: pytest.MonkeyPatch,
    enqueued: list[tuple[str, str]],
) -> None:
    video_id = video.id

    def build_then_deleted(vid: str, _workdir: Path) -> processing.Outputs:
        db_session.execute(delete(Video).where(Video.id == vid))
        db_session.commit()
        return processing.Outputs(playback_size=1, duration=2.0, width=320, height=240)

    monkeypatch.setattr(processing, "_build_and_upload", build_then_deleted)
    monkeypatch.setattr(s3, "delete", _raise(StorageError()))

    assert processing.process_video(db_session, video_id) == processing.Outcome.SKIPPED

    assert ("delete", video_id) in enqueued


def test_stale_scratch_dirs_are_purged_but_live_ones_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "processing_workdir", str(tmp_path))
    stale = tmp_path / "proc-stale"
    live = tmp_path / "proc-live"
    unrelated = tmp_path / "keep-me"
    for directory in (stale, live, unrelated):
        directory.mkdir()
        (directory / "source").write_bytes(b"x")
    old = time.time() - processing.STALE_WORKDIR_AGE_SECONDS - 60
    os.utime(stale, (old, old))
    os.utime(unrelated, (old, old))

    assert processing.purge_stale_workdirs() == 1

    assert not stale.exists()
    assert live.exists()
    assert unrelated.exists()
