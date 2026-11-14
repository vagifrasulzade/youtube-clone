"""URLs for media served through the API. Never storage URLs (acceptance B2)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.models.enums import VideoStatus, Visibility
from app.services.media_tokens import create_media_token

if TYPE_CHECKING:
    from app.models import Channel, User, Video


def _version(updated_at: datetime | None) -> int:
    return int(updated_at.timestamp()) if updated_at else 0


def _prefix() -> str:
    return f"{get_settings().api_prefix}/media"


def channel_avatar_url(channel: Channel) -> str | None:
    if not channel.avatar_key:
        return None
    return f"{_prefix()}/channels/{channel.id}/avatar?v={_version(channel.updated_at)}"


def channel_banner_url(channel: Channel) -> str | None:
    if not channel.banner_key:
        return None
    return f"{_prefix()}/channels/{channel.id}/banner?v={_version(channel.updated_at)}"


def is_openly_viewable(video: Video) -> bool:
    """Anyone with the link may view it, so its media needs no viewer token."""
    return (
        video.visibility in (Visibility.PUBLIC, Visibility.UNLISTED)
        and video.status == VideoStatus.READY
        and not video.is_hidden
    )


def video_stream_url(video: Video, viewer: User | None) -> str | None:
    if video.status != VideoStatus.READY or not video.playback_key:
        return None
    token = create_media_token(video.id, viewer.id if viewer else None)
    return f"{_prefix()}/videos/{video.id}/stream?t={token}"


def video_thumbnail_url(video: Video, viewer: User | None) -> str | None:
    if not video.thumbnail_key:
        return None
    url = f"{_prefix()}/videos/{video.id}/thumbnail?v={_version(video.updated_at)}"
    if not is_openly_viewable(video):
        url += f"&t={create_media_token(video.id, viewer.id if viewer else None)}"
    return url
