"""ffprobe/ffmpeg wrappers for untrusted media (docs/security.md § 6).

Hardening applied to EVERY invocation:
- argument lists, never a shell; paths are server-generated temp files
- `-protocol_whitelist file` (plus `pipe` for progress output) so a crafted playlist or
  concat file cannot make ffmpeg read other local files or fetch URLs
- the container format must be in an allowlist before anything is decoded
- wall-clock timeouts on every process
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

# ffprobe `format_name` values we accept (it reports e.g. "mov,mp4,m4a,3gp,3g2,mj2").
ALLOWED_FORMATS = frozenset({"mov", "mp4", "m4a", "3gp", "3g2", "mj2", "matroska", "webm", "avi"})
BROWSER_SAFE_VIDEO = frozenset({"h264"})
BROWSER_SAFE_PIX_FMT = frozenset({"yuv420p", "yuvj420p"})
BROWSER_SAFE_AUDIO = frozenset({"aac", "mp3"})
MAX_WIDTH, MAX_HEIGHT = 1280, 720  # single 720p rendition (docs/video-storage.md § 4)
MAX_DIMENSION = 8192


class MediaError(Exception):
    """The input is not acceptable media. The message is shown to the owner; never retried."""


@dataclass(frozen=True)
class ProbeResult:
    formats: frozenset[str]
    duration: float
    width: int
    height: int
    video_codec: str
    pix_fmt: str | None
    audio_codec: str | None

    @property
    def browser_safe(self) -> bool:
        """H.264 4:2:0 (+ AAC/MP3 or no audio) can be remuxed into MP4 without re-encoding."""
        return (
            self.video_codec in BROWSER_SAFE_VIDEO
            and self.pix_fmt in BROWSER_SAFE_PIX_FMT
            and (self.audio_codec is None or self.audio_codec in BROWSER_SAFE_AUDIO)
            and self.width <= 1920
            and self.height <= 1920
        )


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603 - fixed binaries, list args, server paths
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError("Processing the file took too long") from exc


def probe(path: Path, *, timeout: int = 60) -> ProbeResult:
    result = _run(
        [
            FFPROBE,
            "-v", "error",
            "-protocol_whitelist", "file",
            "-show_format",
            "-show_streams",
            "-of", "json",
            str(path),
        ],
        timeout,
    )  # fmt: skip
    if result.returncode != 0:
        raise MediaError("The file could not be read as a video")
    try:
        data = json.loads(result.stdout)
        fmt = data["format"]
        streams = data.get("streams", [])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise MediaError("The file could not be read as a video") from exc

    formats = frozenset(str(fmt.get("format_name", "")).split(","))
    if not formats & ALLOWED_FORMATS:
        raise MediaError("Unsupported video container")

    videos = [
        s
        for s in streams
        if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
    ]
    if not videos:
        raise MediaError("The file has no video track")
    video = videos[0]
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    try:
        duration = float(fmt.get("duration") or video.get("duration") or 0)
        width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    except (TypeError, ValueError) as exc:
        raise MediaError("The file has invalid video metadata") from exc
    if duration <= 0:
        raise MediaError("Could not determine the video duration")
    if not (16 <= width <= MAX_DIMENSION and 16 <= height <= MAX_DIMENSION):
        raise MediaError("Unsupported video resolution")

    return ProbeResult(
        formats=formats,
        duration=duration,
        width=width,
        height=height,
        video_codec=str(video.get("codec_name", "")),
        pix_fmt=video.get("pix_fmt"),
        audio_codec=str(audio["codec_name"]) if audio and audio.get("codec_name") else None,
    )


def scale_filter(width: int, height: int) -> str:
    """Downscale into a 1280x720 box (never upscale); keep dimensions even for H.264."""
    if width <= MAX_WIDTH and height <= MAX_HEIGHT:
        return "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    return (
        f"scale=w={MAX_WIDTH}:h={MAX_HEIGHT}:force_original_aspect_ratio=decrease,"
        "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    )


def playback_command(src: Path, dst: Path, info: ProbeResult) -> list[str]:
    cmd = [
        FFMPEG,
        "-hide_banner", "-nostdin", "-y", "-v", "error",
        "-protocol_whitelist", "file,pipe",
        "-i", str(src),
        "-map", "0:v:0", "-map", "0:a:0?",
        "-sn", "-dn", "-map_metadata", "-1",
        "-progress", "pipe:1", "-nostats",
    ]  # fmt: skip
    if info.browser_safe:
        cmd += ["-c", "copy"]  # remux: seconds instead of minutes, no quality loss
    else:
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-vf", scale_filter(info.width, info.height),
            "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        ]  # fmt: skip
    cmd += ["-movflags", "+faststart", "-f", "mp4", str(dst)]  # moov atom first: instant seek
    return cmd


def make_playback(
    src: Path,
    dst: Path,
    info: ProbeResult,
    *,
    timeout: int,
    on_progress: Callable[[int], None] | None = None,
) -> None:
    """Remux or transcode to a progressive MP4, reporting progress (0-99)."""
    cmd = playback_command(src, dst, info)
    deadline = time.monotonic() + timeout
    stderr_path = dst.with_suffix(".stderr.log")
    with stderr_path.open("w") as stderr:
        process = subprocess.Popen(  # noqa: S603 - fixed binary, list args
            cmd, stdout=subprocess.PIPE, stderr=stderr, text=True
        )
        if process.stdout is None:  # cannot happen with stdout=PIPE; keeps type checkers happy
            raise MediaError("The video could not be converted")
        last_reported = -1
        for line in process.stdout:
            if time.monotonic() > deadline:
                process.kill()
                process.wait()
                raise MediaError("Processing the file took too long")
            key, _, value = line.strip().partition("=")
            if key == "out_time_us" and value.isdigit() and on_progress is not None:
                percent = min(99, int(int(value) / 1_000_000 / info.duration * 100))
                if percent > last_reported:
                    last_reported = percent
                    on_progress(percent)
        try:
            returncode = process.wait(timeout=max(1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            process.kill()
            raise MediaError("Processing the file took too long") from exc
    if returncode != 0:
        logger.warning("ffmpeg failed: %s", stderr_path.read_text()[-2000:])
        raise MediaError("The video could not be converted")


def extract_frame(src: Path, dst: Path, at_seconds: float, *, timeout: int = 60) -> None:
    """One 1280x720 JPEG frame (letter-boxed) at `at_seconds`."""
    result = _run(
        [
            FFMPEG,
            "-hide_banner", "-nostdin", "-y", "-v", "error",
            "-protocol_whitelist", "file",
            "-ss", f"{max(0.0, at_seconds):.3f}",
            "-i", str(src),
            "-frames:v", "1",
            "-vf", (
                f"scale={MAX_WIDTH}:{MAX_HEIGHT}:force_original_aspect_ratio=decrease,"
                f"pad={MAX_WIDTH}:{MAX_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black"
            ),
            "-q:v", "3",
            str(dst),
        ],
        timeout,
    )  # fmt: skip
    if result.returncode != 0 or not dst.exists():
        raise MediaError("Could not generate a thumbnail")
