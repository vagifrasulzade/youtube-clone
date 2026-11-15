"""Search endpoints (rate-limited per IP)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, OptionalUser
from app.core import rate_limit
from app.schemas.common import SingleLineText
from app.schemas.pages import NumberedPage, VideoCard
from app.services import search as service

router = APIRouter(
    prefix="/search",
    tags=["search"],
    dependencies=[Depends(rate_limit.limit_by_ip("search", limit=60, window_seconds=60))],
)

Query100 = Annotated[SingleLineText, Query(min_length=1, max_length=100)]


@router.get("", summary="Search public videos by title (and description)")
def search(
    q: Query100,
    viewer: OptionalUser,
    db: DbSession,
    sort: service.SearchSort = "relevance",
    page: Annotated[int, Query(ge=1, le=100)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> NumberedPage[VideoCard]:
    items, total = service.search_videos(db, q, sort=sort, page=page, page_size=page_size)
    return NumberedPage(
        items=[VideoCard.from_model(v, viewer) for v in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/suggestions", summary="Title suggestions for the search box")
def suggestions(q: Query100, db: DbSession) -> list[str]:
    return service.suggestions(db, q)
