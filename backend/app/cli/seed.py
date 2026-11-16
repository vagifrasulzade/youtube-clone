"""Demo data: `python -m app.cli.seed [--refresh-media]` (deploy.sh runs it in the api container).

Creates demo accounts, channels, videos, comments, likes, subscriptions, playlists and
moderation examples so the app can be explored right after deployment.

Every clip is generated locally by ffmpeg: no internet downloads, no third-party media.
Each video gets its own animated background (gradients, cellular automata, fractals,
zone plates...), its own colour palette and length, and its title and channel drawn on
it, so no two demo videos (or their thumbnails) look the same. The files are stored in
MinIO exactly where processed uploads live.

Safe to run again. It only adds what is missing (new demo accounts and videos) and never
changes an existing account's password or anyone's data. Because it adds what is missing,
a demo video or account deleted or renamed in the app comes back on the next run, and
deploy.sh seeds by default (`./deploy.sh --no-seed` skips it). `--refresh-media`
re-renders the files of seeded demo videos (never real uploads) and keeps their likes,
comments, views and chosen thumbnail.

Each video is rendered and uploaded, then committed on its own. A failure part-way keeps
everything before it, removes the failed video's objects, and the next run continues.
"""

from __future__ import annotations

import logging
import random
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, update
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

logger = logging.getLogger(__name__)

# Local development only. Deployments get a random DEMO_PASSWORD from deploy.sh, and the
# seed refuses to run in production without one (security review H1).
DEV_DEMO_PASSWORD = "demo-password-123"  # noqa: S105 - development-only demo credential


def demo_password() -> str | None:
    settings = get_settings()
    if settings.demo_password is not None and settings.demo_password.get_secret_value():
        return settings.demo_password.get_secret_value()
    return None if settings.env == "production" else DEV_DEMO_PASSWORD


# --- accounts ----------------------------------------------------------------------------

# (email, handle, channel name, role) - 15 accounts: staff, a viewer and 12 creators.
USERS = [
    ("admin@example.com", "admin", "Site Admin", RoleName.ADMIN),
    ("moderator@example.com", "moderator", "Moderation Team", RoleName.MODERATOR),
    ("alice@example.com", "alice_cooks", "Alice Cooks", RoleName.USER),
    ("bob@example.com", "bob_codes", "Bob Codes", RoleName.USER),
    ("carol@example.com", "carol_travels", "Carol Travels", RoleName.USER),
    ("viewer@example.com", "viewer", "Demo Viewer", RoleName.USER),
    ("dan@example.com", "dan_fitness", "Dan Moves", RoleName.USER),
    ("elif@example.com", "elif_music", "Elif Plays Piano", RoleName.USER),
    ("farid@example.com", "farid_gaming", "Farid Plays", RoleName.USER),
    ("gulnar@example.com", "gulnar_science", "Gulnar Explains", RoleName.USER),
    ("hasan@example.com", "hasan_garage", "Hasan Garage", RoleName.USER),
    ("ilaha@example.com", "ilaha_draws", "Ilaha Draws", RoleName.USER),
    ("jamal@example.com", "jamal_football", "Jamal Football", RoleName.USER),
    ("kamila@example.com", "kamila_reads", "Kamila Reads", RoleName.USER),
    ("leyla@example.com", "leyla_tech", "Leyla Reviews Tech", RoleName.USER),
]
NON_CREATORS = {"admin", "moderator", "viewer"}


# --- videos ------------------------------------------------------------------------------


@dataclass(frozen=True)
class DemoVideo:
    handle: str
    title: str
    description: str
    visibility: Visibility = Visibility.PUBLIC
    hidden: bool = False  # hidden by a moderator
    reported: bool = False  # has an open report in the moderation queue
    shared_with: str | None = None  # a private video shared with this handle


PRIVATE, UNLISTED = Visibility.PRIVATE, Visibility.UNLISTED

VIDEOS = [
    DemoVideo("alice_cooks", "Azerbaijani plov recipe step by step", "Saffron rice, lamb and dried fruit."),
    DemoVideo("alice_cooks", "Quick breakfast ideas in 5 minutes", "Three easy breakfasts."),
    DemoVideo("alice_cooks", "Street food tour in Ganja", "Tasting the best local snacks."),
    DemoVideo("alice_cooks", "Family dolma recipe (private)", "Only for family members.", PRIVATE, shared_with="viewer"),
    DemoVideo("bob_codes", "Build a YouTube clone with FastAPI", "Backend architecture walkthrough."),
    DemoVideo("bob_codes", "Learn Python in 10 minutes", "Variables, loops and functions.", reported=True),
    DemoVideo("bob_codes", "PostgreSQL indexes explained", "B-tree, GIN and partial indexes."),
    DemoVideo("bob_codes", "Docker compose for beginners", "Run a whole stack with one command.", hidden=True),
    DemoVideo("bob_codes", "Unreleased: conference talk draft", "Shared by link only.", UNLISTED),
    DemoVideo("carol_travels", "Morning walk through Old City Baku", "Icherisheher at sunrise."),
    DemoVideo("carol_travels", "Relaxing rain sounds for sleep", "A few seconds of calm."),
    DemoVideo("carol_travels", "Top 10 hidden places in the Caucasus", "Mountains, lakes, villages."),
    DemoVideo("dan_fitness", "15-minute home workout, no equipment", "Full body, beginner friendly."),
    DemoVideo("dan_fitness", "Morning stretching routine", "Wake up your back and shoulders."),
    DemoVideo("elif_music", "Mugham on piano: Bayati Shiraz", "A classical mode on a modern instrument."),
    DemoVideo("elif_music", "Learn your first three chords", "C, F and G in one evening."),
    DemoVideo("farid_gaming", "Speedrun attempt: the forest level", "Can we beat the record today?"),
    DemoVideo("farid_gaming", "Top 5 indie games of the year", "Small studios, big ideas."),
    DemoVideo("gulnar_science", "Why is the sky blue?", "Rayleigh scattering in plain words."),
    DemoVideo("gulnar_science", "How do black holes form?", "From a dying star to an event horizon."),
    DemoVideo("hasan_garage", "Changing your car oil at home", "Tools, steps and safety."),
    DemoVideo("hasan_garage", "Electric or hybrid: which to buy?", "Costs, range and charging."),
    DemoVideo("ilaha_draws", "Watercolor sunset in 10 minutes", "Wet-on-wet technique."),
    DemoVideo("ilaha_draws", "Drawing faces: basic proportions", "The simple grid that always works."),
    DemoVideo("jamal_football", "Best goals of the season", "Long shots, volleys and headers."),
    DemoVideo("jamal_football", "Free kick technique explained", "Run-up, contact and follow-through."),
    DemoVideo("kamila_reads", "5 books that changed my life", "Short reviews, no spoilers."),
    DemoVideo("kamila_reads", "Classic Azerbaijani novels to read", "Where to start."),
    DemoVideo("leyla_tech", "Budget phone review: worth it?", "Camera, battery and speed tested."),
    DemoVideo("leyla_tech", "Setting up a home network", "Router, mesh and a guest Wi-Fi."),
    DemoVideo("leyla_tech", "Mechanical keyboards explained", "Switches, layouts and keycaps."),
]  # fmt: skip

# (channel handle, title, visibility, video titles in order)
PLAYLISTS = [
    ("bob_codes", "Backend basics", Visibility.PUBLIC, [
        "Build a YouTube clone with FastAPI", "Learn Python in 10 minutes",
        "PostgreSQL indexes explained", "Docker compose for beginners",
    ]),
    ("alice_cooks", "Azerbaijani kitchen", Visibility.PUBLIC, [
        "Azerbaijani plov recipe step by step", "Street food tour in Ganja",
        "Quick breakfast ideas in 5 minutes",
    ]),
    ("leyla_tech", "Tech for beginners", Visibility.PUBLIC, [
        "Setting up a home network", "Mechanical keyboards explained",
        "Budget phone review: worth it?",
    ]),
]  # fmt: skip

COMMENTS = [
    "Great video, thanks!",
    "This is exactly what I was looking for.",
    "Can you make a longer version?",
    "Subscribed!",
    "The explanation at the start is really clear.",
    "Watching this from Baku :)",
    "I tried it today and it worked.",
    "Please do a part two!",
    "Short and to the point. Love it.",
    "Which tools do you use?",
    "Shared this with my friends.",
    "The colours in this video are amazing.",
]
REPLIES = [
    "Thank you, glad it helped!",
    "Part two is coming soon.",
    "Good question, I will cover it next time.",
    "Thanks for watching!",
]

# --- clip rendering --------------------------------------------------------------------

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
STYLES = ("gradient", "life", "plasma", "cellauto", "sierpinski", "spectrum", "zoneplate")
# 11 palettes x 7 styles: the first 77 videos never share both style and colours.
PALETTES = [
    ("0xff6b35", "0xf7c59f", "0x2ec4b6"),
    ("0x3a0ca3", "0x4361ee", "0x4cc9f0"),
    ("0x2b9348", "0x80b918", "0xd4d700"),
    ("0xd00000", "0xffba08", "0x3f88c5"),
    ("0x6a4c93", "0xf15bb5", "0xfee440"),
    ("0x003049", "0xd62828", "0xf77f00"),
    ("0x264653", "0x2a9d8f", "0xe9c46a"),
    ("0x8338ec", "0x3a86ff", "0xff006e"),
    ("0x0b132b", "0x5bc0be", "0xffffff"),
    ("0x582f0e", "0xb6ad90", "0xa68a64"),
    ("0x10002b", "0x9d4edd", "0xe0aaff"),
]
# ffmpeg pseudocolor presets: grey patterns (zone plates, fractals) get a colour map.
COLOR_MAPS = (
    "turbo", "magma", "viridis", "plasma", "cool", "spectral",
    "inferno", "heat", "cividis", "fiery", "helix",
)  # fmt: skip
CELLAUTO_RULES = (30, 90, 110, 150, 182)


def clip_seconds(index: int) -> int:
    """6-14 s, so the duration badges differ too."""
    return 6 + (index * 5) % 9


def _rgb(color: str) -> tuple[int, int, int]:
    value = int(color, 16)
    return value >> 16 & 255, value >> 8 & 255, value & 255


def background(index: int) -> str:
    """A lavfi source graph (1280x720, 30 fps) that is different for every index."""
    style = STYLES[index % len(STYLES)]
    a, b, c = PALETTES[index % len(PALETTES)]
    hue = index * 47 % 360
    big = "scale=1280:720:flags=neighbor"
    if style == "gradient":
        return (
            f"gradients=s=1280x720:r=30:nb_colors=3:c0={a}:c1={b}:c2={c}"
            f":speed={0.01 + index % 4 * 0.01:.2f}:seed={index}"
        )
    if style == "life":
        return (
            f"life=s=320x180:r=15:ratio=0.{2 + index % 5}:mold=8:seed={index}"
            f":life_color={b}:death_color={a}:mold_color={c},{big},fps=30"
        )
    if style == "plasma":
        # Moving sine-wave colour fields; geq works on RGB, small then scaled (fast).
        fx, fy, fz = 9 + index % 7, 11 + index % 5, 15 + index % 9
        red, _, blue = _rgb(c)
        variant = index % 3
        if variant == 0:
            channels = (
                f"r='128+120*sin(X/{fx}+T*2)':g='128+120*sin(Y/{fy}+T*1.3)'"
                f":b='128+120*sin((X+Y)/{fz}+T)'"
            )
        elif variant == 1:
            channels = (
                f"r='128+120*sin(hypot(X-160\\,Y-90)/{fx}-T*3)':g='128+120*cos(X/{fy}+T)'"
                f":b='{blue}'"
            )
        else:
            channels = f"r='{red}':g='128+120*sin(hypot(X-80\\,Y-45)/{fx}-T*2)':b='128+120*sin(Y/{fy}+T*2)'"
        return f"color=s=320x180:r=30:c=black,format=rgb24,geq={channels},scale=1280:720"
    if style == "cellauto":
        r, g, bl = _rgb(b)
        return (
            f"cellauto=s=320x180:r=30:rule={CELLAUTO_RULES[index % len(CELLAUTO_RULES)]}"
            f":seed={index},{big},lutrgb=r='val*{r}/255':g='val*{g}/255':b='val*{bl}/255'"
        )
    if style == "sierpinski":
        if index % 2:
            return (
                f"sierpinski=s=1280x720:r=30:seed={index}:type=carpet"
                f",pseudocolor=p={COLOR_MAPS[index % len(COLOR_MAPS)]}"
            )
        # Triangles are thin lines on black: invert, then tint the (now white) area with
        # the palette colour; colour maps would keep it near white.
        r, g, bl = _rgb(c)
        return (
            f"sierpinski=s=1280x720:r=30:seed={index}:type=triangle,negate"
            f",lutrgb=r='val*{r}/255':g='val*{g}/255':b='val*{bl}/255'"
        )
    if style == "spectrum":
        kind = ("black", "white", "all")[index % 3]
        return f"colorspectrum=s=1280x720:r=30:type={kind},scroll=h=0.003,hue=h={hue}"
    # Broad, slowly moving rings (fine rings average out to grey on small thumbnails).
    return (
        f"zoneplate=s=1280x720:r=30:kx2={12 + index % 5 * 7}:ky2={12 + index % 4 * 8}"
        f":kt={5 + index % 7},pseudocolor=p={COLOR_MAPS[(index + 3) % len(COLOR_MAPS)]}"
    )


def _font(name: str) -> str:
    path = FONT_DIR / name
    return f"fontfile={path}" if path.exists() else "font=Sans"  # fontconfig fallback


# A quote ends the quoted value; a colon or backslash would still be parsed after ffmpeg
# strips one level of quoting. They only occur in Windows paths, and the seed runs in the
# Linux container.
_UNSAFE_IN_FILTER = frozenset("'\\:")
THUMBNAIL_POINTS = (("auto_1", 0.25), ("auto_2", 0.5), ("auto_3", 0.75))


def overlay(title_file: Path, channel_file: Path) -> str:
    """Title in the middle, channel name in a bar at the bottom (as a thumbnail reads).

    The text is read from files, so titles need no escaping; the file paths themselves are
    server-made and refused if they contain filtergraph metacharacters.
    """
    for path in (title_file, channel_file):
        if _UNSAFE_IN_FILTER & set(str(path)):
            raise ValueError(f"unsupported characters for an ffmpeg filter path: {path}")
    return (
        "drawbox=x=0:y=ih-90:w=iw:h=90:color=black@0.55:t=fill,"
        f"drawtext={_font('DejaVuSans-Bold.ttf')}:textfile='{title_file}':fontsize=64"
        ":fontcolor=white:line_spacing=14:x=(w-text_w)/2:y=(h-text_h)/2-30"
        ":box=1:boxcolor=black@0.45:boxborderw=28,"
        f"drawtext={_font('DejaVuSans.ttf')}:textfile='{channel_file}':fontsize=34"
        ":fontcolor=white:x=40:y=h-62"
    )


def render_clip(path: Path, index: int, title: str, channel: str) -> int:
    """Render one demo clip (H.264/AAC MP4). Returns its duration in seconds.

    Inputs are lavfi graphs built in this module (no files or URLs are opened). ffmpeg gets
    the same minimal environment as the processing worker, so no credentials reach it.
    """
    seconds = clip_seconds(index)
    title_file = path.with_suffix(".title.txt")
    channel_file = path.with_suffix(".channel.txt")
    title_file.write_text(textwrap.fill(title, width=26), encoding="utf-8")
    channel_file.write_text(channel, encoding="utf-8")
    cmd = [
        ffmpeg.FFMPEG,
        "-hide_banner", "-nostdin", "-y", "-v", "error",
        "-f", "lavfi", "-i", background(index),
        "-f", "lavfi", "-i", f"sine=frequency={180 + index * 37 % 520}:sample_rate=44100",
        "-t", str(seconds),
        # Some sources (zone plates) are full range: always publish limited-range yuv420p.
        "-vf", f"{overlay(title_file, channel_file)},scale=out_range=tv,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-shortest",
        "-movflags", "+faststart",
        str(path),
    ]  # fmt: skip
    result = subprocess.run(  # noqa: S603 - fixed binary, list args, graphs built here
        cmd, capture_output=True, text=True, timeout=300, check=False, env=ffmpeg.CHILD_ENV
    )
    if result.returncode != 0:
        logger.error("ffmpeg could not render demo clip %d: %s", index, result.stderr[-1500:])
        raise RuntimeError(f"rendering demo clip {index} failed")
    return seconds


@dataclass(frozen=True)
class Media:
    seconds: int
    size: int


def _render_and_upload(
    video_id: str, title: str, channel_name: str, index: int, workdir: Path
) -> Media:
    """Render the clip and its thumbnails locally first, then upload: a render failure
    uploads nothing, so storage and the database cannot disagree because of it."""
    settings = get_settings()
    clip = workdir / f"{video_id}.mp4"
    seconds = render_clip(clip, index, title, channel_name)
    frames: dict[str, Path] = {}
    for choice, fraction in THUMBNAIL_POINTS:
        frames[choice] = workdir / f"{video_id}-{choice}.jpg"
        ffmpeg.extract_frame(clip, frames[choice], seconds * fraction)
    s3.upload_file(
        settings.media_bucket, keys.video_playback(video_id), str(clip), content_type="video/mp4"
    )
    for choice, frame in frames.items():
        s3.upload_file(
            settings.media_bucket,
            keys.video_thumbnail(video_id, choice),
            str(frame),
            content_type="image/jpeg",
        )
    return Media(seconds=seconds, size=clip.stat().st_size)


def _apply_media(video: Video, media: Media) -> None:
    video.playback_key = keys.video_playback(video.id)
    # A thumbnail chosen in Studio (auto_1/2/3 or custom) survives a re-render.
    video.thumbnail_key = video.thumbnail_key or keys.video_thumbnail(video.id, "auto_2")
    video.playback_size_bytes = media.size
    video.duration_seconds = media.seconds
    video.width, video.height = 1280, 720
    video.updated_at = datetime.now(UTC)  # new ?v= so browsers fetch the new thumbnail


def _discard_objects(video_id: str) -> None:
    try:
        s3.delete_prefix(get_settings().media_bucket, keys.video_prefix(video_id))
    except Exception:  # best effort; the error that stopped the seed is what matters
        logger.exception("Could not remove the objects of failed demo video %s", video_id)


def _is_seeded(video: Video) -> bool:
    """Demo videos have no raw upload; a real upload by a demo account is never touched."""
    return video.source_key is None and video.status == VideoStatus.READY


# --- seeding -----------------------------------------------------------------------------


@dataclass
class SeedResult:
    users: int = 0
    videos: int = 0
    refreshed: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.users or self.videos or self.refreshed)


def _ensure_users(db: Session, password: str) -> tuple[dict[str, User], set[str]]:
    users: dict[str, User] = {}
    created: set[str] = set()
    password_hash: str | None = None
    for email, handle, name, role in USERS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:  # existing accounts keep their password (reset_password changes it)
            password_hash = password_hash or hash_password(password)
            user = User(email=email, password_hash=password_hash, role_id=ROLE_IDS[role])
            user.channel = Channel(handle=handle, name=name, description=f"Welcome to {name}!")
            db.add(user)
            created.add(handle)
        users[handle] = user
    db.flush()
    return users, created


def _engage(
    db: Session, video: Video, users: list[User], rng: random.Random, now: datetime
) -> None:
    """Likes, comments and a few creator replies. Counters equal the rows they count."""
    for viewer in rng.sample(users, k=rng.randint(2, len(users))):
        value = 1 if rng.random() < 0.85 else -1
        db.add(VideoReaction(user_id=viewer.id, video_id=video.id, value=value))
        video.like_count += value > 0
        video.dislike_count += value < 0
    published = video.published_at or now
    span = (now - published).total_seconds()
    creator = next(u for u in users if u.channel.id == video.channel_id)
    for author in rng.sample(users, k=rng.randint(1, 4)):
        # Between publishing and now; a reply lands between its parent and now.
        at = published + timedelta(seconds=span * rng.uniform(0.05, 0.7))
        comment = Comment(
            video_id=video.id, author_id=author.id, body=rng.choice(COMMENTS), created_at=at
        )
        db.add(comment)
        video.comment_count += 1
        if author is not creator and rng.random() < 0.35:
            db.flush()
            db.add(
                Comment(
                    video_id=video.id,
                    author_id=creator.id,
                    parent_id=comment.id,
                    body=rng.choice(REPLIES),
                    created_at=at + (now - at) * rng.uniform(0.1, 0.9),
                )
            )
            comment.reply_count += 1
            video.comment_count += 1


def _subscribe(db: Session, users: dict[str, User], created: set[str], rng: random.Random) -> None:
    """Random follows; only pairs involving a newly created account (re-runs add none)."""
    creators = [h for h in users if h not in NON_CREATORS]
    for subscriber_handle, subscriber in users.items():
        for creator_handle in creators:
            if subscriber_handle == creator_handle:
                continue
            if subscriber_handle not in created and creator_handle not in created:
                continue
            if rng.random() < 0.55:
                channel_id = users[creator_handle].channel.id
                db.add(Subscription(subscriber_id=subscriber.id, channel_id=channel_id))
                # Atomic: channels that already exist may be followed through the API
                # while the seed runs (CLAUDE.md rule 5).
                db.execute(
                    update(Channel)
                    .where(Channel.id == channel_id)
                    .values(subscriber_count=Channel.subscriber_count + 1)
                )


def _moderation_and_sharing(
    db: Session, demo: DemoVideo, video: Video, users: dict[str, User], now: datetime
) -> None:
    if demo.hidden:
        video.is_hidden, video.hidden_at = True, now
    if demo.reported:
        db.add(
            Report(
                video_id=video.id,
                reporter_id=users["viewer"].id,
                reason=ReportReason.SPAM,
                details="Looks like spam to me",
            )
        )
    if demo.shared_with:
        db.add(
            VideoPermission(
                video_id=video.id,
                user_id=users[demo.shared_with].id,
                granted_by_id=users[demo.handle].id,
            )
        )


def _ensure_playlists(db: Session, users: dict[str, User], videos: dict[str, Video]) -> None:
    for handle, title, visibility, titles in PLAYLISTS:
        channel = users[handle].channel
        playlist = db.scalar(
            select(Playlist).where(Playlist.channel_id == channel.id, Playlist.title == title)
        )
        if playlist is not None:
            continue
        playlist = Playlist(channel_id=channel.id, title=title, visibility=visibility)
        db.add(playlist)
        db.flush()
        for position, video_title in enumerate(t for t in titles if t in videos):
            db.add(
                PlaylistVideo(
                    playlist_id=playlist.id, video_id=videos[video_title].id, position=position
                )
            )


def seed(db: Session, password: str, *, refresh_media: bool = False) -> SeedResult:
    rng = random.Random(42)  # deterministic demo data  # noqa: S311
    now = datetime.now(UTC)
    result = SeedResult()
    users, created = _ensure_users(db, password)
    db.commit()
    result.users = len(created)
    everyone = list(users.values())

    videos: dict[str, Video] = {}
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        for index, demo in enumerate(VIDEOS):
            channel = users[demo.handle].channel
            existing = db.scalar(
                select(Video).where(Video.channel_id == channel.id, Video.title == demo.title)
            )
            if existing is not None:
                videos[demo.title] = existing
                if refresh_media and _is_seeded(existing):
                    media = _render_and_upload(
                        existing.id, demo.title, channel.name, index, workdir
                    )
                    _apply_media(existing, media)
                    db.commit()  # files and metadata agree from here on
                    result.refreshed += 1
                    logger.info("Re-rendered video %s: %s", existing.id, demo.title)
                continue
            video = Video(
                channel_id=channel.id,
                title=demo.title,
                description=demo.description,
                visibility=demo.visibility,
                status=VideoStatus.READY,
                published_at=now - timedelta(days=index + 1, hours=rng.randint(0, 20)),
                view_count=rng.randint(40, 60_000),
            )
            db.add(video)
            db.flush()
            video_id = video.id
            try:
                media = _render_and_upload(video_id, demo.title, channel.name, index, workdir)
            except Exception:
                db.rollback()  # earlier videos are already committed
                _discard_objects(video_id)
                raise
            _apply_media(video, media)
            _engage(db, video, everyone, rng, now)
            _moderation_and_sharing(db, demo, video, users, now)
            db.commit()
            videos[demo.title] = video
            result.videos += 1
            logger.info("Seeded video %s: %s", video_id, demo.title)

    _subscribe(db, users, created, rng)
    _ensure_playlists(db, users, videos)
    db.commit()
    return result


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if any(arg not in ("--refresh-media",) for arg in args):
        print("usage: python -m app.cli.seed [--refresh-media]", file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    password = demo_password()
    if password is None:
        print("Refusing to seed: set DEMO_PASSWORD (deploy.sh generates one).", file=sys.stderr)
        return 1
    with get_sessionmaker()() as db:
        result = seed(db, password, refresh_media="--refresh-media" in args)
    if result.changed:
        print(
            f"Demo data: {result.users} new accounts, {result.videos} new videos, "
            f"{result.refreshed} videos re-rendered."
        )
    else:
        print("Demo data already present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
