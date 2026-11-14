"""Identity: roles, users, refresh tokens."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, created_at_column, str_enum, uuid_pk
from app.models.enums import ROLE_IDS, RoleName

if TYPE_CHECKING:
    from app.models.channel import Channel


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    name: Mapped[RoleName] = mapped_column(str_enum(RoleName, "role_name"), unique=True)
    level: Mapped[int] = mapped_column(SmallInteger, unique=True)


class User(TimestampMixin, Base):
    """Authentication identity. The public profile lives in `Channel` (1:1)."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("roles.id", ondelete="RESTRICT"),
        index=True,
        default=ROLE_IDS[RoleName.USER],
        server_default=text(str(ROLE_IDS[RoleName.USER])),
    )
    banned_at: Mapped[datetime | None]
    ban_reason: Mapped[str | None] = mapped_column(String(500))
    last_login_at: Mapped[datetime | None]

    role: Mapped[Role] = relationship(lazy="joined")
    channel: Mapped[Channel] = relationship(back_populates="owner", uselist=False)

    @property
    def is_banned(self) -> bool:
        return self.banned_at is not None


class RefreshToken(Base):
    """One row per issued refresh token; only the SHA-256 of the token is stored."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"), index=True
    )
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = created_at_column()
