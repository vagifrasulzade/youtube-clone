"""Video request/response schemas (upload and owner-facing views)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.models import Video
from app.models.enums import VideoStatus, Visibility
from app.schemas.common import MultiLineText, RequestModel, SingleLineText

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


class VideoUpdateRequest(RequestModel):
    title: Title | None = None
    description: Description | None = None
    visibility: Visibility | None = None
