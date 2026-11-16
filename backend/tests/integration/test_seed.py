"""Demo seed against the real database.

Rendering and uploading are replaced by a recorder here; `test_seed_render.py` renders
the real clips with ffmpeg (Docker / CI).
"""

from __future__ import annotations

from datetime import UTC, datetime
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
from app.models.enums import VideoStatus
from app.storage import keys

PASSWORD = "seed-password-123"
DEMO_EMAILS = [email for email, *_ in seed.USERS]


@pytest.fixture
def rendered(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record which videos would be rendered and uploaded instead of running ffmpeg."""
    calls: list[str] = []

    def fake(video_id: str, title: str, _channel: str, index: int, _workdir: Path) -> seed.Media:
        calls.append(title)
        return seed.Media(seconds=seed.clip_seconds(index), size=1000 + index)

    monkeypatch.setattr(seed, "_render_and_upload", fake)
    return calls


def _count(db: Session, model: type, *where: object) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def _demo_videos(db: Session) -> list[Video]:
    return list(
        db.scalars(select(Video).join(Channel).join(User).where(User.email.in_(DEMO_EMAILS)))
    )


def _assert_consistent(db: Session) -> None:
    """Counters equal the rows they count (D8); replies come after their parent."""
    db.expire_all()
    now = datetime.now(UTC)
    for video in _demo_videos(db):
        likes = _count(
            db, VideoReaction, VideoReaction.video_id == video.id, VideoReaction.value == 1
        )
        dislikes = _count(
            db, VideoReaction, VideoReaction.video_id == video.id, VideoReaction.value == -1
        )
        assert (video.like_count, video.dislike_count) == (likes, dislikes), video.title
        assert video.comment_count == _count(db, Comment, Comment.video_id == video.id)
        for comment in db.scalars(select(Comment).where(Comment.video_id == video.id)):
            assert comment.created_at <= now
            assert comment.reply_count == _count(db, Comment, Comment.parent_id == comment.id)
            if comment.parent_id is not None:
                parent = db.get(Comment, comment.parent_id)
                assert parent is not None
                assert comment.created_at > parent.created_at
    for channel in db.scalars(select(Channel).join(User).where(User.email.in_(DEMO_EMAILS))):
        assert channel.subscriber_count == _count(
            db, Subscription, Subscription.channel_id == channel.id
        ), channel.handle


def test_fresh_seed_creates_consistent_demo_data(db_session: Session, rendered: list[str]) -> None:
    result = seed.seed(db_session, PASSWORD)

    assert (result.users, result.videos) == (15, len(seed.VIDEOS))
    assert _count(db_session, User, User.email.in_(DEMO_EMAILS)) == 15
    videos = _demo_videos(db_session)
    assert len(videos) == len(seed.VIDEOS)
    assert sorted(rendered) == sorted(v.title for v in seed.VIDEOS)
    _assert_consistent(db_session)
    ids = [v.id for v in videos]
    playlist_titles = [title for _, title, _, _ in seed.PLAYLISTS]
    assert _count(db_session, Playlist, Playlist.title.in_(playlist_titles)) == len(seed.PLAYLISTS)
    assert _count(db_session, Report, Report.video_id.in_(ids)) == sum(
        v.reported for v in seed.VIDEOS
    )
    assert _count(db_session, VideoPermission, VideoPermission.video_id.in_(ids)) == sum(
        v.shared_with is not None for v in seed.VIDEOS
    )
    assert sum(v.is_hidden for v in videos) == sum(v.hidden for v in seed.VIDEOS)
    for video in videos:
        assert video.thumbnail_key == keys.video_thumbnail(video.id, "auto_2")
        assert video.playback_key == keys.video_playback(video.id)
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
    counts = (
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
    ) == counts
    db_session.refresh(admin)
    assert admin.password_hash == "changed-by-reset-password"


def test_refresh_media_keeps_choices_and_never_touches_real_uploads(
    db_session: Session, rendered: list[str]
) -> None:
    seed.seed(db_session, PASSWORD)
    videos = {v.title: v for v in _demo_videos(db_session)}
    picked = videos[seed.VIDEOS[0].title]
    picked.thumbnail_key = keys.video_thumbnail(picked.id, "auto_3")  # chosen in Studio
    upload = videos[seed.VIDEOS[1].title]
    upload.source_key = keys.video_source(upload.id)  # a real upload with a demo title
    db_session.commit()  # this bumps their updated_at, so read the stamps afterwards
    db_session.expire_all()
    likes_before = {v.id: v.like_count for v in videos.values()}
    stamp = {v.id: v.updated_at for v in videos.values()}
    rendered.clear()

    result = seed.seed(db_session, PASSWORD, refresh_media=True)

    assert (result.users, result.videos) == (0, 0)
    assert result.refreshed == len(seed.VIDEOS) - 1
    assert upload.title not in rendered
    db_session.expire_all()
    assert db_session.get(Video, picked.id).thumbnail_key == keys.video_thumbnail(
        picked.id, "auto_3"
    )
    assert {v.id: v.like_count for v in _demo_videos(db_session)} == likes_before
    refreshed = db_session.get(Video, videos[seed.VIDEOS[2].title].id)
    assert refreshed.updated_at > stamp[refreshed.id]  # new ?v= for browsers
    assert db_session.get(Video, upload.id).updated_at == stamp[upload.id]


def test_older_installs_get_the_missing_accounts_and_videos(
    db_session: Session, rendered: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An install seeded with the first 6 accounts / 12 videos is topped up on re-run,
    and the existing channels' subscriber counters stay equal to their rows."""
    with monkeypatch.context() as old:
        old.setattr(seed, "USERS", seed.USERS[:6])
        old.setattr(seed, "VIDEOS", seed.VIDEOS[:12])
        old.setattr(seed, "PLAYLISTS", seed.PLAYLISTS[:1])
        seed.seed(db_session, PASSWORD)

    result = seed.seed(db_session, PASSWORD)

    assert (result.users, result.videos) == (9, len(seed.VIDEOS) - 12)
    assert _count(db_session, User, User.email.in_(DEMO_EMAILS)) == 15
    assert len(_demo_videos(db_session)) == len(seed.VIDEOS)
    _assert_consistent(db_session)


def test_a_failed_render_keeps_earlier_videos_and_removes_its_objects(
    db_session: Session, rendered: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    good = seed._render_and_upload
    discarded: list[str] = []

    def third_fails(
        video_id: str, title: str, channel: str, index: int, workdir: Path
    ) -> seed.Media:
        if index == 2:
            raise RuntimeError("rendering demo clip 2 failed")
        return good(video_id, title, channel, index, workdir)

    monkeypatch.setattr(seed, "_render_and_upload", third_fails)
    monkeypatch.setattr(seed.s3, "delete_prefix", lambda _bucket, prefix: discarded.append(prefix))

    with pytest.raises(RuntimeError, match="clip 2"):
        seed.seed(db_session, PASSWORD)

    titles = {v.title for v in _demo_videos(db_session)}
    assert titles == {seed.VIDEOS[0].title, seed.VIDEOS[1].title}  # committed one by one
    assert len(discarded) == 1
    assert discarded[0].startswith("videos/")
    _assert_consistent(db_session)

    monkeypatch.setattr(seed, "_render_and_upload", good)
    result = seed.seed(db_session, PASSWORD)  # the next run completes the rest

    assert result.videos == len(seed.VIDEOS) - 2
    assert all(v.status == VideoStatus.READY for v in _demo_videos(db_session))
    _assert_consistent(db_session)
