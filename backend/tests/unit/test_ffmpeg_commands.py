"""ffmpeg command construction (no ffmpeg binary needed)."""

from pathlib import Path

import pytest

from app.workers.ffmpeg import ProbeResult, playback_command, scale_filter


def _probe(**overrides) -> ProbeResult:
    values = {
        "formats": frozenset({"mov", "mp4"}),
        "duration": 12.5,
        "width": 1280,
        "height": 720,
        "video_codec": "h264",
        "pix_fmt": "yuv420p",
        "audio_codec": "aac",
    }
    values.update(overrides)
    return ProbeResult(**values)


@pytest.mark.parametrize(
    ("overrides", "safe"),
    [
        ({}, True),
        ({"audio_codec": None}, True),
        ({"audio_codec": "mp3"}, True),
        ({"video_codec": "hevc"}, False),
        ({"video_codec": "vp9"}, False),
        ({"pix_fmt": "yuv444p"}, False),
        ({"audio_codec": "opus"}, False),
        ({"width": 3840, "height": 2160}, False),
    ],
)
def test_browser_safe_detection(overrides: dict, safe: bool) -> None:
    assert _probe(**overrides).browser_safe is safe


def test_browser_safe_input_is_remuxed_not_reencoded() -> None:
    cmd = playback_command(Path("in"), Path("out.mp4"), _probe())

    assert cmd[cmd.index("-c") + 1] == "copy"
    assert "libx264" not in cmd


def test_other_input_is_transcoded_to_h264_aac() -> None:
    cmd = playback_command(Path("in"), Path("out.mp4"), _probe(video_codec="vp9"))

    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"


@pytest.mark.parametrize("info", [_probe(), _probe(video_codec="vp9")], ids=["remux", "transcode"])
def test_every_command_is_hardened(info: ProbeResult) -> None:
    cmd = playback_command(Path("in"), Path("out.mp4"), info)

    assert cmd[cmd.index("-protocol_whitelist") + 1] == "file,pipe"  # no network/concat tricks
    assert cmd[cmd.index("-movflags") + 1] == "+faststart"  # moov first: instant seeking
    assert "-map_metadata" in cmd  # source metadata (GPS etc.) dropped
    assert cmd[-1] == "out.mp4"


def test_small_video_is_never_upscaled() -> None:
    assert "1280" not in scale_filter(640, 360)


def test_large_video_is_scaled_into_720p_box() -> None:
    assert "w=1280:h=720:force_original_aspect_ratio=decrease" in scale_filter(1920, 1080)
    assert "w=1280:h=720" in scale_filter(1080, 1920)  # portrait too


def test_every_input_is_limited_to_allowlisted_demuxers() -> None:
    """Review L5: concat/HLS/image demuxers can never open an uploaded file."""
    cmd = playback_command(Path("in"), Path("out.mp4"), _probe(video_codec="vp9"))

    whitelist = cmd[cmd.index("-format_whitelist") + 1].split(",")
    assert cmd.index("-format_whitelist") < cmd.index("-i")
    assert set(whitelist) == {"mov", "mp4", "m4a", "3gp", "3g2", "mj2", "matroska", "webm", "avi"}


def test_playback_deadline_fires_even_when_ffmpeg_prints_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review L4: a stalled process is killed by the timer, not only between progress lines."""
    import sys
    import time

    from app.workers import ffmpeg

    stall = [sys.executable, "-c", "import time; time.sleep(30)"]
    monkeypatch.setattr(ffmpeg, "playback_command", lambda *_args, **_kwargs: stall)

    started = time.monotonic()
    with pytest.raises(ffmpeg.MediaError, match="too long"):
        ffmpeg.make_playback(tmp_path / "in", tmp_path / "out.mp4", _probe(), timeout=1)

    assert time.monotonic() - started < 10


def test_output_caps_bound_what_ffmpeg_writes() -> None:
    """Review M1: the input header's duration can lie, so the output itself is capped."""
    cmd = playback_command(
        Path("in"), Path("out.mp4"), _probe(), max_seconds=7201.0, max_bytes=2048
    )

    assert cmd[cmd.index("-t") + 1] == "7201.000"
    assert cmd[cmd.index("-fs") + 1] == "2048"
    assert cmd.index("-t") > cmd.index("-i")  # an output option: limits what is written


def test_child_processes_get_no_credentials() -> None:
    """Review L2: DATABASE_URL, S3 keys etc. never reach the process parsing uploads."""
    from app.workers.ffmpeg import CHILD_ENV

    assert set(CHILD_ENV) <= {"PATH", "SYSTEMROOT", "LANG"}


def test_interrupted_playback_kills_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Review L1: Celery's soft time limit (or any error) must not leave ffmpeg running."""
    import subprocess
    import sys

    from app.workers import ffmpeg

    script = "print('out_time_us=1000000', flush=True); import time; time.sleep(60)"
    monkeypatch.setattr(
        ffmpeg, "playback_command", lambda *_a, **_k: [sys.executable, "-c", script]
    )
    started: list[subprocess.Popen[str]] = []
    real_popen = subprocess.Popen

    def recording_popen(*args: object, **kwargs: object) -> subprocess.Popen[str]:
        assert kwargs["env"] is ffmpeg.CHILD_ENV
        process = real_popen(*args, **kwargs)  # type: ignore[call-overload]
        started.append(process)
        return process

    monkeypatch.setattr(ffmpeg.subprocess, "Popen", recording_popen)

    def interrupt(_percent: int) -> None:
        raise RuntimeError("soft time limit")

    with pytest.raises(RuntimeError, match="soft time limit"):
        ffmpeg.make_playback(
            tmp_path / "in", tmp_path / "out.mp4", _probe(), timeout=60, on_progress=interrupt
        )

    [process] = started
    assert process.poll() is not None  # killed and reaped, not left running
