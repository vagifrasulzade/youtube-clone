"""Retry policy of the process_video Celery task (no broker, DB or ffmpeg needed)."""

from __future__ import annotations

from contextlib import nullcontext

import pytest

from app.workers import processing, tasks


@pytest.fixture
def no_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: lambda: nullcontext(None))


@pytest.mark.usefixtures("no_db")
def test_storage_outages_are_retried_then_the_video_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[str] = []
    gave_up: list[str] = []

    def outage(_db: object, video_id: str) -> processing.Outcome:
        attempts.append(video_id)
        raise processing.TransientError(video_id)

    monkeypatch.setattr(processing, "process_video", outage)
    monkeypatch.setattr(processing, "give_up", lambda _db, video_id: gave_up.append(video_id))

    result = tasks.process_video.apply(args=["abcdefghijk"])

    assert result.get() == processing.Outcome.FAILED
    assert len(attempts) == 1 + tasks.PROCESS_MAX_RETRIES
    assert gave_up == ["abcdefghijk"]


@pytest.mark.usefixtures("no_db")
def test_a_recovered_outage_publishes_without_giving_up(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes = iter([processing.TransientError("x"), processing.Outcome.READY])
    gave_up: list[str] = []

    def flaky(_db: object, _video_id: str) -> processing.Outcome:
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(processing, "process_video", flaky)
    monkeypatch.setattr(processing, "give_up", lambda _db, video_id: gave_up.append(video_id))

    assert tasks.process_video.apply(args=["abcdefghijk"]).get() == processing.Outcome.READY
    assert gave_up == []
