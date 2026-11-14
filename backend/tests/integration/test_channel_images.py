"""Avatar/banner uploads are validated and re-encoded before reaching storage."""

from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Channel
from tests.factories import auth_headers, create_user
from tests.storage_helpers import image_bytes, object_bytes

AVATAR = "/api/v1/channels/me/avatar"
BANNER = "/api/v1/channels/me/banner"


@pytest.fixture
def owner(db_session: Session, storage_cleanup: list[str]):
    user = create_user(db_session)
    storage_cleanup.append(str(user.channel.id))
    return user


def _put(client: TestClient, path: str, owner, data: bytes, name: str, ctype: str):
    return client.put(path, headers=auth_headers(owner), files={"file": (name, data, ctype)})


def test_avatar_is_reencoded_to_a_square_jpeg(
    client: TestClient, owner, db_session: Session
) -> None:
    response = _put(client, AVATAR, owner, image_bytes("PNG", (1000, 500)), "me.png", "image/png")

    assert response.status_code == 200
    assert response.json()["avatar_url"].startswith(f"/api/v1/media/channels/{owner.channel.id}/")
    channel = db_session.get(Channel, owner.channel.id)
    assert channel is not None
    db_session.refresh(channel)
    stored = object_bytes(get_settings().media_bucket, channel.avatar_key)
    assert stored[:2] == b"\xff\xd8"  # JPEG, whatever the user sent
    with Image.open(BytesIO(stored)) as image:
        assert image.size == (800, 800)
        assert not image.getexif()  # metadata stripped


def test_banner_is_cropped_to_16_9(client: TestClient, owner, db_session: Session) -> None:
    response = _put(client, BANNER, owner, image_bytes("JPEG", (3000, 3000)), "b.jpg", "image/jpeg")

    assert response.status_code == 200
    channel = db_session.get(Channel, owner.channel.id)
    assert channel is not None
    db_session.refresh(channel)
    with Image.open(BytesIO(object_bytes(get_settings().media_bucket, channel.banner_key))) as im:
        assert im.size == (2560, 1440)


@pytest.mark.parametrize(
    ("data", "name", "ctype"),
    [
        (b"definitely not an image", "fake.png", "image/png"),
        (b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>', "x.svg", "image/svg+xml"),
        (b"GIF89a" + b"\x00" * 64, "anim.gif", "image/gif"),
        (b"", "empty.png", "image/png"),
    ],
    ids=["garbage", "svg", "gif", "empty"],
)
def test_non_images_and_unsupported_formats_are_rejected(
    client: TestClient, owner, data: bytes, name: str, ctype: str
) -> None:
    response = _put(client, AVATAR, owner, data, name, ctype)

    assert response.status_code == 415


def test_oversized_image_is_rejected(
    client: TestClient, owner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "max_avatar_bytes", 1024)

    response = _put(client, AVATAR, owner, image_bytes("PNG", (800, 800)), "big.png", "image/png")

    assert response.status_code == 413


def test_channel_image_upload_requires_authentication(client: TestClient) -> None:
    response = client.put(AVATAR, files={"file": ("a.png", image_bytes(), "image/png")})

    assert response.status_code == 401
