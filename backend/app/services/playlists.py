"""Playlists: owner-managed ordered lists of videos.

Viewing follows the same visibility rules as videos (private playlist -> 404 for
others). Entries the viewer may not watch are shown as "Private video" placeholders,
as on YouTube, so a public playlist never leaks a private video's title.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models import Channel, Playlist, PlaylistVideo, User, Video
from app.models.enums import Visibility
from app.services import access


def _not_found() -> NotFoundError:
    return NotFoundError("Playlist not found", code="playlist_not_found")


def _is_owner(playlist: Playlist, user: User | None) -> bool:
    return user is not None and user.channel is not None and playlist.channel_id == user.channel.id


def get_viewable(db: Session, playlist_id: uuid.UUID, viewer: User | None) -> Playlist:
    playlist = db.get(Playlist, playlist_id)
    if playlist is None:
        raise _not_found()
    if playlist.visibility == Visibility.PRIVATE and not (
        _is_owner(playlist, viewer) or access.is_staff(viewer)
    ):
        raise _not_found()
    return playlist


def get_owned(db: Session, playlist_id: uuid.UUID, user: User) -> Playlist:
    playlist = get_viewable(db, playlist_id, user)
    if not _is_owner(playlist, user):
        raise ForbiddenError("Only the playlist owner can do this", code="not_owner")
    return playlist


def create(db: Session, user: User, *, title: str, description: str, visibility: Visibility):
    playlist = Playlist(
        channel_id=user.channel.id, title=title, description=description, visibility=visibility
    )
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    return playlist


def update_playlist(db: Session, user: User, playlist_id: uuid.UUID, changes: dict) -> Playlist:
    playlist = get_owned(db, playlist_id, user)
    for field, value in changes.items():
        setattr(playlist, field, value)
    db.commit()
    db.refresh(playlist)
    return playlist


def delete_playlist(db: Session, user: User, playlist_id: uuid.UUID) -> None:
    db.delete(get_owned(db, playlist_id, user))
    db.commit()


def entries(db: Session, playlist: Playlist) -> list[Video]:
    return list(
        db.scalars(
            select(Video)
            .options(joinedload(Video.channel))
            .join(PlaylistVideo, PlaylistVideo.video_id == Video.id)
            .where(PlaylistVideo.playlist_id == playlist.id)
            .order_by(PlaylistVideo.position)
        ).unique()
    )


def add_video(db: Session, user: User, playlist_id: uuid.UUID, video_id: str) -> None:
    playlist = get_owned(db, playlist_id, user)
    video = access.get_viewable_video_or_404(db, video_id, user)  # only videos you can watch
    next_position = db.scalar(
        select(func.coalesce(func.max(PlaylistVideo.position) + 1, 0)).where(
            PlaylistVideo.playlist_id == playlist.id
        )
    )
    db.add(PlaylistVideo(playlist_id=playlist.id, video_id=video.id, position=next_position))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("The video is already in this playlist", code="already_added") from exc


def remove_video(db: Session, user: User, playlist_id: uuid.UUID, video_id: str) -> None:
    playlist = get_owned(db, playlist_id, user)
    removed = db.scalar(
        delete(PlaylistVideo)
        .where(PlaylistVideo.playlist_id == playlist.id, PlaylistVideo.video_id == video_id)
        .returning(PlaylistVideo.position)
    )
    if removed is not None:  # close the gap so positions stay 0..n-1
        db.execute(
            update(PlaylistVideo)
            .where(PlaylistVideo.playlist_id == playlist.id, PlaylistVideo.position > removed)
            .values(position=PlaylistVideo.position - 1)
        )
    db.commit()


def reorder(db: Session, user: User, playlist_id: uuid.UUID, video_ids: list[str]) -> None:
    """`video_ids` must be exactly the current entries, in the new order."""
    playlist = get_owned(db, playlist_id, user)
    current = set(
        db.scalars(select(PlaylistVideo.video_id).where(PlaylistVideo.playlist_id == playlist.id))
    )
    if len(video_ids) != len(set(video_ids)) or set(video_ids) != current:
        raise BadRequestError("Send every video of the playlist exactly once", code="invalid_order")
    for position, video_id in enumerate(video_ids):
        db.execute(
            update(PlaylistVideo)
            .where(PlaylistVideo.playlist_id == playlist.id, PlaylistVideo.video_id == video_id)
            .values(position=position)
        )
    db.commit()  # the unique (playlist, position) constraint is checked here (deferred)


def channel_playlists(db: Session, channel: Channel, viewer: User | None) -> list[Playlist]:
    stmt = select(Playlist).where(Playlist.channel_id == channel.id)
    if not (viewer is not None and channel.user_id == viewer.id):
        stmt = stmt.where(Playlist.visibility == Visibility.PUBLIC)
    return list(db.scalars(stmt.order_by(Playlist.created_at.desc())))


def video_counts(db: Session, playlist_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not playlist_ids:
        return {}
    rows = db.execute(
        select(PlaylistVideo.playlist_id, func.count())
        .where(PlaylistVideo.playlist_id.in_(playlist_ids))
        .group_by(PlaylistVideo.playlist_id)
    )
    return {row[0]: row[1] for row in rows}
