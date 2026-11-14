"""Channels (public creator profile, 1:1 with users) and subscriptions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, created_at_column, uuid_pk

if TYPE_CHECKING:
    from app.models.user import User

HANDLE_PATTERN = r"^[a-z0-9._-]{3,30}$"


class Channel(TimestampMixin, Base):
    __tablename__ = "channels"
    __table_args__ = (
        CheckConstraint(f"handle ~ '{HANDLE_PATTERN}'", name="handle_format"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 50", name="name_length"),
        CheckConstraint("char_length(description) <= 1000", name="description_length"),
        CheckConstraint("subscriber_count >= 0", name="subscriber_count_non_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    handle: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    avatar_key: Mapped[str | None] = mapped_column(String(300))
    banner_key: Mapped[str | None] = mapped_column(String(300))
    subscriber_count: Mapped[int] = mapped_column(default=0, server_default="0")

    owner: Mapped[User] = relationship(back_populates="channel")


class Subscription(Base):
    """PK (subscriber_id, channel_id) makes subscribing idempotent by construction."""

    __tablename__ = "subscriptions"

    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = created_at_column()
