"""Operator CLI: `python -m app.cli.reset_password <email>`."""

from __future__ import annotations

from contextlib import nullcontext

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import reset_password
from app.core.security import verify_password
from app.models import RefreshToken, User
from app.services import auth
from tests.factories import create_user

OLD = "old-password-123"
NEW = "brand-new-password-456"


@pytest.fixture
def target(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> User:
    monkeypatch.setattr(reset_password, "get_sessionmaker", lambda: lambda: nullcontext(db_session))
    return create_user(db_session, email="forgot@example.com", handle="forgetful", password=OLD)


def _run(email: str, password: str | None) -> int:
    return reset_password.main([email], reader=lambda: password)


def test_sets_the_new_password_and_signs_out_every_session(
    db_session: Session, target: User
) -> None:
    for agent in ("laptop", "phone"):
        auth.issue_session(db_session, target, user_agent=agent)
    db_session.flush()

    assert _run("Forgot@Example.com", NEW) == 0

    db_session.refresh(target)
    assert verify_password(target.password_hash, NEW)
    assert not verify_password(target.password_hash, OLD)
    tokens = db_session.scalars(select(RefreshToken).where(RefreshToken.user_id == target.id))
    assert all(token.revoked_at is not None for token in tokens)


@pytest.mark.parametrize(
    "password",
    [
        None,  # cancelled or the two entries did not match
        "short",  # under 8 characters
        "x" * 129,
        "forgetful",  # the handle
        "FORGOT",  # the email's local part, any case
    ],
)
def test_rejected_passwords_change_nothing(
    db_session: Session, target: User, password: str | None
) -> None:
    assert _run("forgot@example.com", password) == 1

    db_session.refresh(target)
    assert verify_password(target.password_hash, OLD)


def test_unknown_account_and_bad_usage(target: User) -> None:
    assert _run("nobody@example.com", NEW) == 1
    assert reset_password.main([]) == 2
    assert reset_password.main(["a@example.com", NEW]) == 2  # never from the command line


def test_piped_stdin_is_read_as_one_line(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(f"{NEW}\r\nignored\n"))

    assert reset_password.read_password() == NEW
