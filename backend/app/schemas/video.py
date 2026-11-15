"""Video request/response schemas (upload and owner-facing views)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models import Channel, User, Video
from app.models.enums import VideoStatus, Visibility
from app.schemas.common import MultiLineText, RequestModel, SingleLineText
from app.services.media_urls import channel_avatar_url, video_stream_url, video_thumbnail_url

Title = Annotated[SingleLineText, Field(min_length=1, max_length=100)]
Description = Annotated[MultiLineText, Field(max_length=5000)]


class UploadRequest(RequestModel):
    filename: Annotated[str, Field(min_length=1, max_length=255)]
    content_type: Annotated[str, Field(min_length=1, max_length=100)]
    size_bytes: Annotated[int, Field(ge=1)]
    title: Title | None = None


class UploadPolicyOut(BaseModel):
    """Form fields for a multipart POST straight to object storage."""

    url: str
    fields: dict[str, str]
    expires_at: datetime
    max_bytes: int


class VideoOwnerOut(BaseModel):
    """What the owner sees in Studio (includes processing state and errors)."""

    id: str
    title: str
    description: str
    visibility: Visibility
    status: VideoStatus
    is_hidden: bool
    processing_error: str | None
    original_filename: str | None
    duration_seconds: int | None
    width: int | None
    height: int | None
    view_count: int
    like_count: int
    dislike_count: int
    comment_count: int
    created_at: datetime
    published_at: datetime | None

    @classmethod
    def from_model(cls, video: Video) -> VideoOwnerOut:
        return cls.model_validate(video, from_attributes=True)


class UploadCreatedOut(BaseModel):
    video: VideoOwnerOut
    upload: UploadPolicyOut


class VideoStatusOut(BaseModel):
    id: str
    status: VideoStatus
    progress: int | None = Field(default=None, description="Processing progress 0-100")
    error: str | None = None


ThumbnailChoice = Literal["auto_1", "auto_2", "auto_3", "custom"]


class VideoUpdateRequest(RequestModel):
    title: Title | None = None
    description: Description | None = None
    visibility: Visibility | None = None
    thumbnail: ThumbnailChoice | None = None


class ChannelInfo(BaseModel):
    id: uuid.UUID
    handle: str
    name: str
    avatar_url: str | None
    subscriber_count: int

    @classmethod
    def from_model(cls, channel: Channel) -> ChannelInfo:
        return cls(
            id=channel.id,
            handle=channel.handle,
            name=channel.name,
            avatar_url=channel_avatar_url(channel),
            subscriber_count=channel.subscriber_count,
        )


class VideoDetailOut(BaseModel):
    """Watch page payload. Media URLs are API paths, never storage URLs."""

    id: str
    title: str
    description: str
    visibility: Visibility
    status: VideoStatus
    is_hidden: bool
    duration_seconds: int | None
    width: int | None
    height: int | None
    view_count: int
    like_count: int
    dislike_count: int
    comment_count: int
    published_at: datetime | None
    created_at: datetime
    stream_url: str | None
    thumbnail_url: str | None
    channel: ChannelInfo
    my_reaction: Literal["like", "dislike"] | None
    is_subscribed: bool
    can_edit: bool

    @classmethod
    def build(
        cls,
        video: Video,
        viewer: User | None,
        *,
        my_reaction: Literal["like", "dislike"] | None,
        is_subscribed: bool,
        can_edit: bool,
    ) -> VideoDetailOut:
        return cls(
            id=video.id,
            title=video.title,
            description=video.description,
            visibility=video.visibility,
            status=video.status,
            is_hidden=video.is_hidden,
            duration_seconds=video.duration_seconds,
            width=video.width,
            height=video.height,
            view_count=video.view_count,
            like_count=video.like_count,
            dislike_count=video.dislike_count,
            comment_count=video.comment_count,
            published_at=video.published_at,
            created_at=video.created_at,
            stream_url=video_stream_url(video, viewer),
            thumbnail_url=video_thumbnail_url(video, viewer),
            channel=ChannelInfo.from_model(video.channel),
            my_reaction=my_reaction,
            is_subscribed=is_subscribed,
            can_edit=can_edit,
        )


class ReactionRequest(RequestModel):
    value: Literal["like", "dislike"]


class ReactionOut(BaseModel):
    like_count: int
    dislike_count: int
    my_reaction: Literal["like", "dislike"] | None


class GrantRequest(RequestModel):
    handle: Annotated[str, Field(min_length=3, max_length=30)]


class GrantOut(BaseModel):
    user_id: uuid.UUID
    handle: str
    name: str
    granted_at: datetime
