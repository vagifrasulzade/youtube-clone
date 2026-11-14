"""The signed-in user's library: subscriptions, feeds."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.pages import ChannelBrief, CursorPage, VideoCard
from app.services import feeds, subscriptions

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/subscriptions", summary="Channels I follow (sidebar)")
def my_subscriptions(user: CurrentUser, db: DbSession) -> list[ChannelBrief]:
    return [ChannelBrief.from_model(c) for c in subscriptions.subscribed_channels(db, user)]


@router.get("/feed/subscriptions", summary="Newest videos from channels I follow")
def subscriptions_feed(
    user: CurrentUser, db: DbSession, cursor: str | None = None, limit: int = 24
) -> CursorPage[VideoCard]:
    items, next_cursor = feeds.subscriptions_feed(db, user, cursor, limit)
    return CursorPage(items=[VideoCard.from_model(v, user) for v in items], next_cursor=next_cursor)
