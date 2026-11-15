"""The demo data must be usable through the real API (found during the deploy check)."""

import pytest

from app.cli import seed
from app.schemas.auth import LoginRequest, RegisterRequest


@pytest.mark.parametrize(("email", "handle", "name", "_role"), seed.USERS)
def test_demo_accounts_pass_api_validation(email: str, handle: str, name: str, _role) -> None:
    """`.local` and similar reserved domains are rejected by email validation, which
    would make the seeded accounts impossible to log in with."""
    LoginRequest(email=email, password=seed.DEV_DEMO_PASSWORD)
    RegisterRequest(email=email, password=seed.DEV_DEMO_PASSWORD, handle=handle, display_name=name)


def test_demo_videos_fit_the_schema_limits() -> None:
    handles = {handle for _, handle, _, _ in seed.USERS}
    for handle, title, description, _source, _visibility in seed.VIDEOS:
        assert handle in handles
        assert 1 <= len(title) <= 100
        assert len(description) <= 5000


def test_seed_refuses_to_use_a_known_password_in_production(monkeypatch) -> None:
    """Review H1: a public demo password on a deployed admin account is a takeover."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "demo_password", None)

    assert seed.demo_password() is None
    assert seed.main() == 1
