"""Comments with one level of replies (as on YouTube)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, uuid_pk
from app.models.video import VIDEO_ID_LENGTH

if TYPE_CHECKING:
    from app.models.user import User


class Comment(TimestampMixin, Base):
    __tablename__ = "comments"
    __table_args__ = (
        # (id, video_id) is unique so replies can reference it: the composite FK below
        # makes "a reply belongs to the same video as its parent" a database guarantee.
        UniqueConstraint("id", "video_id", name="uq_comments_id_video_id"),
        ForeignKeyConstraint(
            ["parent_id", "video_id"],
            ["comments.id", "comments.video_id"],
            ondelete="CASCADE",
            name="fk_comments_parent_same_video",
        ),
        CheckConstraint("char_length(body) BETWEEN 1 AND 10000", name="body_length"),
        CheckConstraint("reply_count >= 0", name="reply_count_non_negative"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    video_id: Mapped[str] = mapped_column(
        String(VIDEO_ID_LENGTH), ForeignKey("videos.id", ondelete="CASCADE")
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID | None]
    body: Mapped[str] = mapped_column(Text)
    reply_count: Mapped[int] = mapped_column(default=0, server_default="0")
    edited_at: Mapped[datetime | None]

    author: Mapped[User] = relationship()


Index(
    "ix_comments_video_top_level",
    Comment.video_id,
    Comment.created_at.desc(),
    postgresql_where=text("parent_id IS NULL"),
)
Index("ix_comments_parent_created", Comment.parent_id, Comment.created_at)
