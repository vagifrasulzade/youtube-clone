"""Video upload and owner management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, UploadFile, status
from redis.exceptions import RedisError

from app.api.deps import CurrentUser, DbSession, OptionalUser, RedisClient
from app.core import rate_limit
from app.schemas.pages import CursorPage, VideoCard
from app.schemas.video import (
    ReactionOut,
    ReactionRequest,
    UploadCreatedOut,
    UploadPolicyOut,
    UploadRequest,
    VideoDetailOut,
    VideoOwnerOut,
    VideoStatusOut,
    VideoUpdateRequest,
)
from app.services import access, feeds, reactions, uploads, views
from app.services import videos as video_service

router = APIRouter(prefix="/videos", tags=["videos"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a private draft and get a storage upload policy",
)
def create_upload(
    body: UploadRequest, user: CurrentUser, db: DbSession, redis: RedisClient
) -> UploadCreatedOut:
    rate_limit.hit(redis, f"upload:user:{user.id}", limit=20, window_seconds=3600)
    ticket = uploads.create_draft(
        db,
        user,
        filename=body.filename,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        title=body.title,
    )
    return UploadCreatedOut(
        video=VideoOwnerOut.from_model(ticket.video),
        upload=UploadPolicyOut(
            url=ticket.url,
            fields=ticket.fields,
            expires_at=ticket.expires_at,
            max_bytes=ticket.max_bytes,
        ),
    )


@router.post(
    "/{video_id}/upload-complete",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Confirm the file was uploaded; starts processing",
)
def complete_upload(video_id: str, user: CurrentUser, db: DbSession) -> VideoStatusOut:
    video = uploads.complete_upload(db, user, video_id)
    return VideoStatusOut(id=video.id, status=video.status)


@router.get("/{video_id}/status", summary="Processing status (owner only)")
def video_status(
    video_id: str, user: CurrentUser, db: DbSession, redis: RedisClient
) -> VideoStatusOut:
    video = access.get_owned_video(db, video_id, user)
    progress: int | None = None
    try:
        raw = redis.get(f"proc:{video.id}")
        progress = int(raw) if raw is not None else None
    except (RedisError, ValueError):
        progress = None  # progress is best-effort; the status itself comes from the DB
    return VideoStatusOut(
        id=video.id, status=video.status, progress=progress, error=video.processing_error
    )


@router.patch("/{video_id}", summary="Edit title, description or visibility (owner only)")
def update_video(
    video_id: str, body: VideoUpdateRequest, user: CurrentUser, db: DbSession
) -> VideoOwnerOut:
    video = access.get_owned_video(db, video_id, user)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    thumbnail = changes.pop("thumbnail", None)
    for field, value in changes.items():
        setattr(video, field, value)
    if thumbnail is not None:
        video_service.select_thumbnail(video, thumbnail)
    db.commit()
    db.refresh(video)
    return VideoOwnerOut.from_model(video)


@router.get("", summary="Home feed (public videos, newest first)")
def home_feed(
    viewer: OptionalUser, db: DbSession, cursor: str | None = None, limit: int = 24
) -> CursorPage[VideoCard]:
    items, next_cursor = feeds.home_feed(db, cursor, limit)
    return CursorPage(
        items=[VideoCard.from_model(v, viewer) for v in items], next_cursor=next_cursor
    )


@router.get("/{video_id}/related", summary="Related videos for the watch page")
def related(video_id: str, viewer: OptionalUser, db: DbSession, limit: int = 20) -> list[VideoCard]:
    video = access.get_viewable_video_or_404(db, video_id, viewer)
    return [VideoCard.from_model(v, viewer) for v in feeds.related_videos(db, video, limit)]


@router.get("/{video_id}", summary="Watch page details (404 if you may not see it)")
def get_video(video_id: str, viewer: OptionalUser, db: DbSession) -> VideoDetailOut:
    video = access.get_viewable_video_or_404(db, video_id, viewer)
    return VideoDetailOut.build(
        video,
        viewer,
        my_reaction=video_service.my_reaction(db, video, viewer),
        is_subscribed=video_service.is_subscribed(db, video, viewer),
        can_edit=access.is_owner(video, viewer),
    )


@router.put(
    "/{video_id}/thumbnail",
    summary="Upload a custom thumbnail (JPEG/PNG/WebP, re-encoded; owner only)",
    dependencies=[
        Depends(rate_limit.limit_by_ip("video-thumbnail", limit=30, window_seconds=3600))
    ],
)
def upload_thumbnail(
    video_id: str, file: UploadFile, user: CurrentUser, db: DbSession
) -> VideoOwnerOut:
    video = access.get_owned_video(db, video_id, user)
    return VideoOwnerOut.from_model(video_service.upload_custom_thumbnail(db, video, file.file))


@router.delete(
    "/{video_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a video (owner or admin); storage is cleaned up asynchronously",
)
def delete_video(video_id: str, user: CurrentUser, db: DbSession) -> Response:
    video_service.delete_video(db, video_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{video_id}/reaction", summary="Like or dislike (idempotent)")
def set_reaction(
    video_id: str, body: ReactionRequest, user: CurrentUser, db: DbSession
) -> ReactionOut:
    video = reactions.set_reaction(db, user, video_id, body.value)
    return ReactionOut(
        like_count=video.like_count, dislike_count=video.dislike_count, my_reaction=body.value
    )


@router.delete("/{video_id}/reaction", summary="Remove my like/dislike (idempotent)")
def remove_reaction(video_id: str, user: CurrentUser, db: DbSession) -> ReactionOut:
    video = reactions.remove_reaction(db, user, video_id)
    return ReactionOut(
        like_count=video.like_count, dislike_count=video.dislike_count, my_reaction=None
    )


@router.post(
    "/{video_id}/views",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Count a view (at most once per viewer per 24 h)",
    dependencies=[Depends(rate_limit.limit_by_ip("views", limit=120, window_seconds=60))],
)
def record_view(
    video_id: str, request: Request, viewer: OptionalUser, db: DbSession, redis: RedisClient
) -> dict[str, bool]:
    counted = views.record_view(db, redis, video_id, viewer, rate_limit.client_ip(request))
    return {"counted": counted}
