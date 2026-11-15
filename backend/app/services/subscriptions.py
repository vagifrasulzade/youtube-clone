"""Channel subscriptions (acceptance D3).

The (subscriber_id, channel_id) primary key makes subscribing idempotent; the counter
changes only when a row was really inserted or deleted, in the same transaction.
"""

from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, NotFoundError
from app.models import Channel, Subscription, User


def get_channel_by_handle(db: Session, handle: str) -> Channel:
    channel = db.scalar(select(Channel).where(Channel.handle == handle.strip().lower()))
    if channel is None:
        raise NotFoundError("Channel not found", code="channel_not_found")
    return channel


def _bump(db: Session, channel_id: object, delta: int) -> None:
    db.execute(
        update(Channel)
        .where(Channel.id == channel_id)
        .values(subscriber_count=Channel.subscriber_count + delta)
    )


def subscribe(db: Session, user: User, handle: str) -> Channel:
    channel = get_channel_by_handle(db, handle)
    if channel.user_id == user.id:
        raise BadRequestError("You cannot subscribe to your own channel", code="self_subscription")
    inserted = db.scalar(
        insert(Subscription)
        .values(subscriber_id=user.id, channel_id=channel.id)
        .on_conflict_do_nothing(index_elements=["subscriber_id", "channel_id"])
        .returning(Subscription.channel_id)
    )
    if inserted is not None:
        _bump(db, channel.id, 1)
    db.commit()
    db.refresh(channel)
    return channel


def unsubscribe(db: Session, user: User, handle: str) -> Channel:
    channel = get_channel_by_handle(db, handle)
    deleted = db.scalar(
        delete(Subscription)
        .where(Subscription.subscriber_id == user.id, Subscription.channel_id == channel.id)
        .returning(Subscription.channel_id)
    )
    if deleted is not None:
        _bump(db, channel.id, -1)
    db.commit()
    db.refresh(channel)
    return channel


def is_subscribed(db: Session, user: User | None, channel: Channel) -> bool:
    if user is None:
        return False
    return db.get(Subscription, (user.id, channel.id)) is not None


def subscribed_channels(db: Session, user: User) -> list[Channel]:
    return list(
        db.scalars(
            select(Channel)
            .join(Subscription, Subscription.channel_id == Channel.id)
            .where(Subscription.subscriber_id == user.id)
            .order_by(Channel.name)
        )
    )
