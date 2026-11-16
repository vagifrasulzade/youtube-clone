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


def test_fifteen_unique_accounts_and_every_creator_has_videos() -> None:
    emails = [email for email, *_ in seed.USERS]
    handles = [handle for _, handle, _, _ in seed.USERS]
    assert len(seed.USERS) == 15
    assert len(set(emails)) == len(emails)
    assert len(set(handles)) == len(handles)
    creators = set(handles) - seed.NON_CREATORS
    assert creators <= {video.handle for video in seed.VIDEOS}


def test_demo_videos_fit_the_schema_limits() -> None:
    handles = {handle for _, handle, _, _ in seed.USERS}
    titles = [video.title for video in seed.VIDEOS]
    assert len(set(titles)) == len(titles)  # re-runs find videos by (channel, title)
    for video in seed.VIDEOS:
        assert video.handle in handles
        assert 1 <= len(video.title) <= 100
        assert len(video.description) <= 5000
        assert video.shared_with is None or video.shared_with in handles


def test_no_two_demo_videos_look_the_same() -> None:
    """Each clip has its own style + palette pair, title and channel drawn on it."""
    looks = [
        (index % len(seed.STYLES), index % len(seed.PALETTES)) for index in range(len(seed.VIDEOS))
    ]
    assert len(set(looks)) == len(looks)
    backgrounds = [seed.background(i) for i in range(len(seed.VIDEOS))]
    assert len(set(backgrounds)) == len(backgrounds)
    assert len({seed.clip_seconds(i) for i in range(len(seed.VIDEOS))}) > 5  # varied lengths


def test_moderation_examples_and_playlists_reference_real_videos() -> None:
    titles = {video.title for video in seed.VIDEOS}
    assert any(video.hidden for video in seed.VIDEOS)
    assert any(video.reported for video in seed.VIDEOS)
    assert any(video.shared_with for video in seed.VIDEOS)
    for _handle, _title, _visibility, playlist_titles in seed.PLAYLISTS:
        assert set(playlist_titles) <= titles


def test_overlay_quotes_text_files_and_refuses_odd_paths(tmp_path) -> None:
    graph = seed.overlay(tmp_path / "t.txt", tmp_path / "c.txt")
    assert f"textfile='{tmp_path / 't.txt'}'" in graph
    with pytest.raises(ValueError, match="quote"):
        seed.overlay(tmp_path / "it's.txt", tmp_path / "c.txt")


def test_unknown_arguments_are_rejected() -> None:
    assert seed.main(["--reset"]) == 2


def test_seed_refuses_to_use_a_known_password_in_production(monkeypatch) -> None:
    """Review H1: a public demo password on a deployed admin account is a takeover."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "demo_password", None)

    assert seed.demo_password() is None
    assert seed.main([]) == 1
