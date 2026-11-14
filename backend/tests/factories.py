"""Small factory helpers that insert rows directly (no API), for DB-level tests."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import Channel, User, Video
from app.models.enums import ROLE_IDS, RoleName


def unique_suffix() -> str:
    return uuid.uuid4().hex[:10]


def create_user(
    db: Session,
    *,
    email: str | None = None,
    handle: str | None = None,
    role: RoleName = RoleName.USER,
) -> User:
    suffix = unique_suffix()
    user = User(
        email=email or f"user_{suffix}@example.com",
        password_hash="not-a-real-hash",
        role_id=ROLE_IDS[role],
    )
    user.channel = Channel(handle=handle or f"user_{suffix}", name=f"User {suffix}")
    db.add(user)
    db.flush()
    return user


def create_video(db: Session, channel: Channel, **fields: Any) -> Video:
    fields.setdefault("title", "Test video")
    video = Video(channel_id=channel.id, **fields)
    db.add(video)
    db.flush()
    return video
