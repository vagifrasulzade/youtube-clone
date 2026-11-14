"""Enumerations shared by models, schemas and services."""

from enum import StrEnum


class RoleName(StrEnum):
    USER = "user"
    MODERATOR = "moderator"
    ADMIN = "admin"


# Seeded by the initial migration. Permission checks compare levels (admin ⊇ moderator ⊇ user).
ROLE_IDS: dict[RoleName, int] = {RoleName.USER: 1, RoleName.MODERATOR: 2, RoleName.ADMIN: 3}
ROLE_LEVELS: dict[RoleName, int] = {RoleName.USER: 0, RoleName.MODERATOR: 10, RoleName.ADMIN: 20}


class Visibility(StrEnum):
    PUBLIC = "public"
    UNLISTED = "unlisted"
    PRIVATE = "private"


class VideoStatus(StrEnum):
    AWAITING_UPLOAD = "awaiting_upload"
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ReportReason(StrEnum):
    SPAM = "spam"
    SEXUAL = "sexual"
    VIOLENT = "violent"
    HATEFUL = "hateful"
    HARASSMENT = "harassment"
    HARMFUL = "harmful"
    MISINFORMATION = "misinformation"
    COPYRIGHT = "copyright"
    OTHER = "other"


class ReportStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ModerationActionType(StrEnum):
    HIDE_VIDEO = "hide_video"
    RESTORE_VIDEO = "restore_video"
    DELETE_VIDEO = "delete_video"
    DELETE_COMMENT = "delete_comment"
    RESOLVE_REPORT = "resolve_report"
    DISMISS_REPORT = "dismiss_report"
    CHANGE_ROLE = "change_role"
    BAN_USER = "ban_user"
    UNBAN_USER = "unban_user"


class ModerationTargetType(StrEnum):
    VIDEO = "video"
    COMMENT = "comment"
    USER = "user"
    REPORT = "report"
