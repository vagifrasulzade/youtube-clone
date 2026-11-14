"""Channel profile operations."""

from __future__ import annotations

from typing import BinaryIO, Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Channel, User
from app.services import images
from app.storage import keys, s3

ChannelImage = Literal["avatar", "banner"]


def set_channel_image(db: Session, user: User, kind: ChannelImage, stream: BinaryIO) -> Channel:
    settings = get_settings()
    limit = settings.max_avatar_bytes if kind == "avatar" else settings.max_banner_bytes
    jpeg = images.reencode_jpeg(images.read_limited(stream, limit), kind)

    channel = user.channel
    key = keys.channel_avatar(channel.id) if kind == "avatar" else keys.channel_banner(channel.id)
    s3.put_bytes(settings.media_bucket, key, jpeg, content_type="image/jpeg")

    if kind == "avatar":
        channel.avatar_key = key
    else:
        channel.banner_key = key
    channel.updated_at = func.now()  # bumps the ?v= cache-buster even when the key is unchanged
    db.commit()
    db.refresh(channel)
    return channel
