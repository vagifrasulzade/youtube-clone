"""Playlists: ownership, ordering, and no leaking of private videos."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import VideoStatus, Visibility
from tests.factories import auth_headers, create_user, create_video


@pytest.fixture
def owner(db_session: Session):
    return create_user(db_session)


def _video(db: Session, channel, **fields):
    fields.setdefault("visibility", Visibility.PUBLIC)
    return create_video(db, channel, status=VideoStatus.READY, **fields)


def _create(client: TestClient, owner, **body) -> dict:
    body.setdefault("title", "Favourites")
    body.setdefault("visibility", "public")
    response = client.post("/api/v1/playlists", json=body, headers=auth_headers(owner))
    assert response.status_code == 201, response.text
    return response.json()


def _add(client: TestClient, owner, playlist_id: str, video_id: str):
    return client.post(
        f"/api/v1/playlists/{playlist_id}/videos",
        json={"video_id": video_id},
        headers=auth_headers(owner),
    )


def test_create_add_and_list_in_order(client: TestClient, owner, db_session: Session) -> None:
    a, b = (
        _video(db_session, owner.channel, title="A"),
        _video(db_session, owner.channel, title="B"),
    )
    playlist = _create(client, owner)
    _add(client, owner, playlist["id"], a.id)
    _add(client, owner, playlist["id"], b.id)

    body = client.get(f"/api/v1/playlists/{playlist['id']}").json()

    assert [e["video"]["id"] for e in body["entries"]] == [a.id, b.id]
    assert body["is_owner"] is False  # anonymous viewer


def test_adding_twice_conflicts(client: TestClient, owner, db_session: Session) -> None:
    video = _video(db_session, owner.channel)
    playlist = _create(client, owner)
    _add(client, owner, playlist["id"], video.id)

    assert _add(client, owner, playlist["id"], video.id).status_code == 409


def test_reorder_swaps_positions(client: TestClient, owner, db_session: Session) -> None:
    a, b, c = (_video(db_session, owner.channel, title=t) for t in "ABC")
    playlist = _create(client, owner)
    for video in (a, b, c):
        _add(client, owner, playlist["id"], video.id)

    response = client.put(
        f"/api/v1/playlists/{playlist['id']}/videos",
        json={"video_ids": [c.id, a.id, b.id]},
        headers=auth_headers(owner),
    )

    assert response.status_code == 200
    assert [e["video"]["id"] for e in response.json()["entries"]] == [c.id, a.id, b.id]


@pytest.mark.parametrize("bad", ["missing-one", "duplicate", "foreign"])
def test_reorder_requires_an_exact_permutation(
    client: TestClient, owner, db_session: Session, bad: str
) -> None:
    a, b = _video(db_session, owner.channel), _video(db_session, owner.channel)
    playlist = _create(client, owner)
    _add(client, owner, playlist["id"], a.id)
    _add(client, owner, playlist["id"], b.id)
    order = {"missing-one": [a.id], "duplicate": [a.id, a.id], "foreign": [a.id, "zzzzzzzzzzz"]}

    response = client.put(
        f"/api/v1/playlists/{playlist['id']}/videos",
        json={"video_ids": order[bad]},
        headers=auth_headers(owner),
    )

    assert response.status_code == 400


def test_removing_closes_the_gap(client: TestClient, owner, db_session: Session) -> None:
    a, b, c = (_video(db_session, owner.channel) for _ in range(3))
    playlist = _create(client, owner)
    for video in (a, b, c):
        _add(client, owner, playlist["id"], video.id)

    client.delete(f"/api/v1/playlists/{playlist['id']}/videos/{b.id}", headers=auth_headers(owner))
    body = client.get(f"/api/v1/playlists/{playlist['id']}").json()

    assert [(e["position"], e["video"]["id"]) for e in body["entries"]] == [(0, a.id), (1, c.id)]


def test_private_video_in_a_public_playlist_is_a_placeholder(
    client: TestClient, owner, db_session: Session
) -> None:
    """A public playlist must not leak a private video's title (C3)."""
    secret = _video(db_session, owner.channel, title="Secret title", visibility=Visibility.PRIVATE)
    playlist = _create(client, owner)
    _add(client, owner, playlist["id"], secret.id)

    as_stranger = client.get(f"/api/v1/playlists/{playlist['id']}").json()
    as_owner = client.get(f"/api/v1/playlists/{playlist['id']}", headers=auth_headers(owner)).json()

    assert as_stranger["entries"][0] == {"position": 0, "video": None, "title": "Private video"}
    assert "Secret title" not in str(as_stranger)
    assert as_owner["entries"][0]["video"]["id"] == secret.id


def test_private_playlist_is_404_for_others(client: TestClient, owner, db_session: Session) -> None:
    playlist = _create(client, owner, visibility="private")

    assert client.get(f"/api/v1/playlists/{playlist['id']}").status_code == 404
    stranger = auth_headers(create_user(db_session))
    assert client.get(f"/api/v1/playlists/{playlist['id']}", headers=stranger).status_code == 404


def test_only_the_owner_can_modify(client: TestClient, owner, db_session: Session) -> None:
    video = _video(db_session, owner.channel)
    playlist = _create(client, owner)
    stranger = create_user(db_session)
    base = f"/api/v1/playlists/{playlist['id']}"

    assert _add(client, stranger, playlist["id"], video.id).status_code == 403
    assert (
        client.patch(base, json={"title": "x"}, headers=auth_headers(stranger)).status_code == 403
    )
    assert client.delete(base, headers=auth_headers(stranger)).status_code == 403


def test_cannot_add_a_video_you_cannot_watch(
    client: TestClient, owner, db_session: Session
) -> None:
    someone_else = create_user(db_session)
    private = _video(db_session, someone_else.channel, visibility=Visibility.PRIVATE)
    playlist = _create(client, owner)

    assert _add(client, owner, playlist["id"], private.id).status_code == 404


def test_channel_playlists_tab_shows_public_ones_to_visitors(
    client: TestClient, owner, db_session: Session
) -> None:
    public = _create(client, owner, title="Public list")
    _create(client, owner, title="Private list", visibility="private")
    url = f"/api/v1/channels/{owner.channel.handle}/playlists"

    visitor = [p["id"] for p in client.get(url).json()]
    mine = [
        p["title"] for p in client.get("/api/v1/me/playlists", headers=auth_headers(owner)).json()
    ]

    assert visitor == [public["id"]]
    assert sorted(mine) == ["Private list", "Public list"]


def test_third_party_unlisted_video_is_not_listed_through_a_public_playlist(
    client: TestClient, owner, db_session: Session
) -> None:
    """Review L1: unlisted means 'never listed', even inside someone else's playlist."""
    creator = create_user(db_session)
    unlisted = _video(
        db_session, creator.channel, title="Unlisted talk", visibility=Visibility.UNLISTED
    )
    mine = _video(db_session, owner.channel, title="My unlisted", visibility=Visibility.UNLISTED)
    playlist = _create(client, owner)
    _add(client, owner, playlist["id"], unlisted.id)
    _add(client, owner, playlist["id"], mine.id)

    anonymous = client.get(f"/api/v1/playlists/{playlist['id']}").json()["entries"]
    as_creator = client.get(
        f"/api/v1/playlists/{playlist['id']}", headers=auth_headers(creator)
    ).json()["entries"]
    cards = client.get(f"/api/v1/channels/{owner.channel.handle}/playlists").json()

    assert anonymous[0] == {"position": 0, "video": None, "title": "Private video"}
    assert anonymous[1]["video"]["id"] == mine.id  # the playlist owner's own video
    assert "Unlisted talk" not in str(anonymous)
    assert as_creator[0]["video"]["id"] == unlisted.id  # its own creator still sees it
    assert unlisted.id not in str(cards)  # nor used as the public cover


def test_playlist_size_limits(
    client: TestClient, owner, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review L9: bounded playlists keep public playlist pages cheap."""
    from app.services import playlists as service

    monkeypatch.setattr(service, "MAX_ENTRIES_PER_PLAYLIST", 1)
    monkeypatch.setattr(service, "MAX_PLAYLISTS_PER_CHANNEL", 1)
    a, b = _video(db_session, owner.channel), _video(db_session, owner.channel)
    playlist = _create(client, owner)
    _add(client, owner, playlist["id"], a.id)

    full = _add(client, owner, playlist["id"], b.id)
    second = client.post(
        "/api/v1/playlists",
        json={"title": "Another", "visibility": "public"},
        headers=auth_headers(owner),
    )

    assert full.status_code == 409
    assert full.json()["error"]["code"] == "playlist_full"
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "too_many_playlists"
