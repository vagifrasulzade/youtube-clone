"""Password hashing and token primitives."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.errors import UnauthorizedError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    verify_password,
)


def test_password_hash_is_argon2id_and_verifies() -> None:
    hashed = hash_password("s3cret-password")

    assert hashed.startswith("$argon2id$")
    assert "s3cret-password" not in hashed
    assert verify_password(hashed, "s3cret-password")
    assert not verify_password(hashed, "wrong-password")


def test_same_password_hashes_differently() -> None:
    assert hash_password("same-password") != hash_password("same-password")  # random salt


def test_verify_password_tolerates_garbage_hash() -> None:
    assert verify_password("not-a-hash", "anything") is False


def test_access_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    token, ttl = create_access_token(user_id)

    assert ttl == get_settings().access_token_ttl_seconds
    assert decode_access_token(token) == user_id


def _token(secret: str | None = None, **claims: object) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": str(uuid.uuid4()),
        "typ": "access",
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        **claims,
    }
    key = secret or settings.jwt_secret.get_secret_value()
    return jwt.encode(payload, key, algorithm="HS256")


@pytest.mark.parametrize(
    ("token", "code"),
    [
        (lambda: "not.a.jwt", "invalid_token"),
        (lambda: _token(exp=int(datetime.now(UTC).timestamp()) - 10), "token_expired"),
        (lambda: _token(secret="another-secret-another-secret-123"), "invalid_token"),
        (lambda: _token(typ="media"), "invalid_token"),
        (lambda: _token(iss="someone-else"), "invalid_token"),
        (lambda: _token(sub="not-a-uuid"), "invalid_token"),
        (
            lambda: jwt.encode({"sub": str(uuid.uuid4()), "typ": "access"}, None, algorithm="none"),
            "invalid_token",
        ),
    ],
    ids=["garbage", "expired", "wrong-secret", "wrong-type", "wrong-issuer", "bad-sub", "alg-none"],
)
def test_invalid_access_tokens_are_rejected(token, code: str) -> None:
    with pytest.raises(UnauthorizedError) as exc_info:
        decode_access_token(token())
    assert exc_info.value.code == code


def test_refresh_tokens_are_random_and_hashed() -> None:
    a, b = new_refresh_token(), new_refresh_token()

    assert a != b
    assert len(a) >= 43  # 256 bits, URL-safe base64
    assert hash_token(a) != a
    assert len(hash_token(a)) == 64
