"""Demo data: `python -m app.cli.seed` (run by deploy.sh inside the api container).

Creates demo accounts, channels and short videos so the app can be explored right
after deployment. Clips are generated locally with ffmpeg's built-in test sources
(no internet downloads, no third-party media) and stored in MinIO exactly where real
processed videos live. Idempotent: does nothing if the demo admin already exists.
"""

from __future__ import annotations

import logging
import random
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import get_sessionmaker
from app.models import (
    Channel,
    Comment,
    Playlist,
    PlaylistVideo,
    Report,
    Subscription,
    User,
    Video,
    VideoPermission,
    VideoReaction,
)
from app.models.enums import ROLE_IDS, ReportReason, RoleName, VideoStatus, Visibility
from app.storage import keys, s3
from app.workers import ffmpeg

logger = logging.getLogger("seed")

DEMO_PASSWORD = "demo-password-123"  # noqa: S105 - documented demo credential
CLIP_SECONDS = 8

USERS = [
    ("admin@example.com", "admin", "Site Admin", RoleName.ADMIN),
    ("moderator@example.com", "moderator", "Moderation Team", RoleName.MODERATOR),
    ("alice@example.com", "alice_cooks", "Alice Cooks", RoleName.USER),
    ("bob@example.com", "bob_codes", "Bob Codes", RoleName.USER),
    ("carol@example.com", "carol_travels", "Carol Travels", RoleName.USER),
    ("viewer@example.com", "viewer", "Demo Viewer", RoleName.USER),
]

# (channel handle, title, description, lavfi source, visibility)
VIDEOS = [
    ("alice_cooks", "Azerbaijani plov recipe step by step", "Saffron rice, lamb and dried fruit.", "testsrc2", Visibility.PUBLIC),
    ("alice_cooks", "Quick breakfast ideas in 5 minutes", "Three easy breakfasts.", "smptehdbars", Visibility.PUBLIC),
    ("alice_cooks", "Street food tour in Ganja", "Tasting the best local snacks.", "rgbtestsrc", Visibility.PUBLIC),
    ("alice_cooks", "Family dolma recipe (private)", "Only for family members.", "yuvtestsrc", Visibility.PRIVATE),
    ("bob_codes", "Build a YouTube clone with FastAPI", "Backend architecture walkthrough.", "mandelbrot", Visibility.PUBLIC),
    ("bob_codes", "Learn Python in 10 minutes", "Variables, loops and functions.", "life", Visibility.PUBLIC),
    ("bob_codes", "PostgreSQL indexes explained", "B-tree, GIN and partial indexes.", "cellauto", Visibility.PUBLIC),
    ("bob_codes", "Docker compose for beginners", "Run a whole stack with one command.", "sierpinski", Visibility.PUBLIC),
    ("bob_codes", "Unreleased: conference talk draft", "Shared by link only.", "testsrc", Visibility.UNLISTED),
    ("carol_travels", "Morning walk through Old City Baku", "Icherisheher at sunrise.", "testsrc2", Visibility.PUBLIC),
    ("carol_travels", "Relaxing rain sounds for sleep", "Eight seconds of calm.", "smptebars", Visibility.PUBLIC),
    ("carol_travels", "Top 10 hidden places in the Caucasus", "Mountains, lakes, villages.", "mandelbrot", Visibility.PUBLIC),
]  # fmt: skip

COMMENTS = [
    "Great video, thanks!",
    "This is exactly what I was looking for.",
    "Can you make a longer version?",
    "Subscribed!",
    "The explanation at the start is really clear.",
    "Watching this from Baku :)",
]


def _generate_clip(path: Path, source: str, frequency: int) -> None:
    """A short H.264/AAC clip from ffmpeg's built-in test sources (no input files)."""
    cmd = [
        ffmpeg.FFMPEG,
        "-hide_banner", "-nostdin", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"{source}=size=1280x720:rate=30",
        "-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=44100",
        "-t", str(CLIP_SECONDS),
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-shortest",
        "-movflags", "+faststart",
        str(path),
    ]  # fmt: skip
    subprocess.run(cmd, check=True, timeout=120, capture_output=True)  # noqa: S603


def _store_media(video: Video, workdir: Path, source: str, frequency: int) -> None:
    settings = get_settings()
    clip = workdir / f"{video.id}.mp4"
    _generate_clip(clip, source, frequency)
    s3.upload_file(
        settings.media_bucket, keys.video_playback(video.id), str(clip), content_type="video/mp4"
    )
    for choice, fraction in (("auto_1", 0.25), ("auto_2", 0.5), ("auto_3", 0.75)):
        frame = workdir / f"{video.id}-{choice}.jpg"
        ffmpeg.extract_frame(clip, frame, CLIP_SECONDS * fraction)
        s3.upload_file(
            settings.media_bucket,
            keys.video_thumbnail(video.id, choice),
            str(frame),
            content_type="image/jpeg",
        )
    video.playback_key = keys.video_playback(video.id)
    video.thumbnail_key = keys.video_thumbnail(video.id, "auto_2")
    video.playback_size_bytes = clip.stat().st_size
    video.duration_seconds = CLIP_SECONDS
    video.width, video.height = 1280, 720


def seed(db: Session) -> bool:
    if db.scalar(select(User.id).where(User.email == USERS[0][0])) is not None:
        logger.info("Demo data already present; nothing to do")
        return False

    rng = random.Random(42)  # deterministic demo data  # noqa: S311
    now = datetime.now(UTC)
    password_hash = hash_password(DEMO_PASSWORD)

    users: dict[str, User] = {}
    for email, handle, name, role in USERS:
        user = User(email=email, password_hash=password_hash, role_id=ROLE_IDS[role])
        user.channel = Channel(handle=handle, name=name, description=f"Welcome to {name}!")
        db.add(user)
        users[handle] = user
    db.flush()

    videos: list[Video] = []
    with tempfile.TemporaryDirectory() as tmp:
        for index, (handle, title, description, source, visibility) in enumerate(VIDEOS):
            channel = users[handle].channel
            video = Video(
                channel_id=channel.id,
                title=title,
                description=description,
                visibility=visibility,
                status=VideoStatus.READY,
                published_at=now - timedelta(days=index * 2 + 1, hours=rng.randint(0, 20)),
                view_count=rng.randint(40, 25_000),
            )
            db.add(video)
            db.flush()
            _store_media(video, Path(tmp), source, 220 + index * 40)
            videos.append(video)
            logger.info("Seeded video %s: %s", video.id, title)

    viewers = list(users.values())
    for video in videos:
        for viewer in rng.sample(viewers, k=rng.randint(1, len(viewers))):
            value = 1 if rng.random() < 0.85 else -1
            db.add(VideoReaction(user_id=viewer.id, video_id=video.id, value=value))
            video.like_count += value > 0
            video.dislike_count += value < 0
        for author in rng.sample(viewers, k=rng.randint(1, 3)):
            db.add(Comment(video_id=video.id, author_id=author.id, body=rng.choice(COMMENTS)))
            video.comment_count += 1

    for subscriber in viewers:
        for creator in ("alice_cooks", "bob_codes", "carol_travels"):
            if subscriber is not users[creator] and rng.random() < 0.7:
                db.add(
                    Subscription(subscriber_id=subscriber.id, channel_id=users[creator].channel.id)
                )
                users[creator].channel.subscriber_count += 1

    # Private video shared with the demo viewer only.
    private = next(v for v in videos if v.visibility == Visibility.PRIVATE)
    db.add(
        VideoPermission(
            video_id=private.id, user_id=users["viewer"].id, granted_by_id=users["alice_cooks"].id
        )
    )

    # A hidden video with a resolved report, plus an open report for the moderation queue.
    hidden = videos[7]
    hidden.is_hidden, hidden.hidden_at = True, now
    db.add(
        Report(
            video_id=videos[5].id,
            reporter_id=users["viewer"].id,
            reason=ReportReason.SPAM,
            details="Looks like spam to me",
        )
    )

    playlist = Playlist(
        channel_id=users["bob_codes"].channel.id,
        title="Backend basics",
        visibility=Visibility.PUBLIC,
    )
    db.add(playlist)
    db.flush()
    for position, video in enumerate(v for v in videos[4:8]):
        db.add(PlaylistVideo(playlist_id=playlist.id, video_id=video.id, position=position))

    db.commit()
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with get_sessionmaker()() as db:
        created = seed(db)
    print(  # CLI output
        "Demo data created." if created else "Demo data already present.",
        f"Demo password for all accounts: {DEMO_PASSWORD}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
