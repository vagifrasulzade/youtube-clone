"""View counting and watch history (acceptance D4).

At most one counted view per viewer per video per 24 hours. Deduplication uses a Redis
key that expires after 24 hours. Anonymous viewers are identified by a salted hash of
their IP address: no IP address is stored anywhere.
"""

from __future__ import annotations

import hashlib
import logging

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models import User, Video, VideoReaction, VideoView
from app.services import access

logger = logging.getLogger(__name__)

DEDUPE_SECONDS = 24 * 3600


def _viewer_key(viewer: User | None, client_ip: str) -> str:
    if viewer is not None:
        return f"u:{viewer.id}"
    salt = get_settings().media_token_secret.get_secret_value()
    return "a:" + hashlib.sha256(f"{salt}:{client_ip}".encode()).hexdigest()[:32]


def record_view(
    db: Session, redis: Redis, video_id: str, viewer: User | None, client_ip: str
) -> bool:
    """Returns True if this view was counted."""
    video = access.get_viewable_video_or_404(db, video_id, viewer)
    key = f"view:{video.id}:{_viewer_key(viewer, client_ip)}"
    try:
        first = redis.set(key, 1, nx=True, ex=DEDUPE_SECONDS)
    except RedisError:
        logger.warning("View dedupe unavailable; view not counted", exc_info=True)
        return False  # never inflate counts when deduplication is unavailable
    if not first:
        return False
    db.add(VideoView(video_id=video.id, user_id=viewer.id if viewer else None))
    db.execute(update(Video).where(Video.id == video.id).values(view_count=Video.view_count + 1))
    db.commit()
    return True


def history(db: Session, user: User, limit: int) -> list[Video]:
    """Most recently watched first, one entry per video, only videos still viewable."""
    last_seen = (
        # max(id): ids are an increasing identity, so this is "latest view" without ties
        select(VideoView.video_id, func.max(VideoView.id).label("seen"))
        .where(VideoView.user_id == user.id)
        .group_by(VideoView.video_id)
        .subquery()
    )
    rows = db.scalars(
        select(Video)
        .options(joinedload(Video.channel))
        .join(last_seen, last_seen.c.video_id == Video.id)
        .order_by(last_seen.c.seen.desc())
        .limit(max(1, min(limit, 100)))
    ).unique()
    return [v for v in rows if access.can_view(db, v, user)]


def clear_history(db: Session, user: User) -> None:
    # Keeps view counts; only unlinks the views from the user.
    db.execute(update(VideoView).where(VideoView.user_id == user.id).values(user_id=None))
    db.commit()


def liked_videos(db: Session, user: User, limit: int) -> list[Video]:
    rows = db.scalars(
        select(Video)
        .options(joinedload(Video.channel))
        .join(VideoReaction, VideoReaction.video_id == Video.id)
        .where(VideoReaction.user_id == user.id, VideoReaction.value == 1)
        .order_by(VideoReaction.created_at.desc())
        .limit(max(1, min(limit, 100)))
    ).unique()
    return [v for v in rows if access.can_view(db, v, user)]
