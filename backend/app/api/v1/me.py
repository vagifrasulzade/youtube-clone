"""The signed-in user's library: subscriptions, feeds."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.pages import ChannelBrief, CursorPage, VideoCard
from app.schemas.playlist import PlaylistCard
from app.services import feeds, grants, subscriptions, views
from app.services import playlists as playlist_service

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


@router.get("/history", summary="Watch history (most recent first)")
def watch_history(user: CurrentUser, db: DbSession, limit: int = 50) -> list[VideoCard]:
    return [VideoCard.from_model(v, user) for v in views.history(db, user, limit)]


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT, summary="Clear watch history")
def clear_watch_history(user: CurrentUser, db: DbSession) -> Response:
    views.clear_history(db, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/liked", summary="Videos I liked")
def liked(user: CurrentUser, db: DbSession, limit: int = 50) -> list[VideoCard]:
    return [VideoCard.from_model(v, user) for v in views.liked_videos(db, user, limit)]


@router.get("/shared", summary="Private videos shared with me")
def shared(user: CurrentUser, db: DbSession, limit: int = 50) -> list[VideoCard]:
    return [VideoCard.from_model(v, user) for v in grants.shared_with_me(db, user, limit)]


@router.get("/playlists", summary="My playlists (for 'Save to playlist')")
def my_playlists(user: CurrentUser, db: DbSession) -> list[PlaylistCard]:
    return playlist_service.build_cards(
        db, playlist_service.channel_playlists(db, user.channel, user), user
    )
