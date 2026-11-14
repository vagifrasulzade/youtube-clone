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
