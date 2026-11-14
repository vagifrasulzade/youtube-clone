"""Videos and everything attached to a single video: permissions, reactions, views."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    ForeignKey,
    Identity,
    Index,
    SmallInteger,
    String,
    Text,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, created_at_column, str_enum
from app.models.enums import VideoStatus, Visibility

if TYPE_CHECKING:
    from app.models.channel import Channel

VIDEO_ID_LENGTH = 11
VIDEO_ID_PATTERN = r"^[A-Za-z0-9_-]{11}$"

# A video is "listable" (feed, search, channel page, related) only in this state.
LISTABLE_PREDICATE = "visibility = 'public' AND status = 'ready' AND NOT is_hidden"


def new_video_id() -> str:
    """YouTube-style id: 8 random bytes -> 11 URL-safe base64 characters (non-enumerable)."""
    return secrets.token_urlsafe(8)


class Video(TimestampMixin, Base):
    __tablename__ = "videos"
    __table_args__ = (
        CheckConstraint(f"id ~ '{VIDEO_ID_PATTERN}'", name="id_format"),
        CheckConstraint("char_length(title) BETWEEN 1 AND 100", name="title_length"),
        CheckConstraint("char_length(description) <= 5000", name="description_length"),
        CheckConstraint(
            "view_count >= 0 AND like_count >= 0 AND dislike_count >= 0 AND comment_count >= 0",
            name="counters_non_negative",
        ),
    )

    id: Mapped[str] = mapped_column(String(VIDEO_ID_LENGTH), primary_key=True, default=new_video_id)
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    visibility: Mapped[Visibility] = mapped_column(
        str_enum(Visibility, "visibility"),
        default=Visibility.PRIVATE,
        server_default=Visibility.PRIVATE.value,
    )
    status: Mapped[VideoStatus] = mapped_column(
        str_enum(VideoStatus, "status"),
        default=VideoStatus.AWAITING_UPLOAD,
        server_default=VideoStatus.AWAITING_UPLOAD.value,
    )
    is_hidden: Mapped[bool] = mapped_column(default=False, server_default=false())
    hidden_at: Mapped[datetime | None]

    # Object storage keys (bytes live in MinIO, never in PostgreSQL).
    source_key: Mapped[str | None] = mapped_column(String(300))
    playback_key: Mapped[str | None] = mapped_column(String(300))
    thumbnail_key: Mapped[str | None] = mapped_column(String(300))

    original_filename: Mapped[str | None] = mapped_column(String(255))
    source_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    playback_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    duration_seconds: Mapped[int | None]
    width: Mapped[int | None]
    height: Mapped[int | None]
    processing_error: Mapped[str | None] = mapped_column(String(500))
    processing_started_at: Mapped[datetime | None]

    # Denormalized counters, updated atomically in the same transaction as their rows.
    view_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    like_count: Mapped[int] = mapped_column(default=0, server_default="0")
    dislike_count: Mapped[int] = mapped_column(default=0, server_default="0")
    comment_count: Mapped[int] = mapped_column(default=0, server_default="0")

    published_at: Mapped[datetime | None]

    # 'simple' config: language-agnostic (titles may be AZ/RU/EN), no stemming surprises.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('simple'::regconfig, coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('simple'::regconfig, coalesce(description, '')), 'B')",
            persisted=True,
        ),
        deferred=True,
    )

    channel: Mapped[Channel] = relationship()


Index(
    "ix_videos_feed",
    Video.published_at.desc(),
    Video.id.desc(),
    postgresql_where=text(LISTABLE_PREDICATE),
)
Index(
    "ix_videos_channel_public",
    Video.channel_id,
    Video.published_at.desc(),
    postgresql_where=text(LISTABLE_PREDICATE),
)
Index("ix_videos_popular", Video.view_count.desc(), postgresql_where=text(LISTABLE_PREDICATE))
Index("ix_videos_channel_created", Video.channel_id, Video.created_at.desc())
Index("ix_videos_search", Video.search_vector, postgresql_using="gin")
Index(
    "ix_videos_title_trgm",
    Video.title,
    postgresql_using="gin",
    postgresql_ops={"title": "gin_trgm_ops"},
)
Index(
    "ix_videos_pipeline",
    Video.status,
    Video.created_at,
    postgresql_where=text("status IN ('awaiting_upload', 'queued', 'processing')"),
)


class VideoPermission(Base):
    """Explicit grant: this user may watch this private video."""

    __tablename__ = "video_permissions"

    video_id: Mapped[str] = mapped_column(
        String(VIDEO_ID_LENGTH), ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = created_at_column()


class VideoReaction(TimestampMixin, Base):
    """Like (+1) or dislike (-1). PK guarantees one reaction per user per video."""

    __tablename__ = "video_reactions"
    __table_args__ = (CheckConstraint("value IN (-1, 1)", name="value_valid"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    video_id: Mapped[str] = mapped_column(
        String(VIDEO_ID_LENGTH),
        ForeignKey("videos.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    value: Mapped[int] = mapped_column(SmallInteger)


Index(
    "ix_video_reactions_liked",
    VideoReaction.user_id,
    VideoReaction.created_at.desc(),
    postgresql_where=text("value = 1"),
)


class VideoView(Base):
    """One row per counted (deduplicated) view; also the source of watch history."""

    __tablename__ = "video_views"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    video_id: Mapped[str] = mapped_column(
        String(VIDEO_ID_LENGTH), ForeignKey("videos.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_column()


Index("ix_video_views_video_created", VideoView.video_id, VideoView.created_at)
Index(
    "ix_video_views_history",
    VideoView.user_id,
    VideoView.created_at.desc(),
    postgresql_where=text("user_id IS NOT NULL"),
)
