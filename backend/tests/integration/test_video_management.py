"""Thumbnail selection, custom thumbnails and deletion."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Video
from app.models.enums import RoleName, Visibility
from app.storage import keys, s3
from tests.factories import auth_headers, create_user
from tests.storage_helpers import image_bytes, make_ready_video


def test_owner_can_switch_to_another_generated_thumbnail(
    client: TestClient, db_session: Session, storage_cleanup: list[str]
) -> None:
    owner = create_user(db_session)
    video = make_ready_video(db_session, owner.channel, storage_cleanup)
    s3.put_bytes(
        get_settings().media_bucket,
        keys.video_thumbnail(video.id, "auto_3"),
        image_bytes("JPEG"),
        content_type="image/jpeg",
    )

    response = client.patch(
        f"/api/v1/videos/{video.id}", json={"thumbnail": "auto_3"}, headers=auth_headers(owner)
    )

    assert response.status_code == 200
    db_session.refresh(video)
    assert video.thumbnail_key == keys.video_thumbnail(video.id, "auto_3")


def test_selecting_a_missing_thumbnail_conflicts(
    client: TestClient, db_session: Session, storage_cleanup: list[str]
) -> None:
    owner = create_user(db_session)
    video = make_ready_video(db_session, owner.channel, storage_cleanup)

    response = client.patch(
        f"/api/v1/videos/{video.id}", json={"thumbnail": "custom"}, headers=auth_headers(owner)
    )

    assert response.status_code == 409


def test_custom_thumbnail_is_reencoded_and_selected(
    client: TestClient, db_session: Session, storage_cleanup: list[str]
) -> None:
    owner = create_user(db_session)
    video = make_ready_video(db_session, owner.channel, storage_cleanup)

    response = client.put(
        f"/api/v1/videos/{video.id}/thumbnail",
        files={"file": ("t.png", image_bytes("PNG", (1920, 1080)), "image/png")},
        headers=auth_headers(owner),
    )

    assert response.status_code == 200
    db_session.refresh(video)
    assert video.thumbnail_key == keys.video_thumbnail(video.id, "custom")


def test_only_the_owner_can_upload_a_thumbnail(
    client: TestClient, db_session: Session, storage_cleanup: list[str]
) -> None:
    owner = create_user(db_session)
    video = make_ready_video(db_session, owner.channel, storage_cleanup)

    response = client.put(
        f"/api/v1/videos/{video.id}/thumbnail",
        files={"file": ("t.png", image_bytes("PNG"), "image/png")},
        headers=auth_headers(create_user(db_session)),
    )

    assert response.status_code == 403


def test_owner_deletes_a_video_and_storage_cleanup_is_enqueued(
    client: TestClient,
    db_session: Session,
    storage_cleanup: list[str],
    enqueued: list[tuple[str, str]],
) -> None:
    owner = create_user(db_session)
    video = make_ready_video(db_session, owner.channel, storage_cleanup)
    video_id = video.id

    response = client.delete(f"/api/v1/videos/{video_id}", headers=auth_headers(owner))

    assert response.status_code == 204
    assert ("delete", video_id) in enqueued
    db_session.expire_all()
    assert db_session.get(Video, video_id) is None
    assert client.get(f"/api/v1/videos/{video_id}").status_code == 404


def test_admin_can_delete_any_video(
    client: TestClient, db_session: Session, storage_cleanup: list[str]
) -> None:
    video = make_ready_video(db_session, create_user(db_session).channel, storage_cleanup)
    admin = create_user(db_session, role=RoleName.ADMIN)

    assert (
        client.delete(f"/api/v1/videos/{video.id}", headers=auth_headers(admin)).status_code == 204
    )


def test_moderator_and_strangers_cannot_delete(
    client: TestClient, db_session: Session, storage_cleanup: list[str]
) -> None:
    owner = create_user(db_session)
    public = make_ready_video(db_session, owner.channel, storage_cleanup)
    private = make_ready_video(
        db_session, owner.channel, storage_cleanup, visibility=Visibility.PRIVATE
    )
    moderator = auth_headers(create_user(db_session, role=RoleName.MODERATOR))
    stranger = auth_headers(create_user(db_session))

    assert client.delete(f"/api/v1/videos/{public.id}", headers=moderator).status_code == 403
    assert client.delete(f"/api/v1/videos/{public.id}", headers=stranger).status_code == 403
    assert client.delete(f"/api/v1/videos/{private.id}", headers=stranger).status_code == 404
    assert client.delete(f"/api/v1/videos/{public.id}").status_code == 401
