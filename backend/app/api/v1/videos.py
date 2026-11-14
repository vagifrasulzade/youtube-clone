"""Video upload and owner management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, UploadFile, status
from redis.exceptions import RedisError

from app.api.deps import CurrentUser, DbSession, OptionalUser, RedisClient
from app.core import rate_limit
from app.schemas.video import (
    UploadCreatedOut,
    UploadPolicyOut,
    UploadRequest,
    VideoDetailOut,
    VideoOwnerOut,
    VideoStatusOut,
    VideoUpdateRequest,
)
from app.services import access, uploads
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
