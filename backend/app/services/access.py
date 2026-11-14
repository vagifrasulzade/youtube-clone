"""The ONE place that decides who may see or manage a video (docs/security.md § 3.2).

- Every single-video read goes through `get_viewable_video_or_404`.
- Every video list composes `listable_filter()`.
- A video the caller may not see is a 404, so private videos are not revealed.
"""

from __future__ import annotations

import re

from sqlalchemy import ColumnElement, and_, exists, select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError
from app.models import User, Video, VideoPermission
from app.models.enums import ROLE_LEVELS, RoleName, VideoStatus, Visibility
from app.models.video import VIDEO_ID_PATTERN

_VIDEO_ID_RE = re.compile(VIDEO_ID_PATTERN)


def has_role(user: User, minimum: RoleName) -> bool:
    return user.role.level >= ROLE_LEVELS[minimum]


def is_staff(user: User | None) -> bool:
    return user is not None and has_role(user, RoleName.MODERATOR)


def is_owner(video: Video, user: User | None) -> bool:
    return user is not None and user.channel is not None and video.channel_id == user.channel.id


def has_grant(db: Session, video_id: str, user_id: object) -> bool:
    stmt = select(
        exists().where(VideoPermission.video_id == video_id, VideoPermission.user_id == user_id)
    )
    return bool(db.scalar(stmt))


def can_view(db: Session, video: Video, viewer: User | None) -> bool:
    if is_owner(video, viewer):
        return True  # owner always: drafts, processing, failed, hidden
    if is_staff(viewer):
        return True  # moderators/admins review any video (incl. private, hidden)
    if video.is_hidden or video.status != VideoStatus.READY:
        return False
    if video.visibility in (Visibility.PUBLIC, Visibility.UNLISTED):
        return True
    return viewer is not None and has_grant(db, video.id, viewer.id)


def _not_found() -> NotFoundError:
    return NotFoundError("Video not found", code="video_not_found")


def get_video_or_404(db: Session, video_id: str) -> Video:
    if not _VIDEO_ID_RE.match(video_id):
        raise _not_found()
    video = db.get(Video, video_id)
    if video is None:
        raise _not_found()
    return video


def get_viewable_video_or_404(db: Session, video_id: str, viewer: User | None) -> Video:
    video = get_video_or_404(db, video_id)
    if not can_view(db, video, viewer):
        raise _not_found()
    return video


def get_owned_video(db: Session, video_id: str, user: User) -> Video:
    """For management actions: 404 if the caller cannot even see it, 403 if they can
    see it but do not own it."""
    video = get_viewable_video_or_404(db, video_id, user)
    if not is_owner(video, user):
        raise ForbiddenError("Only the video owner can do this", code="not_owner")
    return video


def listable_filter() -> ColumnElement[bool]:
    """Videos that may appear in any public list (feed, search, channel, related)."""
    return and_(
        Video.visibility == Visibility.PUBLIC,
        Video.status == VideoStatus.READY,
        Video.is_hidden.is_(False),
    )
