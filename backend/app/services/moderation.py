"""Reports, hide/restore and the moderation audit log.

Every staff action writes an append-only `moderation_actions` row in the same
transaction as the change it records, with a snapshot (e.g. the video title) so the
audit trail survives deletion of the target.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import ModerationAction, Report, User, Video
from app.models.enums import (
    ModerationActionType,
    ModerationTargetType,
    ReportReason,
    ReportStatus,
)
from app.services import access


def audit(
    db: Session,
    actor: User,
    action: ModerationActionType,
    target_type: ModerationTargetType,
    target_id: str,
    *,
    reason: str | None = None,
    report_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        ModerationAction(
            actor_id=actor.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            report_id=report_id,
            details=details or {},
        )
    )


# --- reports (any signed-in user) ---------------------------------------------------


def create_report(
    db: Session, user: User, video_id: str, reason: ReportReason, details: str
) -> Report:
    video = access.get_viewable_video_or_404(db, video_id, user)  # cannot report the unseen
    report = Report(video_id=video.id, reporter_id=user.id, reason=reason, details=details)
    db.add(report)
    try:
        db.commit()
    except IntegrityError as exc:  # partial unique index: one open report per user+video
        db.rollback()
        raise ConflictError("You already reported this video", code="already_reported") from exc
    db.refresh(report)
    return report


# --- staff ----------------------------------------------------------------------------


def list_reports(
    db: Session, status: ReportStatus | None, page: int, page_size: int
) -> tuple[list[Report], int]:
    stmt = select(Report)
    if status is not None:
        stmt = stmt.where(Report.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Report.created_at.desc(), Report.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total


def get_report(db: Session, report_id: uuid.UUID) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise NotFoundError("Report not found", code="report_not_found")
    return report


def _set_hidden(db: Session, video: Video, hidden: bool) -> None:
    video.is_hidden = hidden
    video.hidden_at = datetime.now(UTC) if hidden else None


def hide_video(
    db: Session, actor: User, video_id: str, reason: str, report_id: uuid.UUID | None = None
) -> Video:
    video = access.get_video_or_404(db, video_id)
    if not video.is_hidden:
        _set_hidden(db, video, True)
        audit(
            db, actor, ModerationActionType.HIDE_VIDEO, ModerationTargetType.VIDEO, video.id,
            reason=reason, report_id=report_id, details={"title": video.title},
        )  # fmt: skip
    db.commit()
    db.refresh(video)
    return video


def restore_video(db: Session, actor: User, video_id: str, reason: str) -> Video:
    video = access.get_video_or_404(db, video_id)
    if video.is_hidden:
        _set_hidden(db, video, False)
        audit(
            db, actor, ModerationActionType.RESTORE_VIDEO, ModerationTargetType.VIDEO, video.id,
            reason=reason, details={"title": video.title},
        )  # fmt: skip
    db.commit()
    db.refresh(video)
    return video


def _close(db: Session, report: Report, actor: User, status: ReportStatus, note: str) -> None:
    if report.status != ReportStatus.OPEN:
        raise ConflictError("This report is already closed", code="report_closed")
    report.status = status
    report.resolved_by_id = actor.id
    report.resolved_at = datetime.now(UTC)
    report.resolution_note = note


def resolve_report(
    db: Session, actor: User, report_id: uuid.UUID, *, hide: bool, note: str
) -> Report:
    report = get_report(db, report_id)
    _close(db, report, actor, ReportStatus.RESOLVED, note)
    audit(
        db, actor, ModerationActionType.RESOLVE_REPORT, ModerationTargetType.REPORT,
        str(report.id), reason=note, report_id=report.id, details={"hide_video": hide},
    )  # fmt: skip
    if hide:
        video = access.get_video_or_404(db, report.video_id)
        if not video.is_hidden:
            _set_hidden(db, video, True)
            audit(
                db, actor, ModerationActionType.HIDE_VIDEO, ModerationTargetType.VIDEO, video.id,
                reason=note, report_id=report.id, details={"title": video.title},
            )  # fmt: skip
        # A hidden video needs no further review: close its other open reports too.
        db.execute(
            update(Report)
            .where(Report.video_id == video.id, Report.status == ReportStatus.OPEN)
            .values(
                status=ReportStatus.RESOLVED,
                resolved_by_id=actor.id,
                resolved_at=datetime.now(UTC),
                resolution_note=note,
            )
        )
    db.commit()
    db.refresh(report)
    return report


def dismiss_report(db: Session, actor: User, report_id: uuid.UUID, note: str) -> Report:
    report = get_report(db, report_id)
    _close(db, report, actor, ReportStatus.DISMISSED, note)
    audit(
        db, actor, ModerationActionType.DISMISS_REPORT, ModerationTargetType.REPORT,
        str(report.id), reason=note, report_id=report.id,
    )  # fmt: skip
    db.commit()
    db.refresh(report)
    return report


def list_actions(
    db: Session, target_type: ModerationTargetType | None, page: int, page_size: int
) -> tuple[list[ModerationAction], int]:
    stmt = select(ModerationAction)
    if target_type is not None:
        stmt = stmt.where(ModerationAction.target_type == target_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(ModerationAction.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return list(rows), total
