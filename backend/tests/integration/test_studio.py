"""Creator Studio list and channel profile editing."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import VideoStatus, Visibility
from tests.factories import auth_headers, create_user, create_video


def test_studio_lists_all_my_videos_in_every_state(client: TestClient, db_session: Session) -> None:
    me = create_user(db_session)
    states = [VideoStatus.AWAITING_UPLOAD, VideoStatus.PROCESSING, VideoStatus.FAILED]
    mine = {create_video(db_session, me.channel, status=s).id for s in states}
    mine.add(create_video(db_session, me.channel, status=VideoStatus.READY, is_hidden=True).id)
    create_video(db_session, create_user(db_session).channel, status=VideoStatus.READY)

    body = client.get("/api/v1/studio/videos", headers=auth_headers(me)).json()

    assert {v["id"] for v in body["items"]} == mine
    assert body["total"] == 4


def test_studio_filters_and_paginates(client: TestClient, db_session: Session) -> None:
    me = create_user(db_session)
    for i in range(5):
        create_video(db_session, me.channel, title=f"Trip {i}", visibility=Visibility.PUBLIC)
    create_video(db_session, me.channel, title="Cooking", visibility=Visibility.PRIVATE)
    headers = auth_headers(me)

    public = client.get("/api/v1/studio/videos?visibility=public&page_size=2", headers=headers)
    search = client.get("/api/v1/studio/videos?q=cook", headers=headers)
    literal = client.get("/api/v1/studio/videos?q=%25", headers=headers)  # '%' is not a wildcard

    assert public.json()["total"] == 5
    assert len(public.json()["items"]) == 2
    assert [v["title"] for v in search.json()["items"]] == ["Cooking"]
    assert literal.json()["total"] == 0


def test_studio_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/studio/videos").status_code == 401


def test_edit_my_channel(client: TestClient, db_session: Session) -> None:
    me = create_user(db_session)

    response = client.patch(
        "/api/v1/channels/me",
        json={"name": "  Cooking With Me ", "description": "Recipes\nfrom Baku"},
        headers=auth_headers(me),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Cooking With Me"
    assert response.json()["description"] == "Recipes\nfrom Baku"


def test_channel_edit_rejects_protected_fields(client: TestClient, db_session: Session) -> None:
    me = create_user(db_session)

    for payload in ({"handle": "stolen"}, {"subscriber_count": 1_000_000}, {"name": ""}):
        response = client.patch("/api/v1/channels/me", json=payload, headers=auth_headers(me))
        assert response.status_code == 422, payload
