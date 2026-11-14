"""Reports and the append-only moderation audit log."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_column, str_enum, uuid_pk
from app.models.enums import ModerationActionType, ModerationTargetType, ReportReason, ReportStatus
from app.models.video import VIDEO_ID_LENGTH


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = uuid_pk()
    video_id: Mapped[str] = mapped_column(
        String(VIDEO_ID_LENGTH), ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[ReportReason] = mapped_column(str_enum(ReportReason, "reason"))
    details: Mapped[str] = mapped_column(String(1000), default="", server_default="")
    status: Mapped[ReportStatus] = mapped_column(
        str_enum(ReportStatus, "status"),
        default=ReportStatus.OPEN,
        server_default=ReportStatus.OPEN.value,
    )
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    resolved_at: Mapped[datetime | None]
    resolution_note: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = created_at_column()


# One *open* report per user per video; a new one is allowed after resolution.
Index(
    "uq_reports_open_per_reporter",
    Report.video_id,
    Report.reporter_id,
    unique=True,
    postgresql_where=text("status = 'open'"),
)
Index("ix_reports_status_created", Report.status, Report.created_at)


class ModerationAction(Base):
    """Append-only audit log.

    The target is polymorphic (no FK) on purpose: audit rows must survive deletion
    of the video/comment they describe. `details` keeps a snapshot (title, old/new role...).
    """

    __tablename__ = "moderation_actions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[ModerationActionType] = mapped_column(str_enum(ModerationActionType, "action"))
    target_type: Mapped[ModerationTargetType] = mapped_column(
        str_enum(ModerationTargetType, "target_type")
    )
    target_id: Mapped[str] = mapped_column(String(64))
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reports.id", ondelete="SET NULL"), index=True
    )
    reason: Mapped[str | None] = mapped_column(String(1000))
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = created_at_column()


Index("ix_moderation_actions_target", ModerationAction.target_type, ModerationAction.target_id)
Index("ix_moderation_actions_created", ModerationAction.created_at.desc())
