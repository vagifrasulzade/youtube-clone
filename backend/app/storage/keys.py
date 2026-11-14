"""Object key builders.

Keys are built ONLY from server-generated ids (11-char video ids, UUIDs), never from
user input such as filenames, so they cannot contain path tricks and are safe to
forward unmodified in nginx X-Accel redirects.
"""

import uuid


def video_source(video_id: str) -> str:
    """Raw upload in the uploads bucket."""
    return f"{video_id}/source"


def video_prefix(video_id: str) -> str:
    return f"videos/{video_id}/"


def video_playback(video_id: str) -> str:
    return f"{video_prefix(video_id)}playback.mp4"


def video_thumbnail(video_id: str, choice: str) -> str:
    """choice: 'auto_1'..'auto_3' (generated frames) or 'custom' (uploaded)."""
    return f"{video_prefix(video_id)}thumb-{choice}.jpg"


def channel_avatar(channel_id: uuid.UUID) -> str:
    return f"channels/{channel_id}/avatar.jpg"


def channel_banner(channel_id: uuid.UUID) -> str:
    return f"channels/{channel_id}/banner.jpg"
