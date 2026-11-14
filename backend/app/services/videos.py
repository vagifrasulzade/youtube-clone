"""Single-video operations: detail, thumbnail selection, deletion."""

from __future__ import annotations

import logging
from typing import BinaryIO, Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError
from app.models import Subscription, User, Video, VideoReaction
from app.models.enums import RoleName
from app.services import access, images
from app.storage import keys, s3
from app.workers import queue

logger = logging.getLogger(__name__)

ThumbnailChoice = Literal["auto_1", "auto_2", "auto_3", "custom"]


def my_reaction(
    db: Session, video: Video, viewer: User | None
) -> Literal["like", "dislike"] | None:
    if viewer is None:
        return None
    reaction = db.get(VideoReaction, (viewer.id, video.id))
    if reaction is None:
        return None
    return "like" if reaction.value > 0 else "dislike"


def is_subscribed(db: Session, video: Video, viewer: User | None) -> bool:
    if viewer is None:
        return False
    return db.get(Subscription, (viewer.id, video.channel_id)) is not None


def select_thumbnail(video: Video, choice: ThumbnailChoice) -> None:
    """Point the video at one of its existing thumbnails (auto candidates or custom)."""
    key = keys.video_thumbnail(video.id, choice)
    if s3.head(get_settings().media_bucket, key) is None:
        raise ConflictError("That thumbnail does not exist yet", code="thumbnail_not_found")
    video.thumbnail_key = key
    video.updated_at = func.now()  # new ?v= so browsers fetch the new image


def upload_custom_thumbnail(db: Session, video: Video, stream: BinaryIO) -> Video:
    settings = get_settings()
    data = images.read_limited(stream, settings.max_thumbnail_bytes)
    jpeg = images.reencode_jpeg(data, "thumbnail")
    key = keys.video_thumbnail(video.id, "custom")
    s3.put_bytes(settings.media_bucket, key, jpeg, content_type="image/jpeg")
    video.thumbnail_key = key
    video.updated_at = func.now()
    db.commit()
    db.refresh(video)
    return video


def delete_video(db: Session, video_id: str, user: User) -> None:
    """Owner, or an admin, may delete. Moderators hide instead (stage 7)."""
    video = access.get_viewable_video_or_404(db, video_id, user)
    if not (access.is_owner(video, user) or access.has_role(user, RoleName.ADMIN)):
        raise ForbiddenError("Only the owner or an admin can delete this video", code="not_owner")
    db.delete(video)  # rows attached to the video go with it (ON DELETE CASCADE)
    db.commit()
    # Objects are removed asynchronously after commit; the task is idempotent.
    queue.enqueue_video_deletion(video_id)
    logger.info("Video deleted", extra={"video_id": video_id, "by": str(user.id)})
