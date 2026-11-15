"""Channel page schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.models import Channel
from app.schemas.common import MultiLineText, RequestModel, SingleLineText
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


class ChannelUpdate(RequestModel):
    name: Annotated[SingleLineText, Field(min_length=1, max_length=50)] | None = None
    description: Annotated[MultiLineText, Field(max_length=1000)] | None = None
