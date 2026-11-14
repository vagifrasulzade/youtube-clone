"""The visibility policy as a truth table (acceptance C1, C5).

Built on in-memory objects (no database) except for the grant lookup, which is stubbed,
so every combination is checked quickly and exhaustively.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.models.enums import ROLE_LEVELS, RoleName, VideoStatus, Visibility
from app.services import access

OWNER_CHANNEL = uuid.uuid4()


def _user(role: RoleName, *, owns: bool = False) -> SimpleNamespace:
    channel = SimpleNamespace(id=OWNER_CHANNEL if owns else uuid.uuid4())
    return SimpleNamespace(
        id=uuid.uuid4(), channel=channel, role=SimpleNamespace(level=ROLE_LEVELS[role])
    )


def _video(visibility: Visibility, status: VideoStatus, hidden: bool) -> SimpleNamespace:
    return SimpleNamespace(
        id="abcdefghijk",
        channel_id=OWNER_CHANNEL,
        visibility=visibility,
        status=status,
        is_hidden=hidden,
    )


VIEWERS = {
    "anonymous": lambda: None,
    "stranger": lambda: _user(RoleName.USER),
    "granted": lambda: _user(RoleName.USER),
    "owner": lambda: _user(RoleName.USER, owns=True),
    "moderator": lambda: _user(RoleName.MODERATOR),
    "admin": lambda: _user(RoleName.ADMIN),
}

# (visibility, status, hidden) -> set of viewers who may see it
CASES = [
    (Visibility.PUBLIC, VideoStatus.READY, False, set(VIEWERS)),
    (Visibility.UNLISTED, VideoStatus.READY, False, set(VIEWERS)),
    (Visibility.PRIVATE, VideoStatus.READY, False, {"granted", "owner", "moderator", "admin"}),
    (Visibility.PUBLIC, VideoStatus.READY, True, {"owner", "moderator", "admin"}),
    (Visibility.PRIVATE, VideoStatus.READY, True, {"owner", "moderator", "admin"}),
    (Visibility.PUBLIC, VideoStatus.PROCESSING, False, {"owner", "moderator", "admin"}),
    (Visibility.PUBLIC, VideoStatus.FAILED, False, {"owner", "moderator", "admin"}),
    (Visibility.PUBLIC, VideoStatus.AWAITING_UPLOAD, False, {"owner", "moderator", "admin"}),
]


@pytest.mark.parametrize(("visibility", "status", "hidden", "allowed"), CASES)
@pytest.mark.parametrize("viewer_kind", list(VIEWERS))
def test_can_view_matrix(
    monkeypatch: pytest.MonkeyPatch,
    visibility: Visibility,
    status: VideoStatus,
    hidden: bool,
    allowed: set[str],
    viewer_kind: str,
) -> None:
    viewer = VIEWERS[viewer_kind]()
    monkeypatch.setattr(access, "has_grant", lambda _db, _vid, _uid: viewer_kind == "granted")

    result = access.can_view(None, _video(visibility, status, hidden), viewer)  # type: ignore[arg-type]

    assert result is (viewer_kind in allowed)
