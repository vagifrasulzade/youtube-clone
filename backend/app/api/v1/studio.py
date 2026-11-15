"""Creator Studio: the owner's own videos in every state."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models import Video
from app.models.enums import VideoStatus, Visibility
from app.schemas.pages import NumberedPage
from app.schemas.video import VideoOwnerOut

router = APIRouter(prefix="/studio", tags=["studio"])


@router.get("/videos", summary="My videos (drafts, processing, failed and hidden included)")
def my_videos(
    user: CurrentUser,
    db: DbSession,
    status: VideoStatus | None = None,
    visibility: Visibility | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> NumberedPage[VideoOwnerOut]:
    stmt = select(Video).where(Video.channel_id == user.channel.id)
    if status is not None:
        stmt = stmt.where(Video.status == status)
    if visibility is not None:
        stmt = stmt.where(Video.visibility == visibility)
    if q:
        stmt = stmt.where(Video.title.ilike(f"%{q.replace('%', r'\%').replace('_', r'\_')}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Video.created_at.desc(), Video.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return NumberedPage(
        items=[VideoOwnerOut.from_model(v) for v in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
