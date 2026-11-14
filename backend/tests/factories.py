"""Factory helpers: insert rows directly (DB tests) or go through the API (auth tests)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models import Channel, User, Video
from app.models.enums import ROLE_IDS, RoleName

DEFAULT_PASSWORD = "correct-horse-battery"


def unique_suffix() -> str:
    return uuid.uuid4().hex[:10]


def create_user(
    db: Session,
    *,
    email: str | None = None,
    handle: str | None = None,
    role: RoleName = RoleName.USER,
    password: str | None = None,
) -> User:
    suffix = unique_suffix()
    user = User(
        email=email or f"user_{suffix}@example.com",
        password_hash=hash_password(password) if password else "not-a-real-hash",
        role_id=ROLE_IDS[role],
    )
    user.channel = Channel(handle=handle or f"user_{suffix}", name=f"User {suffix}")
    db.add(user)
    db.flush()
    db.refresh(user)
    return user


def create_video(db: Session, channel: Channel, **fields: Any) -> Video:
    fields.setdefault("title", "Test video")
    video = Video(channel_id=channel.id, **fields)
    db.add(video)
    db.flush()
    return video


def auth_headers(user: User) -> dict[str, str]:
    """Bearer header for a user created with `create_user` (skips the login endpoint)."""
    token, _ = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def register_payload(**overrides: str) -> dict[str, str]:
    suffix = unique_suffix()
    payload = {
        "email": f"viewer_{suffix}@example.com",
        "password": DEFAULT_PASSWORD,
        "handle": f"viewer_{suffix}",
        "display_name": "Test Viewer",
    }
    payload.update(overrides)
    return payload


def register(client: TestClient, **overrides: str) -> dict[str, Any]:
    response = client.post("/api/v1/auth/register", json=register_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()
