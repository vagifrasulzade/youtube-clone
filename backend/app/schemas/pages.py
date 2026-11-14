"""Generic page envelopes and list item shapes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import Channel, User, Video
from app.services.media_urls import channel_avatar_url, video_thumbnail_url


class CursorPage[T](BaseModel):
    """Infinite lists (feed, comments, channel videos, history)."""

    items: list[T]
    next_cursor: str | None


class NumberedPage[T](BaseModel):
    """Numbered lists (search, studio, moderation, admin)."""

    items: list[T]
    total: int
    page: int
    page_size: int


class ChannelBrief(BaseModel):
    id: uuid.UUID
    handle: str
    name: str
    avatar_url: str | None

    @classmethod
    def from_model(cls, channel: Channel) -> ChannelBrief:
        return cls(
            id=channel.id,
            handle=channel.handle,
            name=channel.name,
            avatar_url=channel_avatar_url(channel),
        )


class VideoCard(BaseModel):
    """A thumbnail tile in feeds, search results, related videos and playlists."""

    id: str
    title: str
    thumbnail_url: str | None
    duration_seconds: int | None
    view_count: int
    published_at: datetime | None
    channel: ChannelBrief

    @classmethod
    def from_model(cls, video: Video, viewer: User | None = None) -> VideoCard:
        return cls(
            id=video.id,
            title=video.title,
            thumbnail_url=video_thumbnail_url(video, viewer),
            duration_seconds=video.duration_seconds,
            view_count=video.view_count,
            published_at=video.published_at,
            channel=ChannelBrief.from_model(video.channel),
        )
