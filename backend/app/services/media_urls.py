"""Public URLs for media served through the API (never storage URLs).

Channel images are public. Video thumbnails and streams are added in later stages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.models import Channel


def _version(channel: Channel) -> int:
    return int(channel.updated_at.timestamp()) if channel.updated_at else 0


def channel_avatar_url(channel: Channel) -> str | None:
    if not channel.avatar_key:
        return None
    prefix = get_settings().api_prefix
    return f"{prefix}/media/channels/{channel.id}/avatar?v={_version(channel)}"


def channel_banner_url(channel: Channel) -> str | None:
    if not channel.banner_key:
        return None
    prefix = get_settings().api_prefix
    return f"{prefix}/media/channels/{channel.id}/banner?v={_version(channel)}"
