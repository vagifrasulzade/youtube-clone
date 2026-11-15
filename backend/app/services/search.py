"""Video search: PostgreSQL full-text search plus trigram similarity.

- `search_vector` (generated tsvector, 'simple' config: works for AZ/RU/EN alike, title
  weighted above description) answers word matches, served by a GIN index.
- `pg_trgm` word_similarity on the title catches typos and partial words ("plof" ->
  "plov"). word_similarity compares the query with the best-matching PART of the title;
  plain similarity compares whole strings and misses typos in long titles.
Only listable videos are ever returned (C3).
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Video
from app.services import access

SearchSort = Literal["relevance", "date", "views"]
TRIGRAM_THRESHOLD = 0.5  # word_similarity; measured on the demo titles (see tests)


def search_videos(
    db: Session, query: str, *, sort: SearchSort, page: int, page_size: int
) -> tuple[list[Video], int]:
    tsquery = func.websearch_to_tsquery("simple", query)
    text_match = Video.search_vector.op("@@")(tsquery)
    similarity = func.word_similarity(query, Video.title)
    matches = or_(text_match, similarity >= TRIGRAM_THRESHOLD)

    base = select(Video).where(access.listable_filter(), matches)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    if sort == "date":
        order = (Video.published_at.desc(), Video.id)
    elif sort == "views":
        order = (Video.view_count.desc(), Video.id)
    else:
        rank = func.ts_rank(Video.search_vector, tsquery) + similarity
        order = (rank.desc(), Video.view_count.desc(), Video.id)

    rows = db.scalars(
        base.options(joinedload(Video.channel))
        .order_by(*order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique()
    return list(rows), total


def suggestions(db: Session, prefix: str, limit: int = 10) -> list[str]:
    """Titles for the search box dropdown: prefix matches first, then similar ones."""
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    starts = Video.title.ilike(f"{escaped}%")
    stmt = (
        select(Video.title)
        .where(
            access.listable_filter(),
            or_(starts, func.word_similarity(prefix, Video.title) >= TRIGRAM_THRESHOLD),
        )
        .group_by(Video.title)
        .order_by(
            func.bool_or(starts).desc(), func.max(func.word_similarity(prefix, Video.title)).desc()
        )
        .limit(limit)
    )
    return list(db.scalars(stmt))
