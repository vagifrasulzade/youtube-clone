"""Comment endpoints (docs/api.md § Comments). Rules live in app.services.comments."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, DbSession, OptionalUser, RedisClient
from app.core import rate_limit
from app.schemas.comment import CommentCreate, CommentOut, CommentUpdate
from app.schemas.pages import CursorPage
from app.services import comments as service

router = APIRouter(tags=["comments"])

Limit = Annotated[int, Query(ge=1, le=50)]
Cursor = Annotated[str | None, Query(max_length=200)]


@router.get("/videos/{video_id}/comments", summary="Top-level comments of a video")
def list_comments(
    video_id: str,
    viewer: OptionalUser,
    db: DbSession,
    sort: service.CommentSort = "newest",
    limit: Limit = 20,
    cursor: Cursor = None,
) -> CursorPage[CommentOut]:
    video, items, next_cursor = service.list_top_level(
        db, video_id, viewer, sort=sort, limit=limit, cursor=cursor
    )
    return service.build_page(items, next_cursor, video, viewer)


@router.post(
    "/videos/{video_id}/comments",
    status_code=status.HTTP_201_CREATED,
    summary="Comment, or reply to a top-level comment",
)
def create_comment(
    video_id: str, body: CommentCreate, user: CurrentUser, db: DbSession, redis: RedisClient
) -> CommentOut:
    rate_limit.hit(redis, f"comment-create:user:{user.id}", limit=20, window_seconds=60)
    comment, video = service.create(db, user, video_id, body=body.body, parent_id=body.parent_id)
    return service.build_out(comment, video, user)


@router.get("/comments/{comment_id}/replies", summary="Replies to a comment (oldest first)")
def list_replies(
    comment_id: uuid.UUID,
    viewer: OptionalUser,
    db: DbSession,
    limit: Limit = 20,
    cursor: Cursor = None,
) -> CursorPage[CommentOut]:
    video, items, next_cursor = service.list_replies(
        db, comment_id, viewer, limit=limit, cursor=cursor
    )
    return service.build_page(items, next_cursor, video, viewer)


@router.patch("/comments/{comment_id}", summary="Edit your comment")
def edit_comment(
    comment_id: uuid.UUID,
    body: CommentUpdate,
    user: CurrentUser,
    db: DbSession,
    redis: RedisClient,
) -> CommentOut:
    rate_limit.hit(redis, f"comment-edit:user:{user.id}", limit=30, window_seconds=60)
    comment, video = service.edit(db, user, comment_id, body.body)
    return service.build_out(comment, video, user)


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a comment (author, video owner, moderator, admin)",
)
def delete_comment(comment_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    service.remove(db, user, comment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
