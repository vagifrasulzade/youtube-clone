"""Playlists and their ordered entries."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, created_at_column, str_enum, uuid_pk
from app.models.enums import Visibility
from app.models.video import VIDEO_ID_LENGTH


class Playlist(TimestampMixin, Base):
    __tablename__ = "playlists"
    __table_args__ = (
        CheckConstraint("char_length(title) BETWEEN 1 AND 150", name="title_length"),
        CheckConstraint("char_length(description) <= 5000", name="description_length"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    visibility: Mapped[Visibility] = mapped_column(
        str_enum(Visibility, "visibility"),
        default=Visibility.PRIVATE,
        server_default=Visibility.PRIVATE.value,
    )


Index("ix_playlists_channel_created", Playlist.channel_id, Playlist.created_at.desc())


class PlaylistVideo(Base):
    __tablename__ = "playlist_videos"
    __table_args__ = (
        # Deferred so a reorder can swap positions inside one transaction.
        UniqueConstraint(
            "playlist_id",
            "position",
            name="uq_playlist_videos_playlist_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("position >= 0", name="position_non_negative"),
    )

    playlist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), primary_key=True
    )
    video_id: Mapped[str] = mapped_column(
        String(VIDEO_ID_LENGTH),
        ForeignKey("videos.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    position: Mapped[int]
    added_at: Mapped[datetime] = created_at_column()
