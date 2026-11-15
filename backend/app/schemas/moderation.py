"""Report and moderation schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field

from app.models import ModerationAction, Report
from app.models.enums import ModerationActionType, ModerationTargetType, ReportReason, ReportStatus
from app.schemas.common import MultiLineText, RequestModel

Note = Annotated[MultiLineText, Field(min_length=1, max_length=1000)]


class ReportCreate(RequestModel):
    reason: ReportReason
    details: Annotated[MultiLineText, Field(max_length=1000)] = ""


class ReportOut(BaseModel):
    id: uuid.UUID
    video_id: str
    reporter_id: uuid.UUID
    reason: ReportReason
    details: str
    status: ReportStatus
    resolved_by_id: uuid.UUID | None
    resolved_at: datetime | None
    resolution_note: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, report: Report) -> ReportOut:
        return cls.model_validate(report, from_attributes=True)


class ResolveRequest(RequestModel):
    hide_video: bool = False
    note: Note


class NoteRequest(RequestModel):
    note: Note


class ModerationActionOut(BaseModel):
    id: int
    actor_id: uuid.UUID | None
    action: ModerationActionType
    target_type: ModerationTargetType
    target_id: str
    report_id: uuid.UUID | None
    reason: str | None
    details: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_model(cls, action: ModerationAction) -> ModerationActionOut:
        return cls.model_validate(action, from_attributes=True)
