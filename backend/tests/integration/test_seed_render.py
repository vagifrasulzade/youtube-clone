"""The demo clips really render: every background style is accepted by ffmpeg.

Needs ffmpeg (skipped with a reason elsewhere); scripts/test.sh and CI provide it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.cli import seed
from app.workers import ffmpeg

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="needs ffmpeg/ffprobe (run scripts/test.sh or CI)",
)


@pytest.mark.parametrize("index", range(len(seed.STYLES)))  # one video of every style
def test_each_style_renders_a_playable_clip(tmp_path: Path, index: int) -> None:
    demo = seed.VIDEOS[index]
    clip = tmp_path / "clip.mp4"

    seconds = seed.render_clip(clip, index, demo.title, "Demo Channel")

    info = ffmpeg.probe(clip)
    assert (info.video_codec, info.pix_fmt, info.audio_codec) == ("h264", "yuv420p", "aac")
    assert (info.width, info.height) == (1280, 720)
    assert abs(info.duration - seconds) < 0.5
    frame = tmp_path / "thumb.jpg"
    ffmpeg.extract_frame(clip, frame, seconds / 2)
    assert frame.stat().st_size > 10_000  # a real picture, not a blank frame
