"""Search by title (full-text + trigram), never returning non-listable videos."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Video
from app.models.enums import VideoStatus, Visibility
from tests.factories import create_user, create_video


@pytest.fixture(autouse=True)
def isolated(db_session: Session) -> None:
    db_session.execute(update(Video).values(is_hidden=True))  # ignore any pre-existing rows


def _video(db: Session, title: str, *, days_ago: int = 0, **fields) -> Video:
    fields.setdefault("visibility", Visibility.PUBLIC)
    fields.setdefault("status", VideoStatus.READY)
    return create_video(
        db,
        create_user(db).channel,
        title=title,
        published_at=datetime.now(UTC) - timedelta(days=days_ago),
        **fields,
    )


def _ids(response) -> list[str]:
    return [item["id"] for item in response.json()["items"]]


def test_finds_videos_by_title_words(client: TestClient, db_session: Session) -> None:
    plov = _video(db_session, "Azerbaijani plov recipe")
    _video(db_session, "Guitar lesson for beginners")

    response = client.get("/api/v1/search", params={"q": "plov"})

    assert response.status_code == 200
    assert _ids(response) == [plov.id]
    assert response.json()["total"] == 1


def test_tolerates_typos_via_trigrams(client: TestClient, db_session: Session) -> None:
    plov = _video(db_session, "Plov recipe")

    assert _ids(client.get("/api/v1/search", params={"q": "plof recipe"})) == [plov.id]


def test_matches_any_language(client: TestClient, db_session: Session) -> None:
    az = _video(db_session, "Bakı küçələri gecə")  # noqa: RUF001 - real Azerbaijani text
    ru = _video(db_session, "Рецепт плова")

    assert _ids(client.get("/api/v1/search", params={"q": "küçələri"})) == [az.id]
    assert _ids(client.get("/api/v1/search", params={"q": "плова"})) == [ru.id]


def test_never_returns_non_listable_videos(client: TestClient, db_session: Session) -> None:
    """C3"""
    _video(db_session, "Secret plov", visibility=Visibility.PRIVATE)
    _video(db_session, "Unlisted plov", visibility=Visibility.UNLISTED)
    _video(db_session, "Hidden plov", is_hidden=True)
    _video(db_session, "Processing plov", status=VideoStatus.PROCESSING)
    public = _video(db_session, "Public plov")

    assert _ids(client.get("/api/v1/search", params={"q": "plov"})) == [public.id]
    suggestions = client.get("/api/v1/search/suggestions", params={"q": "plov"}).json()
    assert "Secret plov" not in suggestions
    assert "Unlisted plov" not in suggestions


def test_sort_by_date_and_views(client: TestClient, db_session: Session) -> None:
    old = _video(db_session, "Cooking show old", days_ago=10, view_count=1000)
    new = _video(db_session, "Cooking show new", days_ago=1, view_count=5)

    by_date = client.get("/api/v1/search", params={"q": "cooking", "sort": "date"})
    by_views = client.get("/api/v1/search", params={"q": "cooking", "sort": "views"})

    assert _ids(by_date) == [new.id, old.id]
    assert _ids(by_views) == [old.id, new.id]


def test_pagination(client: TestClient, db_session: Session) -> None:
    for i in range(5):
        _video(db_session, f"Travel vlog {i}", days_ago=i)

    page1 = client.get("/api/v1/search", params={"q": "travel", "page_size": 2, "sort": "date"})
    page3 = client.get(
        "/api/v1/search", params={"q": "travel", "page_size": 2, "page": 3, "sort": "date"}
    )

    assert page1.json()["total"] == 5
    assert len(page1.json()["items"]) == 2
    assert len(page3.json()["items"]) == 1


def test_suggestions_prefer_prefix_matches(client: TestClient, db_session: Session) -> None:
    _video(db_session, "Football highlights")
    _video(db_session, "Best football goals")

    suggestions = client.get("/api/v1/search/suggestions", params={"q": "foot"}).json()

    assert suggestions[0] == "Football highlights"


@pytest.mark.parametrize("q", ["", " ", "x" * 101])
def test_query_is_validated(client: TestClient, q: str) -> None:
    assert client.get("/api/v1/search", params={"q": q}).status_code == 422


def test_query_operators_are_safe(client: TestClient, db_session: Session) -> None:
    """websearch_to_tsquery never raises on user syntax; LIKE wildcards are escaped."""
    _video(db_session, "Normal title")

    for q in ['"unclosed', "a & | ! ( )", "100%", "under_score", "'; DROP TABLE videos; --"]:
        assert client.get("/api/v1/search", params={"q": q}).status_code == 200
        assert client.get("/api/v1/search/suggestions", params={"q": q}).status_code == 200


def test_search_is_rate_limited(client: TestClient) -> None:
    statuses = [client.get("/api/v1/search", params={"q": "x"}).status_code for _ in range(61)]

    assert statuses[-1] == 429
