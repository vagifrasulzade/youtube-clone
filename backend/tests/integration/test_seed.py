"""Demo seed against the real database (clip rendering is stubbed; see test_seed_data)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cli import seed
from app.core.security import verify_password
from app.models import (
    Channel,
    Comment,
    Playlist,
    Report,
    Subscription,
    User,
    Video,
    VideoPermission,
    VideoReaction,
)
from app.storage import keys

PASSWORD = "seed-password-123"
DEMO_EMAILS = [email for email, *_ in seed.USERS]


@pytest.fixture
def rendered(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record which videos would be rendered instead of running ffmpeg."""
    calls: list[str] = []

    def fake_store(video: Video, _workdir: Path, index: int, _channel: str) -> None:
        calls.append(video.title)
        video.playback_key = keys.video_playback(video.id)
        video.thumbnail_key = keys.video_thumbnail(video.id, "auto_2")
        video.duration_seconds = seed.clip_seconds(index)
        video.width, video.height = 1280, 720

    monkeypatch.setattr(seed, "_store_media", fake_store)
    return calls


def _count(db: Session, model: type, *where: object) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def _demo_videos(db: Session) -> list[Video]:
    return list(
        db.scalars(select(Video).join(Channel).join(User).where(User.email.in_(DEMO_EMAILS)))
    )


def test_fresh_seed_creates_consistent_demo_data(db_session: Session, rendered: list[str]) -> None:
    result = seed.seed(db_session, PASSWORD)

    assert (result.users, result.videos) == (15, len(seed.VIDEOS))
    assert _count(db_session, User, User.email.in_(DEMO_EMAILS)) == 15
    videos = _demo_videos(db_session)
    assert len(videos) == len(seed.VIDEOS)
    assert len(rendered) == len(seed.VIDEOS)
    # Counters equal the rows they count (architecture decision D8).
    for video in videos:
        likes = _count(
            db_session, VideoReaction, VideoReaction.video_id == video.id, VideoReaction.value == 1
        )
        dislikes = _count(
            db_session, VideoReaction, VideoReaction.video_id == video.id, VideoReaction.value == -1
        )
        assert (video.like_count, video.dislike_count) == (likes, dislikes)
        assert video.comment_count == _count(db_session, Comment, Comment.video_id == video.id)
        for comment in db_session.scalars(select(Comment).where(Comment.video_id == video.id)):
            assert comment.reply_count == _count(
                db_session, Comment, Comment.parent_id == comment.id
            )
    for channel in db_session.scalars(
        select(Channel).join(User).where(User.email.in_(DEMO_EMAILS))
    ):
        assert channel.subscriber_count == _count(
            db_session, Subscription, Subscription.channel_id == channel.id
        )
    assert _count(db_session, Playlist) >= len(seed.PLAYLISTS)
    assert _count(db_session, Report) >= 1
    assert _count(db_session, VideoPermission) >= 1
    assert any(v.is_hidden for v in videos)
    admin = db_session.scalar(select(User).where(User.email == "admin@example.com"))
    assert admin is not None
    assert verify_password(admin.password_hash, PASSWORD)


def test_running_again_adds_nothing_and_keeps_passwords(
    db_session: Session, rendered: list[str]
) -> None:
    seed.seed(db_session, PASSWORD)
    admin = db_session.scalar(select(User).where(User.email == "admin@example.com"))
    assert admin is not None
    admin.password_hash = "changed-by-reset-password"
    db_session.commit()
    before = (
        _count(db_session, Video),
        _count(db_session, Comment),
        _count(db_session, Subscription),
    )

    again = seed.seed(db_session, "a-different-password")

    assert not again.changed
    assert (
        _count(db_session, Video),
        _count(db_session, Comment),
        _count(db_session, Subscription),
    ) == before
    db_session.refresh(admin)
    assert admin.password_hash == "changed-by-reset-password"


def test_refresh_media_rerenders_existing_videos_only(
    db_session: Session, rendered: list[str]
) -> None:
    seed.seed(db_session, PASSWORD)
    rendered.clear()
    likes_before = {v.id: v.like_count for v in _demo_videos(db_session)}

    result = seed.seed(db_session, PASSWORD, refresh_media=True)

    assert (result.users, result.videos, result.refreshed) == (0, 0, len(seed.VIDEOS))
    assert sorted(rendered) == sorted(v.title for v in seed.VIDEOS)
    assert {v.id: v.like_count for v in _demo_videos(db_session)} == likes_before


def test_older_installs_get_the_missing_accounts_and_videos(
    db_session: Session, rendered: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An install seeded with the first 6 accounts / 12 videos is topped up on re-run."""
    monkeypatch.setattr(seed, "USERS", seed.USERS[:6])
    monkeypatch.setattr(seed, "VIDEOS", seed.VIDEOS[:12])
    monkeypatch.setattr(seed, "PLAYLISTS", seed.PLAYLISTS[:1])
    seed.seed(db_session, PASSWORD)
    monkeypatch.undo()
    monkeypatch.setattr(seed, "_store_media", lambda video, *_a: rendered.append(video.title))

    result = seed.seed(db_session, PASSWORD)

    assert (result.users, result.videos) == (9, len(seed.VIDEOS) - 12)
    assert _count(db_session, User, User.email.in_(DEMO_EMAILS)) == 15
    assert len(_demo_videos(db_session)) == len(seed.VIDEOS)
