"""Administrator operations: statistics, user management, role changes, bans.

Guardrails (docs/security.md § 3.1, acceptance E4):
- an admin cannot change their own role or ban themselves
- another admin cannot be banned without being demoted first
- the last remaining admin can never be demoted
Every action is written to the moderation audit log in the same transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.models import Channel, Report, User, Video
from app.models.enums import (
    ROLE_IDS,
    ModerationActionType,
    ModerationTargetType,
    ReportStatus,
    RoleName,
    VideoStatus,
)
from app.services.auth import revoke_all_sessions
from app.services.moderation import audit


def stats(db: Session) -> dict:
    by_status = dict(db.execute(select(Video.status, func.count()).group_by(Video.status)).all())
    week_ago = datetime.now(UTC) - timedelta(days=7)
    return {
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "banned_users": db.scalar(select(func.count()).where(User.banned_at.is_not(None))) or 0,
        "videos_by_status": {s.value: int(by_status.get(s, 0)) for s in VideoStatus},
        "views_total": int(db.scalar(select(func.coalesce(func.sum(Video.view_count), 0))) or 0),
        "storage_bytes": int(
            db.scalar(select(func.coalesce(func.sum(Video.playback_size_bytes), 0))) or 0
        ),
        "open_reports": db.scalar(select(func.count()).where(Report.status == ReportStatus.OPEN))
        or 0,
        "signups_7d": db.scalar(select(func.count()).where(User.created_at >= week_ago)) or 0,
    }


def list_users(
    db: Session,
    *,
    q: str | None,
    role: RoleName | None,
    banned: bool | None,
    page: int,
    page_size: int,
) -> tuple[list[User], int]:
    stmt = select(User).join(Channel, Channel.user_id == User.id)
    if q:
        like = "%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(User.email.like(like), Channel.handle.like(like)))
    if role is not None:
        stmt = stmt.where(User.role_id == ROLE_IDS[role])
    if banned is not None:
        stmt = stmt.where(User.banned_at.is_not(None) if banned else User.banned_at.is_(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.options(joinedload(User.channel))
        .order_by(User.created_at.desc(), User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique()
    return list(rows), total


def _get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found", code="user_not_found")
    return user


def _admin_count(db: Session) -> int:
    """Counts admins while locking their rows, so two admins demoting each other at the
    same moment are serialized and cannot leave the system with zero admins."""
    admin_ids = db.scalars(
        select(User.id).where(User.role_id == ROLE_IDS[RoleName.ADMIN]).with_for_update()
    ).all()
    return len(admin_ids)


def change_role(db: Session, actor: User, user_id: uuid.UUID, role: RoleName) -> User:
    target = _get_user(db, user_id)
    if target.id == actor.id:
        raise BadRequestError("You cannot change your own role", code="self_role_change")
    old = target.role.name
    if old == role:
        return target
    if old == RoleName.ADMIN and _admin_count(db) <= 1:
        raise ConflictError("The last admin cannot be demoted", code="last_admin")
    target.role_id = ROLE_IDS[role]
    audit(
        db, actor, ModerationActionType.CHANGE_ROLE, ModerationTargetType.USER, str(target.id),
        details={"old_role": old.value, "new_role": role.value, "handle": target.channel.handle},
    )  # fmt: skip
    db.commit()
    db.refresh(target)
    return target


def ban(db: Session, actor: User, user_id: uuid.UUID, reason: str) -> User:
    target = _get_user(db, user_id)
    if target.id == actor.id:
        raise BadRequestError("You cannot ban yourself", code="self_ban")
    if target.role.name == RoleName.ADMIN:
        raise ConflictError("Demote an admin before banning them", code="ban_admin")
    if not target.is_banned:
        target.banned_at = datetime.now(UTC)
        target.ban_reason = reason
        revoke_all_sessions(db, target.id)  # refresh tokens die now; access is checked per request
        audit(
            db, actor, ModerationActionType.BAN_USER, ModerationTargetType.USER, str(target.id),
            reason=reason, details={"handle": target.channel.handle},
        )  # fmt: skip
    db.commit()
    db.refresh(target)
    return target


def unban(db: Session, actor: User, user_id: uuid.UUID, reason: str) -> User:
    target = _get_user(db, user_id)
    if target.is_banned:
        target.banned_at = None
        target.ban_reason = None
        audit(
            db, actor, ModerationActionType.UNBAN_USER, ModerationTargetType.USER, str(target.id),
            reason=reason, details={"handle": target.channel.handle},
        )  # fmt: skip
    db.commit()
    db.refresh(target)
    return target


def list_videos(
    db: Session,
    *,
    q: str | None,
    status: VideoStatus | None,
    hidden: bool | None,
    page: int,
    page_size: int,
) -> tuple[list[Video], int]:
    stmt = select(Video)
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(Video.title.ilike(like))
    if status is not None:
        stmt = stmt.where(Video.status == status)
    if hidden is not None:
        stmt = stmt.where(Video.is_hidden.is_(hidden))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Video.created_at.desc(), Video.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total
