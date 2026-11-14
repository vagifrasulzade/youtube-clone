"""Channel page schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import Channel
from app.services.media_urls import channel_avatar_url, channel_banner_url


class ChannelPageOut(BaseModel):
    id: uuid.UUID
    handle: str
    name: str
    description: str
    avatar_url: str | None
    banner_url: str | None
    subscriber_count: int
    video_count: int
    joined_at: datetime
    is_subscribed: bool
    is_owner: bool

    @classmethod
    def build(
        cls, channel: Channel, *, video_count: int, is_subscribed: bool, is_owner: bool
    ) -> ChannelPageOut:
        return cls(
            id=channel.id,
            handle=channel.handle,
            name=channel.name,
            description=channel.description,
            avatar_url=channel_avatar_url(channel),
            banner_url=channel_banner_url(channel),
            subscriber_count=channel.subscriber_count,
            video_count=video_count,
            joined_at=channel.created_at,
            is_subscribed=is_subscribed,
            is_owner=is_owner,
        )


class SubscriptionOut(BaseModel):
    subscribed: bool
    subscriber_count: int
