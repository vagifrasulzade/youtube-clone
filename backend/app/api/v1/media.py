"""Media endpoints consumed by <video> and <img> (not JSON).

Authorization runs on EVERY request, including each Range request of a playing video,
so revoking access or hiding a video stops playback at the next request (C4).
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Request, Response

from app.api.deps import DbSession
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.models import Channel
from app.models.enums import VideoStatus
from app.services import access, media_delivery, media_tokens
from app.services.media_urls import is_openly_viewable
from app.storage import keys

router = APIRouter(prefix="/media", tags=["media"])

ThumbnailChoice = Literal["auto_1", "auto_2", "auto_3", "custom"]


@router.get("/videos/{video_id}/stream", summary="Video stream (supports HTTP Range)")
def stream_video(video_id: str, request: Request, db: DbSession, t: str | None = None) -> Response:
    viewer = media_tokens.viewer_from_media_token(db, t, video_id)
    video = access.get_viewable_video_or_404(db, video_id, viewer)
    if video.status != VideoStatus.READY or not video.playback_key:
        raise NotFoundError("Video is not ready yet", code="video_not_ready")
    return media_delivery.serve_object(
        request,
        get_settings().media_bucket,
        video.playback_key,
        content_type="video/mp4",
        cache_control=media_delivery.cache_control_for(is_openly_viewable(video)),
    )


@router.get("/videos/{video_id}/thumbnail", summary="Selected thumbnail (JPEG)")
def video_thumbnail(
    video_id: str, request: Request, db: DbSession, t: str | None = None
) -> Response:
    viewer = media_tokens.viewer_from_media_token(db, t, video_id)
    video = access.get_viewable_video_or_404(db, video_id, viewer)
    if not video.thumbnail_key:
        raise NotFoundError("No thumbnail yet", code="thumbnail_not_found")
    return media_delivery.serve_object(
        request,
        get_settings().media_bucket,
        video.thumbnail_key,
        content_type="image/jpeg",
        cache_control=media_delivery.cache_control_for(is_openly_viewable(video)),
    )


@router.get(
    "/videos/{video_id}/thumbnails/{choice}",
    summary="A thumbnail candidate, for the owner's picker in Studio",
)
def video_thumbnail_candidate(
    video_id: str, choice: ThumbnailChoice, request: Request, db: DbSession, t: str | None = None
) -> Response:
    viewer = media_tokens.viewer_from_media_token(db, t, video_id)
    video = access.get_viewable_video_or_404(db, video_id, viewer)
    if not access.is_owner(video, viewer):
        raise NotFoundError("Thumbnail not found", code="thumbnail_not_found")
    return media_delivery.serve_object(
        request,
        get_settings().media_bucket,
        keys.video_thumbnail(video.id, choice),
        content_type="image/jpeg",
        cache_control="private, no-store",
    )


def _channel_image(channel_id: str, db: DbSession, attr: Literal["avatar_key", "banner_key"]):
    try:
        channel = db.get(Channel, uuid.UUID(channel_id))
    except ValueError:
        channel = None
    key = getattr(channel, attr, None) if channel else None
    if not key:
        raise NotFoundError("Image not found", code="image_not_found")
    return key


@router.get("/channels/{channel_id}/avatar", summary="Channel avatar (public)")
def channel_avatar(channel_id: str, request: Request, db: DbSession) -> Response:
    key = _channel_image(channel_id, db, "avatar_key")
    return media_delivery.serve_object(
        request,
        get_settings().media_bucket,
        key,
        content_type="image/jpeg",
        cache_control="public, max-age=86400",
    )


@router.get("/channels/{channel_id}/banner", summary="Channel banner (public)")
def channel_banner(channel_id: str, request: Request, db: DbSession) -> Response:
    key = _channel_image(channel_id, db, "banner_key")
    return media_delivery.serve_object(
        request,
        get_settings().media_bucket,
        key,
        content_type="image/jpeg",
        cache_control="public, max-age=86400",
    )
