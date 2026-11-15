"""Comments with one level of replies (docs/api.md § Comments, acceptance D2).

Visibility: a comment is readable exactly when its video is (access policy), so the
comments of a video the viewer may not see are a 404, like the video itself (C2).

Counters (CLAUDE.md rule 5): `videos.comment_count` counts every comment including
replies and `comments.reply_count` counts a comment's replies. Both change with atomic
increments in the same transaction as the rows.

Lock order is always parent comment -> reply -> video, so concurrent replies and
deletes cannot deadlock, and a reply can never be added to a parent that is being
deleted (the parent's row lock blocks the reply's foreign-key check until then).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Select, delete, func, or_, select, tuple_, update
from sqlalchemy.orm import Session, joinedload

from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.models import Comment, User, Video
from app.models.enums import ModerationActionType, ModerationTargetType, RoleName
from app.schemas.comment import CommentOut
from app.schemas.pages import CursorPage
from app.services import access
from app.services.moderation import audit
from app.services.pagination import clamp_limit, decode_cursor, encode_cursor, parse_datetime

CommentSort = Literal["newest", "oldest"]


def _not_found() -> NotFoundError:
    return NotFoundError("Comment not found", code="comment_not_found")


def get_viewable_comment_or_404(
    db: Session, comment_id: uuid.UUID, viewer: User | None
) -> tuple[Comment, Video]:
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise _not_found()
    try:
        video = access.get_viewable_video_or_404(db, comment.video_id, viewer)
    except NotFoundError:
        raise _not_found() from None  # same answer as a missing comment
    return comment, video


def may_delete(comment: Comment, video: Video, user: User | None) -> bool:
    """D2: the author, the video's owner, moderators and admins."""
    if user is None:
        return False
    return (
        comment.author_id == user.id
        or access.is_owner(video, user)
        or access.has_role(user, RoleName.MODERATOR)
    )


def _page(
    db: Session, stmt: Select[tuple[Comment]], *, newest_first: bool, limit: int,
    cursor: str | None,
) -> tuple[list[Comment], str | None]:  # fmt: skip
    key = tuple_(Comment.created_at, Comment.id)
    if cursor:
        created_at, comment_id = decode_cursor(cursor, 2)
        after = (parse_datetime(created_at), _parse_uuid(comment_id))
        stmt = stmt.where(key < after if newest_first else key > after)
    order = (
        (Comment.created_at.desc(), Comment.id.desc())
        if newest_first
        else (Comment.created_at.asc(), Comment.id.asc())
    )
    limit = clamp_limit(limit)
    rows = list(
        db.scalars(
            stmt.options(joinedload(Comment.author).joinedload(User.channel))
            .order_by(*order)
            .limit(limit + 1)
        )
    )
    more = len(rows) > limit
    page = rows[:limit]
    next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if more and page else None
    return page, next_cursor


def _parse_uuid(value: object) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise BadRequestError("Invalid cursor", code="invalid_cursor") from None


def list_top_level(
    db: Session, video_id: str, viewer: User | None, *, sort: CommentSort, limit: int,
    cursor: str | None,
) -> tuple[Video, list[Comment], str | None]:  # fmt: skip
    video = access.get_viewable_video_or_404(db, video_id, viewer)
    stmt = select(Comment).where(Comment.video_id == video.id, Comment.parent_id.is_(None))
    items, next_cursor = _page(db, stmt, newest_first=sort == "newest", limit=limit, cursor=cursor)
    return video, items, next_cursor


def list_replies(
    db: Session, comment_id: uuid.UUID, viewer: User | None, *, limit: int, cursor: str | None
) -> tuple[Video, list[Comment], str | None]:
    parent, video = get_viewable_comment_or_404(db, comment_id, viewer)
    if parent.parent_id is not None:  # one level only: a reply has no replies
        raise _not_found()
    stmt = select(Comment).where(Comment.parent_id == parent.id)
    items, next_cursor = _page(db, stmt, newest_first=False, limit=limit, cursor=cursor)
    return video, items, next_cursor


def create(
    db: Session, user: User, video_id: str, *, body: str, parent_id: uuid.UUID | None
) -> tuple[Comment, Video]:
    video = access.get_viewable_video_or_404(db, video_id, user)
    if parent_id is not None:
        # Validates AND row-locks the parent: it must be a top-level comment of this video.
        locked = db.scalar(
            update(Comment)
            .where(
                Comment.id == parent_id,
                Comment.video_id == video.id,
                Comment.parent_id.is_(None),
            )
            .values(reply_count=Comment.reply_count + 1)
            .returning(Comment.id)
        )
        if locked is None:
            db.rollback()
            raise NotFoundError(
                "You can only reply to a top-level comment of this video",
                code="parent_comment_not_found",
            )
    comment = Comment(
        video_id=video.id,
        author_id=user.id,
        parent_id=parent_id,
        body=body,
        # The insert's real time (not the transaction start): orders comments made in
        # quick succession correctly.
        created_at=func.clock_timestamp(),
    )
    db.add(comment)
    db.flush()
    db.execute(
        update(Video).where(Video.id == video.id).values(comment_count=Video.comment_count + 1)
    )
    db.commit()
    db.refresh(comment)
    return comment, video


def edit(db: Session, user: User, comment_id: uuid.UUID, body: str) -> tuple[Comment, Video]:
    comment, video = get_viewable_comment_or_404(db, comment_id, user)
    if comment.author_id != user.id:
        raise ForbiddenError("Only the author can edit this comment", code="not_author")
    edited = db.scalar(
        update(Comment)
        .where(Comment.id == comment.id, Comment.author_id == user.id)
        .values(body=body, edited_at=datetime.now(UTC))
        .returning(Comment.id)
    )
    if edited is None:  # deleted meanwhile
        db.rollback()
        raise _not_found()
    db.commit()
    db.refresh(comment)
    return comment, video


def remove(db: Session, user: User, comment_id: uuid.UUID) -> None:
    comment, video = get_viewable_comment_or_404(db, comment_id, user)
    if not may_delete(comment, video, user):
        raise ForbiddenError("You cannot delete this comment", code="not_allowed")
    staff_action = comment.author_id != user.id and not access.is_owner(video, user)

    if comment.parent_id is None:
        # Lock the thread root first: replies being added now wait, then fail their FK.
        root = db.scalar(select(Comment.id).where(Comment.id == comment.id).with_for_update())
        if root is None:
            db.rollback()
            raise _not_found()
        removed = len(
            db.scalars(
                delete(Comment)
                .where(or_(Comment.id == comment.id, Comment.parent_id == comment.id))
                .returning(Comment.id)
            ).all()
        )
    else:
        parent = db.scalar(
            select(Comment.id).where(Comment.id == comment.parent_id).with_for_update()
        )
        gone = (
            db.scalar(delete(Comment).where(Comment.id == comment.id).returning(Comment.id))
            if parent is not None
            else None
        )
        if gone is None:  # another request deleted it (or its thread) first
            db.rollback()
            raise _not_found()
        db.execute(
            update(Comment)
            .where(Comment.id == comment.parent_id)
            .values(reply_count=Comment.reply_count - 1)
        )
        removed = 1

    db.execute(
        update(Video)
        .where(Video.id == video.id)
        .values(comment_count=Video.comment_count - removed)
    )
    if staff_action:
        audit(
            db, user, ModerationActionType.DELETE_COMMENT, ModerationTargetType.COMMENT,
            str(comment.id),
            details={"video_id": video.id, "author_id": str(comment.author_id),
                     "body": comment.body[:200], "replies_removed": removed - 1},
        )  # fmt: skip
    db.commit()


def build_out(comment: Comment, video: Video, viewer: User | None) -> CommentOut:
    return CommentOut.build(
        comment,
        video_channel_id=video.channel_id,
        viewer=viewer,
        viewer_may_delete=may_delete(comment, video, viewer),
    )


def build_page(
    items: list[Comment], next_cursor: str | None, video: Video, viewer: User | None
) -> CursorPage[CommentOut]:
    return CursorPage[CommentOut](
        items=[build_out(c, video, viewer) for c in items], next_cursor=next_cursor
    )
