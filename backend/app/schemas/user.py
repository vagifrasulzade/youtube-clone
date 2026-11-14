"""User/channel representations returned by the API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import Channel, User
from app.models.enums import RoleName
from app.services.media_urls import channel_avatar_url


class ChannelSummary(BaseModel):
    id: uuid.UUID
    handle: str
    name: str
    avatar_url: str | None = None

    @classmethod
    def from_model(cls, channel: Channel) -> ChannelSummary:
        return cls(
            id=channel.id,
            handle=channel.handle,
            name=channel.name,
            avatar_url=channel_avatar_url(channel),
        )


class CurrentUserOut(BaseModel):
    """The signed-in user (includes private fields such as email)."""

    id: uuid.UUID
    email: str
    role: RoleName
    created_at: datetime
    channel: ChannelSummary

    @classmethod
    def from_model(cls, user: User) -> CurrentUserOut:
        return cls(
            id=user.id,
            email=user.email,
            role=user.role.name,
            created_at=user.created_at,
            channel=ChannelSummary.from_model(user.channel),
        )
