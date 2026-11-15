"""Playlist endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, OptionalUser
from app.models import Channel, Playlist, User
from app.schemas.pages import ChannelBrief, VideoCard
from app.schemas.playlist import (
    PlaylistAddVideo,
    PlaylistCard,
    PlaylistCreate,
    PlaylistEntry,
    PlaylistOrder,
    PlaylistOut,
    PlaylistUpdate,
)
from app.services import access
from app.services import playlists as service

router = APIRouter(prefix="/playlists", tags=["playlists"])


def playlist_detail(db: Session, playlist: Playlist, viewer: User | None) -> PlaylistOut:
    channel = db.get(Channel, playlist.channel_id)
    entries = []
    for position, video in enumerate(service.entries(db, playlist)):
        visible = access.can_view(db, video, viewer)
        entries.append(
            PlaylistEntry(
                position=position,
                video=VideoCard.from_model(video, viewer) if visible else None,
                title=video.title if visible else "Private video",
            )
        )
    return PlaylistOut(
        id=playlist.id,
        title=playlist.title,
        description=playlist.description,
        visibility=playlist.visibility,
        channel=ChannelBrief.from_model(channel),
        is_owner=viewer is not None and channel.user_id == viewer.id,
        entries=entries,
    )


def playlist_cards(db: Session, items: list[Playlist], viewer: User | None) -> list[PlaylistCard]:
    counts = service.video_counts(db, [p.id for p in items])
    result = []
    for playlist in items:
        first = next(
            (v for v in service.entries(db, playlist) if access.can_view(db, v, viewer)), None
        )
        result.append(
            PlaylistCard(
                id=playlist.id,
                title=playlist.title,
                visibility=playlist.visibility,
                video_count=counts.get(playlist.id, 0),
                thumbnail_url=VideoCard.from_model(first, viewer).thumbnail_url if first else None,
                updated_at=playlist.updated_at,
            )
        )
    return result


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a playlist")
def create_playlist(body: PlaylistCreate, user: CurrentUser, db: DbSession) -> PlaylistOut:
    playlist = service.create(
        db, user, title=body.title, description=body.description, visibility=body.visibility
    )
    return playlist_detail(db, playlist, user)


@router.get("/{playlist_id}", summary="Playlist with its entries")
def get_playlist(playlist_id: uuid.UUID, viewer: OptionalUser, db: DbSession) -> PlaylistOut:
    return playlist_detail(db, service.get_viewable(db, playlist_id, viewer), viewer)


@router.patch("/{playlist_id}", summary="Edit a playlist (owner)")
def update_playlist(
    playlist_id: uuid.UUID, body: PlaylistUpdate, user: CurrentUser, db: DbSession
) -> PlaylistOut:
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    return playlist_detail(db, service.update_playlist(db, user, playlist_id, changes), user)


@router.delete("/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete")
def delete_playlist(playlist_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    service.delete_playlist(db, user, playlist_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{playlist_id}/videos", status_code=status.HTTP_201_CREATED, summary="Add a video")
def add_video(
    playlist_id: uuid.UUID, body: PlaylistAddVideo, user: CurrentUser, db: DbSession
) -> PlaylistOut:
    service.add_video(db, user, playlist_id, body.video_id)
    return playlist_detail(db, service.get_owned(db, playlist_id, user), user)


@router.delete(
    "/{playlist_id}/videos/{video_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a video",
)
def remove_video(
    playlist_id: uuid.UUID, video_id: str, user: CurrentUser, db: DbSession
) -> Response:
    service.remove_video(db, user, playlist_id, video_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{playlist_id}/videos", summary="Reorder (send every video id once)")
def reorder(
    playlist_id: uuid.UUID, body: PlaylistOrder, user: CurrentUser, db: DbSession
) -> PlaylistOut:
    service.reorder(db, user, playlist_id, body.video_ids)
    return playlist_detail(db, service.get_owned(db, playlist_id, user), user)
