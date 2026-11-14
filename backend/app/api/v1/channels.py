"""Channel endpoints (profile images in stage 4; pages and subscriptions in stage 6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, OptionalUser
from app.core import rate_limit
from app.models import Video
from app.schemas.channel import ChannelPageOut, SubscriptionOut
from app.schemas.pages import CursorPage, VideoCard
from app.schemas.user import ChannelSummary
from app.services import access, channels, feeds, subscriptions

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


@router.get("/{handle}", summary="Channel page header")
def get_channel(handle: str, viewer: OptionalUser, db: DbSession) -> ChannelPageOut:
    channel = subscriptions.get_channel_by_handle(db, handle)
    video_count = db.scalar(
        select(func.count())
        .select_from(Video)
        .where(Video.channel_id == channel.id, access.listable_filter())
    )
    return ChannelPageOut.build(
        channel,
        video_count=video_count or 0,
        is_subscribed=subscriptions.is_subscribed(db, viewer, channel),
        is_owner=viewer is not None and channel.user_id == viewer.id,
    )


@router.put("/{handle}/subscription", summary="Subscribe (idempotent)")
def subscribe(handle: str, user: CurrentUser, db: DbSession) -> SubscriptionOut:
    channel = subscriptions.subscribe(db, user, handle)
    return SubscriptionOut(subscribed=True, subscriber_count=channel.subscriber_count)


@router.delete("/{handle}/subscription", summary="Unsubscribe (idempotent)")
def unsubscribe(handle: str, user: CurrentUser, db: DbSession) -> SubscriptionOut:
    channel = subscriptions.unsubscribe(db, user, handle)
    return SubscriptionOut(subscribed=False, subscriber_count=channel.subscriber_count)


@router.get("/{handle}/videos", summary="A channel's public videos")
def channel_videos(
    handle: str,
    viewer: OptionalUser,
    db: DbSession,
    sort: feeds.ChannelSort = "latest",
    cursor: str | None = None,
    limit: int = 30,
) -> CursorPage[VideoCard]:
    channel = subscriptions.get_channel_by_handle(db, handle)
    items, next_cursor = feeds.channel_videos(db, channel.id, sort, cursor, limit)
    return CursorPage(
        items=[VideoCard.from_model(v, viewer) for v in items], next_cursor=next_cursor
    )
