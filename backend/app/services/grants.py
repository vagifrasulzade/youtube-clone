"""Explicit access grants for private videos (owner-managed)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, joinedload

from app.core.errors import BadRequestError
from app.models import Channel, User, Video, VideoPermission
from app.models.enums import Visibility
from app.services import access
from app.services.subscriptions import get_channel_by_handle


def list_grants(db: Session, owner: User, video_id: str) -> list[tuple[VideoPermission, Channel]]:
    video = access.get_owned_video(db, video_id, owner)
    rows = db.execute(
        select(VideoPermission, Channel)
        .join(Channel, Channel.user_id == VideoPermission.user_id)
        .where(VideoPermission.video_id == video.id)
        .order_by(VideoPermission.created_at)
    )
    return [(row[0], row[1]) for row in rows]


def grant(db: Session, owner: User, video_id: str, handle: str) -> Channel:
    video = access.get_owned_video(db, video_id, owner)
    grantee = get_channel_by_handle(db, handle)
    if grantee.user_id == owner.id:
        raise BadRequestError("You already own this video", code="grant_to_self")
    db.execute(
        insert(VideoPermission)
        .values(video_id=video.id, user_id=grantee.user_id, granted_by_id=owner.id)
        .on_conflict_do_nothing(index_elements=["video_id", "user_id"])
    )
    db.commit()
    return grantee


def revoke(db: Session, owner: User, video_id: str, user_id: uuid.UUID) -> None:
    """Takes effect on the next request, including the next Range request (C4)."""
    video = access.get_owned_video(db, video_id, owner)
    db.execute(
        delete(VideoPermission).where(
            VideoPermission.video_id == video.id, VideoPermission.user_id == user_id
        )
    )
    db.commit()


def shared_with_me(db: Session, user: User, limit: int) -> list[Video]:
    rows = db.scalars(
        select(Video)
        .options(joinedload(Video.channel))
        .join(VideoPermission, VideoPermission.video_id == Video.id)
        .where(VideoPermission.user_id == user.id, Video.visibility == Visibility.PRIVATE)
        .order_by(VideoPermission.created_at.desc())
        .limit(max(1, min(limit, 100)))
    ).unique()
    return [v for v in rows if access.can_view(db, v, user)]
