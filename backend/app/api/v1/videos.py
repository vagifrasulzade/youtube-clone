"""Video upload and owner management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status
from redis.exceptions import RedisError

from app.api.deps import CurrentUser, DbSession, RedisClient
from app.core import rate_limit
from app.schemas.video import (
    UploadCreatedOut,
    UploadPolicyOut,
    UploadRequest,
    VideoOwnerOut,
    VideoStatusOut,
    VideoUpdateRequest,
)
from app.services import access, uploads

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
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(video, field, value)
    db.commit()
    db.refresh(video)
    return VideoOwnerOut.from_model(video)
