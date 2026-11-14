"""Channel endpoints (profile images in stage 4; pages and subscriptions in stage 6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile

from app.api.deps import CurrentUser, DbSession
from app.core import rate_limit
from app.schemas.user import ChannelSummary
from app.services import channels

router = APIRouter(prefix="/channels", tags=["channels"])

_image_limit = Depends(rate_limit.limit_by_ip("channel-image", limit=30, window_seconds=3600))


@router.put(
    "/me/avatar",
    summary="Upload a channel avatar (JPEG/PNG/WebP, re-encoded server-side)",
    dependencies=[_image_limit],
)
def upload_avatar(file: UploadFile, user: CurrentUser, db: DbSession) -> ChannelSummary:
    return ChannelSummary.from_model(channels.set_channel_image(db, user, "avatar", file.file))


@router.put(
    "/me/banner",
    summary="Upload a channel banner (JPEG/PNG/WebP, re-encoded server-side)",
    dependencies=[_image_limit],
)
def upload_banner(file: UploadFile, user: CurrentUser, db: DbSession) -> ChannelSummary:
    return ChannelSummary.from_model(channels.set_channel_image(db, user, "banner", file.file))
