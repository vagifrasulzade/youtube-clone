"""Admin dashboard endpoints: administrators only (role checked from the database)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import AdminUser, DbSession
from app.models import User
from app.models.enums import RoleName, VideoStatus
from app.schemas.common import RequestModel
from app.schemas.moderation import Note, NoteRequest
from app.schemas.pages import NumberedPage
from app.schemas.video import VideoOwnerOut
from app.services import admin as service

router = APIRouter(prefix="/admin", tags=["admin"])

Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=50)]
SearchText = Annotated[str | None, Query(max_length=100)]


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    handle: str
    name: str
    role: RoleName
    banned_at: datetime | None
    ban_reason: str | None
    created_at: datetime
    last_login_at: datetime | None

    @classmethod
    def from_model(cls, user: User) -> AdminUserOut:
        return cls(
            id=user.id,
            email=user.email,
            handle=user.channel.handle,
            name=user.channel.name,
            role=user.role.name,
            banned_at=user.banned_at,
            ban_reason=user.ban_reason,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )


class RoleChange(RequestModel):
    role: RoleName


class BanRequest(RequestModel):
    reason: Note


@router.get("/stats", summary="Dashboard statistics")
def stats(admin: AdminUser, db: DbSession) -> dict[str, Any]:
    return service.stats(db)


@router.get("/users", summary="Users (search by email or handle)")
def users(
    admin: AdminUser,
    db: DbSession,
    q: SearchText = None,
    role: RoleName | None = None,
    banned: bool | None = None,
    page: Page = 1,
    page_size: PageSize = 20,
) -> NumberedPage[AdminUserOut]:
    items, total = service.list_users(
        db, q=q, role=role, banned=banned, page=page, page_size=page_size
    )
    return NumberedPage(
        items=[AdminUserOut.from_model(u) for u in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/users/{user_id}/role", summary="Change a user's role (audited)")
def change_role(
    user_id: uuid.UUID, body: RoleChange, admin: AdminUser, db: DbSession
) -> AdminUserOut:
    return AdminUserOut.from_model(service.change_role(db, admin, user_id, body.role))


@router.post("/users/{user_id}/ban", summary="Ban a user; their sessions end immediately")
def ban(user_id: uuid.UUID, body: BanRequest, admin: AdminUser, db: DbSession) -> AdminUserOut:
    return AdminUserOut.from_model(service.ban(db, admin, user_id, body.reason))


@router.post("/users/{user_id}/unban", summary="Lift a ban")
def unban(user_id: uuid.UUID, body: NoteRequest, admin: AdminUser, db: DbSession) -> AdminUserOut:
    return AdminUserOut.from_model(service.unban(db, admin, user_id, body.note))


@router.get("/videos", summary="All videos (any state)")
def videos(
    admin: AdminUser,
    db: DbSession,
    q: SearchText = None,
    status: VideoStatus | None = None,
    hidden: bool | None = None,
    page: Page = 1,
    page_size: PageSize = 20,
) -> NumberedPage[VideoOwnerOut]:
    items, total = service.list_videos(
        db, q=q, status=status, hidden=hidden, page=page, page_size=page_size
    )
    return NumberedPage(
        items=[VideoOwnerOut.from_model(v) for v in items],
        total=total,
        page=page,
        page_size=page_size,
    )
