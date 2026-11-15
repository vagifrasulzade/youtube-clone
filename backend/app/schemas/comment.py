"""Comment request and response shapes (docs/api.md § Comments)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.models import Comment, User
from app.schemas.common import MultiLineText, RequestModel
from app.schemas.pages import ChannelBrief

CommentBody = Annotated[MultiLineText, Field(min_length=1, max_length=10_000)]


class CommentCreate(RequestModel):
    body: CommentBody
    parent_id: uuid.UUID | None = Field(
        default=None, description="Reply to this top-level comment of the same video"
    )


class CommentUpdate(RequestModel):
    body: CommentBody


class CommentOut(BaseModel):
    id: uuid.UUID
    video_id: str
    parent_id: uuid.UUID | None
    body: str
    author: ChannelBrief
    is_video_owner: bool = Field(description="Written by the video's channel (creator badge)")
    reply_count: int
    created_at: datetime
    edited_at: datetime | None
    can_edit: bool
    can_delete: bool

    @classmethod
    def build(cls, comment: Comment, *, video_channel_id: uuid.UUID, viewer: User | None,
              viewer_may_delete: bool) -> CommentOut:  # fmt: skip
        channel = comment.author.channel
        return cls(
            id=comment.id,
            video_id=comment.video_id,
            parent_id=comment.parent_id,
            body=comment.body,
            author=ChannelBrief.from_model(channel),
            is_video_owner=channel.id == video_channel_id,
            reply_count=comment.reply_count,
            created_at=comment.created_at,
            edited_at=comment.edited_at,
            can_edit=viewer is not None and viewer.id == comment.author_id,
            can_delete=viewer_may_delete,
        )
