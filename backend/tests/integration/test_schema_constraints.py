"""Database-level guarantees from docs/database.md.

These rules are enforced by PostgreSQL itself (constraints, keys, cascades),
so they hold even if application code has a bug. Each test asserts the exact
constraint name that fires.
"""

from collections.abc import Callable

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Channel,
    Comment,
    Playlist,
    PlaylistVideo,
    Report,
    Role,
    User,
    Video,
    VideoPermission,
    VideoReaction,
    VideoView,
)
from app.models.enums import ReportReason, ReportStatus, RoleName, VideoStatus, Visibility
from app.models.video import new_video_id
from tests.factories import create_user, create_video


def _run_in_savepoint(db: Session, action: Callable[[], object]) -> None:
    with db.begin_nested():
        action()
        db.flush()


def assert_violates(db: Session, constraint: str, action: Callable[[], object]) -> None:
    """Run `action` in a savepoint and assert it fails on the named constraint."""
    with pytest.raises(IntegrityError) as exc_info:
        _run_in_savepoint(db, action)
    assert exc_info.value.orig is not None
    assert exc_info.value.orig.diag.constraint_name == constraint  # type: ignore[attr-defined]


# --- reference data ---------------------------------------------------------


def test_roles_are_seeded_with_levels(db_session: Session) -> None:
    roles = db_session.execute(select(Role.id, Role.name, Role.level).order_by(Role.id)).all()

    assert [tuple(r) for r in roles] == [
        (1, RoleName.USER, 0),
        (2, RoleName.MODERATOR, 10),
        (3, RoleName.ADMIN, 20),
    ]


def test_new_user_defaults_to_user_role(db_session: Session) -> None:
    user = create_user(db_session)
    db_session.refresh(user)

    assert user.role.name == RoleName.USER


# --- users & channels -------------------------------------------------------


def test_email_must_be_stored_lowercase(db_session: Session) -> None:
    assert_violates(
        db_session,
        "ck_users_email_lowercase",
        lambda: db_session.add(User(email="Mixed@Example.com", password_hash="x")),
    )


def test_email_is_unique(db_session: Session) -> None:
    create_user(db_session, email="same@example.com")

    assert_violates(
        db_session,
        "uq_users_email",
        lambda: db_session.add(User(email="same@example.com", password_hash="x")),
    )


def test_user_has_at_most_one_channel(db_session: Session) -> None:
    user = create_user(db_session)

    assert_violates(
        db_session,
        "uq_channels_user_id",
        lambda: db_session.add(Channel(user_id=user.id, handle="second_channel", name="Second")),
    )


@pytest.mark.parametrize("handle", ["ab", "Has-Upper", "with space", "a/b/c", "emoji🙂"])
def test_channel_handle_format_is_enforced(db_session: Session, handle: str) -> None:
    user = User(email="handle@example.com", password_hash="x")
    user.channel = Channel(handle=handle, name="Name")

    assert_violates(db_session, "ck_channels_handle_format", lambda: db_session.add(user))


# --- videos -----------------------------------------------------------------


def test_video_id_generator_produces_youtube_style_ids() -> None:
    ids = {new_video_id() for _ in range(1000)}

    assert len(ids) == 1000
    assert all(len(i) == 11 and i.replace("-", "").replace("_", "").isalnum() for i in ids)


def test_new_video_defaults_are_safe(db_session: Session) -> None:
    channel = create_user(db_session).channel
    video = create_video(db_session, channel)
    db_session.refresh(video)

    assert video.visibility == Visibility.PRIVATE  # drafts are private until published
    assert video.status == VideoStatus.AWAITING_UPLOAD
    assert video.is_hidden is False
    assert (video.view_count, video.like_count, video.dislike_count, video.comment_count) == (
        0,
        0,
        0,
        0,
    )


def test_video_id_format_is_enforced(db_session: Session) -> None:
    channel = create_user(db_session).channel

    assert_violates(
        db_session,
        "ck_videos_id_format",
        lambda: db_session.add(Video(id="../../etc/p", channel_id=channel.id, title="x")),
    )


def test_overlong_values_are_rejected_by_column_length(db_session: Session) -> None:
    """Upper bounds are also enforced by VARCHAR(n) (the error comes before any CHECK)."""
    user = User(email="long@example.com", password_hash="x")
    user.channel = Channel(handle="x" * 31, name="Name")

    with pytest.raises(DataError):
        _run_in_savepoint(db_session, lambda: db_session.add(user))


def test_video_title_cannot_be_empty(db_session: Session) -> None:
    channel = create_user(db_session).channel

    assert_violates(
        db_session,
        "ck_videos_title_length",
        lambda: db_session.add(Video(channel_id=channel.id, title="")),
    )


def test_counters_cannot_go_negative(db_session: Session) -> None:
    video = create_video(db_session, create_user(db_session).channel)

    assert_violates(
        db_session,
        "ck_videos_counters_non_negative",
        lambda: db_session.execute(
            update(Video).where(Video.id == video.id).values(like_count=Video.like_count - 1)
        ),
    )


# --- reactions, permissions, subscriptions ----------------------------------


def test_one_reaction_per_user_per_video(db_session: Session) -> None:
    user = create_user(db_session)
    video = create_video(db_session, create_user(db_session).channel)
    db_session.add(VideoReaction(user_id=user.id, video_id=video.id, value=1))
    db_session.flush()

    assert_violates(
        db_session,
        "pk_video_reactions",
        lambda: db_session.add(VideoReaction(user_id=user.id, video_id=video.id, value=-1)),
    )


def test_reaction_value_must_be_like_or_dislike(db_session: Session) -> None:
    user = create_user(db_session)
    video = create_video(db_session, create_user(db_session).channel)

    assert_violates(
        db_session,
        "ck_video_reactions_value_valid",
        lambda: db_session.add(VideoReaction(user_id=user.id, video_id=video.id, value=5)),
    )


def test_permission_is_granted_once_per_user(db_session: Session) -> None:
    viewer = create_user(db_session)
    video = create_video(db_session, create_user(db_session).channel)
    db_session.add(VideoPermission(video_id=video.id, user_id=viewer.id))
    db_session.flush()

    assert_violates(
        db_session,
        "pk_video_permissions",
        lambda: db_session.add(VideoPermission(video_id=video.id, user_id=viewer.id)),
    )


# --- comments ---------------------------------------------------------------


def test_reply_must_belong_to_the_same_video_as_its_parent(db_session: Session) -> None:
    author = create_user(db_session)
    channel = create_user(db_session).channel
    video_a = create_video(db_session, channel, title="A")
    video_b = create_video(db_session, channel, title="B")
    parent = Comment(video_id=video_a.id, author_id=author.id, body="parent")
    db_session.add(parent)
    db_session.flush()

    assert_violates(
        db_session,
        "fk_comments_parent_same_video",
        lambda: db_session.add(
            Comment(video_id=video_b.id, author_id=author.id, parent_id=parent.id, body="x")
        ),
    )


def test_reply_on_same_video_is_accepted(db_session: Session) -> None:
    author = create_user(db_session)
    video = create_video(db_session, create_user(db_session).channel)
    parent = Comment(video_id=video.id, author_id=author.id, body="parent")
    db_session.add(parent)
    db_session.flush()

    db_session.add(Comment(video_id=video.id, author_id=author.id, parent_id=parent.id, body="r"))
    db_session.flush()


def test_comment_body_cannot_be_empty(db_session: Session) -> None:
    author = create_user(db_session)
    video = create_video(db_session, create_user(db_session).channel)

    assert_violates(
        db_session,
        "ck_comments_body_length",
        lambda: db_session.add(Comment(video_id=video.id, author_id=author.id, body="")),
    )


# --- reports ----------------------------------------------------------------


def test_only_one_open_report_per_user_per_video(db_session: Session) -> None:
    reporter = create_user(db_session)
    video = create_video(db_session, create_user(db_session).channel)
    first = Report(video_id=video.id, reporter_id=reporter.id, reason=ReportReason.SPAM)
    db_session.add(first)
    db_session.flush()

    assert_violates(
        db_session,
        "uq_reports_open_per_reporter",
        lambda: db_session.add(
            Report(video_id=video.id, reporter_id=reporter.id, reason=ReportReason.OTHER)
        ),
    )

    # Once the first report is resolved, the same user may report again.
    first.status = ReportStatus.RESOLVED
    db_session.flush()
    db_session.add(Report(video_id=video.id, reporter_id=reporter.id, reason=ReportReason.OTHER))
    db_session.flush()


# --- playlists --------------------------------------------------------------


def _playlist_with_two_videos(db: Session) -> tuple[PlaylistVideo, PlaylistVideo]:
    channel = create_user(db).channel
    playlist = Playlist(channel_id=channel.id, title="Mix")
    db.add(playlist)
    db.flush()
    first = PlaylistVideo(
        playlist_id=playlist.id, video_id=create_video(db, channel).id, position=0
    )
    second = PlaylistVideo(
        playlist_id=playlist.id, video_id=create_video(db, channel).id, position=1
    )
    db.add_all([first, second])
    db.flush()
    return first, second


def test_playlist_positions_can_be_swapped_in_one_transaction(db_session: Session) -> None:
    first, second = _playlist_with_two_videos(db_session)

    first.position, second.position = 1, 0
    db_session.flush()
    # Deferred unique constraint: force the check now (it would run at COMMIT).
    db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


def test_playlist_positions_are_unique(db_session: Session) -> None:
    first, second = _playlist_with_two_videos(db_session)

    def make_duplicate() -> None:
        second.position = first.position
        db_session.flush()
        db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    assert_violates(db_session, "uq_playlist_videos_playlist_position", make_duplicate)


# --- cascades ---------------------------------------------------------------


def test_deleting_a_video_cascades_to_everything_attached(db_session: Session) -> None:
    viewer = create_user(db_session)
    channel = create_user(db_session).channel
    video = create_video(db_session, channel)
    parent = Comment(video_id=video.id, author_id=viewer.id, body="top")
    db_session.add(parent)
    db_session.flush()
    playlist = Playlist(channel_id=channel.id, title="List")
    db_session.add(playlist)
    db_session.flush()
    db_session.add_all(
        [
            Comment(video_id=video.id, author_id=viewer.id, parent_id=parent.id, body="reply"),
            VideoReaction(user_id=viewer.id, video_id=video.id, value=1),
            VideoPermission(video_id=video.id, user_id=viewer.id),
            VideoView(video_id=video.id, user_id=viewer.id),
            PlaylistVideo(playlist_id=playlist.id, video_id=video.id, position=0),
            Report(video_id=video.id, reporter_id=viewer.id, reason=ReportReason.SPAM),
        ]
    )
    db_session.flush()

    db_session.execute(delete(Video).where(Video.id == video.id))
    db_session.expire_all()

    for model in (Comment, VideoReaction, VideoPermission, VideoView, PlaylistVideo, Report):
        remaining = db_session.scalar(select(func.count()).select_from(model))
        assert remaining == 0, f"{model.__tablename__} rows survived the video deletion"
    # The playlist itself and the users are untouched.
    assert db_session.get(Playlist, playlist.id) is not None
    assert db_session.get(User, viewer.id) is not None


# --- search -----------------------------------------------------------------


def test_search_vector_is_generated_from_title_and_description(db_session: Session) -> None:
    channel = create_user(db_session).channel
    match = create_video(db_session, channel, title="Plov recipe", description="Baku style")
    create_video(db_session, channel, title="Guitar lesson", description="Chords")

    def search(query: str) -> list[str]:
        tsquery = func.websearch_to_tsquery("simple", query)
        stmt = select(Video.id).where(Video.search_vector.op("@@")(tsquery))
        return list(db_session.scalars(stmt))

    assert search("plov") == [match.id]
    assert search("baku") == [match.id]  # description is indexed too
    assert search("violin") == []


def test_trigram_extension_is_available(db_session: Session) -> None:
    similarity = db_session.scalar(select(func.similarity("plov recipe", "plov recipes")))

    assert similarity is not None
    assert similarity > 0.5
