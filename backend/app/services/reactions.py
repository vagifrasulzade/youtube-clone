"""Likes and dislikes (acceptance D1).

One row per (user, video) enforced by the primary key. Counters on the video change in
the same transaction, by atomic SQL increments, so they always equal the row counts.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import User, Video, VideoReaction
from app.services import access

Reaction = Literal["like", "dislike"]


def _value(reaction: Reaction) -> int:
    return 1 if reaction == "like" else -1


def _apply_counts(db: Session, video_id: str, likes: int, dislikes: int) -> None:
    if likes == 0 and dislikes == 0:
        return
    db.execute(
        update(Video)
        .where(Video.id == video_id)
        .values(
            like_count=Video.like_count + likes,
            dislike_count=Video.dislike_count + dislikes,
        )
    )


def _counts_for(value: int) -> tuple[int, int]:
    return (1, 0) if value > 0 else (0, 1)


def set_reaction(db: Session, user: User, video_id: str, reaction: Reaction) -> Video:
    video = access.get_viewable_video_or_404(db, video_id, user)
    new_value = _value(reaction)

    inserted = db.scalar(
        insert(VideoReaction)
        .values(user_id=user.id, video_id=video.id, value=new_value)
        .on_conflict_do_nothing(index_elements=["user_id", "video_id"])
        .returning(VideoReaction.value)
    )
    if inserted is not None:
        likes, dislikes = _counts_for(new_value)
        _apply_counts(db, video.id, likes, dislikes)
    else:
        existing = db.scalar(
            select(VideoReaction)
            .where(VideoReaction.user_id == user.id, VideoReaction.video_id == video.id)
            .with_for_update()
        )
        if existing is not None and existing.value != new_value:
            old_likes, old_dislikes = _counts_for(existing.value)
            new_likes, new_dislikes = _counts_for(new_value)
            existing.value = new_value
            _apply_counts(db, video.id, new_likes - old_likes, new_dislikes - old_dislikes)
    db.commit()
    db.refresh(video)
    return video


def remove_reaction(db: Session, user: User, video_id: str) -> Video:
    video = access.get_viewable_video_or_404(db, video_id, user)
    existing = db.scalar(
        select(VideoReaction)
        .where(VideoReaction.user_id == user.id, VideoReaction.video_id == video.id)
        .with_for_update()
    )
    if existing is not None:
        likes, dislikes = _counts_for(existing.value)
        db.delete(existing)
        _apply_counts(db, video.id, -likes, -dislikes)
    db.commit()
    db.refresh(video)
    return video
