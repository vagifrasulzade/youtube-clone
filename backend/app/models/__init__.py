"""Import every model so `Base.metadata` is complete (Alembic, tests)."""

from app.models.channel import Channel, Subscription
from app.models.comment import Comment
from app.models.moderation import ModerationAction, Report
from app.models.playlist import Playlist, PlaylistVideo
from app.models.user import RefreshToken, Role, User
from app.models.video import Video, VideoPermission, VideoReaction, VideoView

__all__ = [
    "Channel",
    "Comment",
    "ModerationAction",
    "Playlist",
    "PlaylistVideo",
    "RefreshToken",
    "Report",
    "Role",
    "Subscription",
    "User",
    "Video",
    "VideoPermission",
    "VideoReaction",
    "VideoView",
]
