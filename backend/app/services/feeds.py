"""Video lists: home feed, channel videos, subscriptions feed, related videos.

Every list is built on `access.listable_filter()` (public + ready + not hidden), so
private, unlisted, unfinished and hidden videos never appear in any list (C3).
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import Integer, Select, func, select, tuple_
from sqlalchemy.orm import Session, joinedload

from app.core.errors import BadRequestError
from app.models import Subscription, User, Video
from app.services import access
from app.services.pagination import clamp_limit, decode_cursor, encode_cursor, parse_datetime

ChannelSort = Literal["latest", "popular", "oldest"]


def _base() -> Select[tuple[Video]]:
    return select(Video).options(joinedload(Video.channel)).where(access.listable_filter())


def _by_date(
    db: Session, stmt: Select[tuple[Video]], cursor: str | None, limit: int, *, newest: bool
) -> tuple[list[Video], str | None]:
    limit = clamp_limit(limit)
    key = tuple_(Video.published_at, Video.id)
    if cursor:
        published, video_id = decode_cursor(cursor, 2)
        bound = tuple_(parse_datetime(published), str(video_id))
        stmt = stmt.where(key < bound if newest else key > bound)
    order = (
        (Video.published_at.desc(), Video.id.desc())
        if newest
        else (Video.published_at.asc(), Video.id.asc())
    )
    rows = list(db.scalars(stmt.order_by(*order).limit(limit + 1)).unique())
    page, more = rows[:limit], len(rows) > limit
    next_cursor = encode_cursor(page[-1].published_at, page[-1].id) if more and page else None
    return page, next_cursor


def _by_views(
    db: Session, stmt: Select[tuple[Video]], cursor: str | None, limit: int
) -> tuple[list[Video], str | None]:
    limit = clamp_limit(limit)
    if cursor:
        views, video_id = decode_cursor(cursor, 2)
        if type(views) is not int or not 0 <= views < 2**63:
            raise BadRequestError("Invalid cursor", code="invalid_cursor")
        stmt = stmt.where(tuple_(Video.view_count, Video.id) < tuple_(views, str(video_id)))
    ordered = stmt.order_by(Video.view_count.desc(), Video.id.desc()).limit(limit + 1)
    rows = list(db.scalars(ordered).unique())
    page, more = rows[:limit], len(rows) > limit
    next_cursor = encode_cursor(page[-1].view_count, page[-1].id) if more and page else None
    return page, next_cursor


def home_feed(db: Session, cursor: str | None, limit: int) -> tuple[list[Video], str | None]:
    return _by_date(db, _base(), cursor, limit, newest=True)


def channel_videos(
    db: Session, channel_id: object, sort: ChannelSort, cursor: str | None, limit: int
) -> tuple[list[Video], str | None]:
    stmt = _base().where(Video.channel_id == channel_id)
    if sort == "popular":
        return _by_views(db, stmt, cursor, limit)
    return _by_date(db, stmt, cursor, limit, newest=sort == "latest")


def subscriptions_feed(
    db: Session, user: User, cursor: str | None, limit: int
) -> tuple[list[Video], str | None]:
    followed = select(Subscription.channel_id).where(Subscription.subscriber_id == user.id)
    return _by_date(db, _base().where(Video.channel_id.in_(followed)), cursor, limit, newest=True)


def related_videos(db: Session, video: Video, limit: int) -> list[Video]:
    """Title similarity first (pg_trgm), then the same channel, then popular videos."""
    limit = clamp_limit(limit)
    similarity = func.similarity(Video.title, video.title)
    same_channel = (Video.channel_id == video.channel_id).cast(Integer)
    stmt = (
        _base()
        .where(Video.id != video.id)
        .order_by(similarity.desc(), same_channel.desc(), Video.view_count.desc(), Video.id)
        .limit(limit)
    )
    return list(db.scalars(stmt).unique())
