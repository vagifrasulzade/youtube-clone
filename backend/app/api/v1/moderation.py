"""Moderation endpoints: moderators and admins only (role checked from the database)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, ModeratorUser
from app.models.enums import ModerationTargetType, ReportStatus
from app.schemas.moderation import (
    ModerationActionOut,
    NoteRequest,
    ReportOut,
    ResolveRequest,
)
from app.schemas.pages import NumberedPage
from app.schemas.video import VideoOwnerOut
from app.services import moderation as service

router = APIRouter(prefix="/moderation", tags=["moderation"])

Page = Annotated[int, Query(ge=1, le=10_000)]
PageSize = Annotated[int, Query(ge=1, le=50)]


@router.get("/reports", summary="Report queue")
def list_reports(
    staff: ModeratorUser,
    db: DbSession,
    status: ReportStatus | None = ReportStatus.OPEN,
    page: Page = 1,
    page_size: PageSize = 20,
) -> NumberedPage[ReportOut]:
    items, total = service.list_reports(db, status, page, page_size)
    return NumberedPage(
        items=[ReportOut.from_model(r) for r in items], total=total, page=page, page_size=page_size
    )


@router.get("/reports/{report_id}", summary="One report")
def get_report(report_id: uuid.UUID, staff: ModeratorUser, db: DbSession) -> ReportOut:
    return ReportOut.from_model(service.get_report(db, report_id))


@router.post("/reports/{report_id}/resolve", summary="Resolve (optionally hiding the video)")
def resolve(
    report_id: uuid.UUID, body: ResolveRequest, staff: ModeratorUser, db: DbSession
) -> ReportOut:
    report = service.resolve_report(db, staff, report_id, hide=body.hide_video, note=body.note)
    return ReportOut.from_model(report)


@router.post("/reports/{report_id}/dismiss", summary="Dismiss a report")
def dismiss(
    report_id: uuid.UUID, body: NoteRequest, staff: ModeratorUser, db: DbSession
) -> ReportOut:
    return ReportOut.from_model(service.dismiss_report(db, staff, report_id, body.note))


@router.post("/videos/{video_id}/hide", summary="Hide a video from everyone but owner and staff")
def hide(video_id: str, body: NoteRequest, staff: ModeratorUser, db: DbSession) -> VideoOwnerOut:
    return VideoOwnerOut.from_model(service.hide_video(db, staff, video_id, body.note))


@router.post("/videos/{video_id}/restore", summary="Make a hidden video visible again")
def restore(video_id: str, body: NoteRequest, staff: ModeratorUser, db: DbSession) -> VideoOwnerOut:
    return VideoOwnerOut.from_model(service.restore_video(db, staff, video_id, body.note))


@router.get("/actions", summary="Audit log of moderation actions")
def actions(
    staff: ModeratorUser,
    db: DbSession,
    target_type: ModerationTargetType | None = None,
    page: Page = 1,
    page_size: PageSize = 50,
) -> NumberedPage[ModerationActionOut]:
    items, total = service.list_actions(db, target_type, page, page_size)
    return NumberedPage(
        items=[ModerationActionOut.from_model(a) for a in items],
        total=total,
        page=page,
        page_size=page_size,
    )
