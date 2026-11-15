"""Video processing pipeline (docs/video-storage.md § 3-4, acceptance A6).

Runs the real ffmpeg/ffprobe on clips generated from ffmpeg's built-in test sources,
against real PostgreSQL and MinIO. Skipped (with a reason) only where ffmpeg is not
installed; scripts/test.sh (Docker) and CI both provide it.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from redis import Redis
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Video
from app.models.enums import VideoStatus
from app.storage import keys, s3
from app.storage.s3 import StorageError
from app.workers import ffmpeg, processing
from tests.factories import create_user, create_video
from tests.storage_helpers import FAKE_MP4, object_bytes

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="needs ffmpeg/ffprobe (run scripts/test.sh or CI)",
)

AUTO_THUMBS = ("auto_1", "auto_2", "auto_3")


def _make_clip(path: Path, *, size: str, video: list[str], audio: list[str]) -> Path:
    cmd = [
        ffmpeg.FFMPEG,
        "-hide_banner", "-nostdin", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "2", *video, *audio, "-shortest", str(path),
    ]  # fmt: skip
    subprocess.run(cmd, check=True, timeout=120, capture_output=True)  # noqa: S603
    return path


@pytest.fixture(scope="module")
def clips(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    tmp = tmp_path_factory.mktemp("clips")
    h264 = _make_clip(
        tmp / "safe.mp4",
        size="320x240",
        video=["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"],
        audio=["-c:a", "aac", "-b:a", "64k"],
    )
    mpeg4 = _make_clip(
        tmp / "legacy.avi",
        size="1600x900",
        video=["-c:v", "mpeg4", "-q:v", "6"],
        audio=["-c:a", "pcm_s16le"],
    )
    return {"h264": h264.read_bytes(), "mpeg4": mpeg4.read_bytes()}


@pytest.fixture(autouse=True)
def progress(monkeypatch: pytest.MonkeyPatch, redis_client: Redis) -> list[int]:
    """Progress goes to the test Redis DB; every reported value is recorded."""
    monkeypatch.setattr(processing, "get_redis", lambda: redis_client)
    seen: list[int] = []
    original = processing._report_progress

    def record(video_id: str, percent: int) -> None:
        seen.append(percent)
        original(video_id, percent)

    monkeypatch.setattr(processing, "_report_progress", record)
    return seen


@pytest.fixture
def queued_video(
    db_session: Session, storage_cleanup: list[str]
) -> Callable[[bytes | None], Video]:
    channel = create_user(db_session).channel

    def make(source: bytes | None) -> Video:
        video = create_video(db_session, channel, status=VideoStatus.QUEUED)
        video.source_key = keys.video_source(video.id)
        db_session.flush()
        storage_cleanup.append(video.id)
        if source is not None:
            s3.put_bytes(
                get_settings().uploads_bucket, video.source_key, source, content_type="video/mp4"
            )
        return video

    return make


def _media_exists(key: str) -> bool:
    return s3.head(get_settings().media_bucket, key) is not None


def _probe_playback(video_id: str, tmp_path: Path) -> ffmpeg.ProbeResult:
    local = tmp_path / "playback.mp4"
    local.write_bytes(object_bytes(get_settings().media_bucket, keys.video_playback(video_id)))
    return ffmpeg.probe(local)


def test_browser_safe_upload_is_remuxed_and_published(
    db_session: Session,
    queued_video: Callable[[bytes | None], Video],
    clips: dict[str, bytes],
    redis_client: Redis,
    tmp_path: Path,
) -> None:
    video = queued_video(clips["h264"])

    assert processing.process_video(db_session, video.id) == processing.Outcome.READY

    db_session.refresh(video)
    assert video.status == VideoStatus.READY
    assert video.processing_error is None
    assert video.published_at is not None
    assert video.playback_key == keys.video_playback(video.id)
    assert video.thumbnail_key == keys.video_thumbnail(video.id, "auto_2")
    assert (video.width, video.height, video.duration_seconds) == (320, 240, 2)
    stored = s3.head(get_settings().media_bucket, video.playback_key)
    assert stored is not None
    assert stored.size == video.playback_size_bytes
    assert stored.content_type == "video/mp4"
    assert all(_media_exists(keys.video_thumbnail(video.id, c)) for c in AUTO_THUMBS)
    result = _probe_playback(video.id, tmp_path)
    assert (result.video_codec, result.pix_fmt) == ("h264", "yuv420p")
    # The raw upload is deleted once the processed copy is published.
    assert s3.head(get_settings().uploads_bucket, keys.video_source(video.id)) is None
    assert redis_client.get(processing.progress_key(video.id)) is None


def test_other_codecs_are_transcoded_to_h264_within_720p(
    db_session: Session,
    queued_video: Callable[[bytes | None], Video],
    clips: dict[str, bytes],
    progress: list[int],
    tmp_path: Path,
) -> None:
    video = queued_video(clips["mpeg4"])

    assert processing.process_video(db_session, video.id) == processing.Outcome.READY

    db_session.refresh(video)
    assert (video.width, video.height) == (1280, 720)  # 1600x900 scaled into the box
    result = _probe_playback(video.id, tmp_path)
    assert (result.video_codec, result.pix_fmt, result.audio_codec) == ("h264", "yuv420p", "aac")
    assert progress, "transcode progress was never reported"
    assert progress == sorted(progress)
    assert all(0 <= p <= 99 for p in progress)


def test_fake_media_fails_with_a_reason_and_produces_nothing(
    db_session: Session, queued_video: Callable[[bytes | None], Video]
) -> None:
    video = queued_video(FAKE_MP4)  # has an MP4 signature but is not a video

    assert processing.process_video(db_session, video.id) == processing.Outcome.FAILED

    db_session.refresh(video)
    assert video.status == VideoStatus.FAILED
    assert video.processing_error == "The file could not be read as a video"
    assert video.playback_key is None
    assert video.published_at is None
    assert not _media_exists(keys.video_playback(video.id))
    # Kept for debugging until the bucket lifecycle rule expires it.
    assert s3.head(get_settings().uploads_bucket, keys.video_source(video.id)) is not None


def test_video_over_the_duration_limit_fails(
    db_session: Session,
    queued_video: Callable[[bytes | None], Video],
    clips: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "max_video_duration_seconds", 1)
    video = queued_video(clips["h264"])

    assert processing.process_video(db_session, video.id) == processing.Outcome.FAILED

    db_session.refresh(video)
    assert video.processing_error == "The video is longer than the 1-second limit"
    assert not _media_exists(keys.video_playback(video.id))


def test_missing_raw_upload_fails(
    db_session: Session, queued_video: Callable[[bytes | None], Video]
) -> None:
    video = queued_video(None)

    assert processing.process_video(db_session, video.id) == processing.Outcome.FAILED

    db_session.refresh(video)
    assert video.processing_error == "The uploaded file is no longer available; please upload again"


@pytest.mark.parametrize("status", [VideoStatus.PROCESSING, VideoStatus.READY, VideoStatus.FAILED])
def test_only_queued_videos_are_claimed(
    db_session: Session, queued_video: Callable[[bytes | None], Video], status: VideoStatus
) -> None:
    video = queued_video(FAKE_MP4)
    video.status = status
    db_session.flush()

    assert processing.process_video(db_session, video.id) == processing.Outcome.SKIPPED

    db_session.refresh(video)
    assert video.status == status
    assert video.processing_error is None


def test_duplicate_delivery_is_a_no_op(
    db_session: Session, queued_video: Callable[[bytes | None], Video], clips: dict[str, bytes]
) -> None:
    video = queued_video(clips["h264"])
    assert processing.process_video(db_session, video.id) == processing.Outcome.READY
    db_session.refresh(video)
    published_at = video.published_at

    assert processing.process_video(db_session, video.id) == processing.Outcome.SKIPPED

    db_session.refresh(video)
    assert video.status == VideoStatus.READY
    assert video.published_at == published_at


def test_unknown_video_id_is_skipped(db_session: Session) -> None:
    assert processing.process_video(db_session, "AAAAAAAAAAA") == processing.Outcome.SKIPPED


def test_custom_thumbnail_set_during_processing_is_kept(
    db_session: Session, queued_video: Callable[[bytes | None], Video], clips: dict[str, bytes]
) -> None:
    video = queued_video(clips["h264"])
    custom = keys.video_thumbnail(video.id, "custom")
    video.thumbnail_key = custom
    db_session.flush()

    assert processing.process_video(db_session, video.id) == processing.Outcome.READY

    db_session.refresh(video)
    assert video.thumbnail_key == custom


def test_video_deleted_during_processing_leaves_no_output(
    db_session: Session,
    queued_video: Callable[[bytes | None], Video],
    clips: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video = queued_video(clips["h264"])
    video_id = video.id
    build = processing._build_and_upload

    def build_then_owner_deletes(vid: str, workdir: Path) -> processing.Outputs:
        outputs = build(vid, workdir)
        db_session.execute(delete(Video).where(Video.id == vid))
        db_session.commit()
        return outputs

    monkeypatch.setattr(processing, "_build_and_upload", build_then_owner_deletes)

    assert processing.process_video(db_session, video_id) == processing.Outcome.SKIPPED

    db_session.expire_all()
    assert db_session.get(Video, video_id) is None
    assert not _media_exists(keys.video_playback(video_id))
    assert not any(_media_exists(keys.video_thumbnail(video_id, c)) for c in AUTO_THUMBS)


def test_storage_outage_releases_the_claim_for_a_retry(
    db_session: Session,
    queued_video: Callable[[bytes | None], Video],
    clips: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video = queued_video(clips["h264"])

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise StorageError()

    monkeypatch.setattr(s3, "download_file", unavailable)

    with pytest.raises(processing.TransientError):
        processing.process_video(db_session, video.id)

    db_session.refresh(video)
    assert video.status == VideoStatus.QUEUED  # claimable again by the retry
    assert video.processing_started_at is None

    processing.give_up(db_session, video.id)  # retries exhausted

    db_session.refresh(video)
    assert video.status == VideoStatus.FAILED
    assert video.processing_error == processing.GAVE_UP_REASON
