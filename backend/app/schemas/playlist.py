"""Playlist schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.models.enums import Visibility
from app.schemas.common import MultiLineText, RequestModel, SingleLineText
from app.schemas.pages import ChannelBrief, VideoCard

PlaylistTitle = Annotated[SingleLineText, Field(min_length=1, max_length=150)]
PlaylistDescription = Annotated[MultiLineText, Field(max_length=5000)]


class PlaylistCreate(RequestModel):
    title: PlaylistTitle
    description: PlaylistDescription = ""
    visibility: Visibility = Visibility.PRIVATE


class PlaylistUpdate(RequestModel):
    title: PlaylistTitle | None = None
    description: PlaylistDescription | None = None
    visibility: Visibility | None = None


class PlaylistAddVideo(RequestModel):
    video_id: Annotated[str, Field(min_length=11, max_length=11)]


class PlaylistOrder(RequestModel):
    video_ids: Annotated[list[str], Field(max_length=5000)]


class PlaylistCard(BaseModel):
    id: uuid.UUID
    title: str
    visibility: Visibility
    video_count: int
    thumbnail_url: str | None
    updated_at: datetime


class PlaylistEntry(BaseModel):
    """A playlist item; `video` is None for entries the viewer may not watch."""

    position: int
    video: VideoCard | None
    title: str


class PlaylistOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    visibility: Visibility
    channel: ChannelBrief
    is_owner: bool
    entries: list[PlaylistEntry]
