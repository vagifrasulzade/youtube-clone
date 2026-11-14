"""Registration, login, sessions and lockout (acceptance criteria E1-E3, E5)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.redis import get_redis
from app.core.security import hash_token
from app.main import app
from app.models import RefreshToken, User
from tests.factories import DEFAULT_PASSWORD, register, register_payload

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"
CHANGE_PASSWORD = "/api/v1/auth/change-password"
COOKIE = "yt_refresh"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def refresh_with(client: TestClient, cookie_value: str, **headers: str):
    """Send exactly this refresh cookie (ignoring the client's cookie jar)."""
    client.cookies.clear()
    return client.post(REFRESH, headers={"Cookie": f"{COOKIE}={cookie_value}", **headers})


# --- registration -------------------------------------------------------------


def test_register_creates_user_and_channel_and_signs_in(
    client: TestClient, db_session: Session
) -> None:
    body = register(client, email="Alice@Example.com", handle="Alice_1", display_name="Alice")

    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["role"] == "user"
    assert body["user"]["channel"]["handle"] == "alice_1"
    assert body["user"]["channel"]["name"] == "Alice"
    me = client.get(ME, headers=bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["id"] == body["user"]["id"]


def test_password_is_stored_only_as_argon2id_hash(client: TestClient, db_session: Session) -> None:
    """E1"""
    body = register(client)
    user = db_session.get(User, uuid.UUID(body["user"]["id"]))

    assert user is not None
    assert user.password_hash.startswith("$argon2id$")
    assert DEFAULT_PASSWORD not in user.password_hash


def test_register_sets_httponly_strict_refresh_cookie(client: TestClient) -> None:
    response = client.post(REGISTER, json=register_payload())

    cookie = response.headers["set-cookie"].lower()
    assert f"{COOKIE}=" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/api/v1/auth" in cookie
    assert COOKIE not in response.text  # never in the JSON body


def test_register_rejects_duplicate_email_case_insensitively(client: TestClient) -> None:
    register(client, email="bob@example.com")

    response = client.post(REGISTER, json=register_payload(email="BOB@example.com"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


def test_register_rejects_duplicate_handle(client: TestClient) -> None:
    register(client, handle="taken_handle")

    response = client.post(REGISTER, json=register_payload(handle="Taken_Handle"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "handle_taken"


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "short"},
        {"password": "x" * 129},
        {"handle": "ab"},
        {"handle": "has space"},
        {"email": "not-an-email"},
        {"display_name": ""},
        {"display_name": "bad\x00name"},
        {"handle": "samepassword", "password": "samepassword"},
    ],
    ids=[
        "short-password",
        "long-password",
        "short-handle",
        "handle-space",
        "bad-email",
        "empty-name",
        "control-char-name",
        "password-equals-handle",
    ],
)
def test_register_validates_input(client: TestClient, overrides: dict[str, str]) -> None:
    response = client.post(REGISTER, json=register_payload(**overrides))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_register_ignores_role_field(client: TestClient) -> None:
    """No mass assignment: a client cannot register itself as admin."""
    response = client.post(REGISTER, json={**register_payload(), "role": "admin"})

    assert response.status_code == 201
    assert response.json()["user"]["role"] == "user"


# --- login --------------------------------------------------------------------


def test_login_succeeds_and_records_last_login(client: TestClient, db_session: Session) -> None:
    body = register(client, email="carol@example.com")

    response = client.post(LOGIN, json={"email": "Carol@Example.com", "password": DEFAULT_PASSWORD})

    assert response.status_code == 200
    assert response.json()["user"]["id"] == body["user"]["id"]
    user = db_session.get(User, uuid.UUID(body["user"]["id"]))
    assert user is not None
    db_session.refresh(user)
    assert user.last_login_at is not None


def test_wrong_password_and_unknown_email_are_indistinguishable(client: TestClient) -> None:
    """E1: no account enumeration through login."""
    register(client, email="dave@example.com")

    wrong_password = client.post(LOGIN, json={"email": "dave@example.com", "password": "nope-nope"})
    unknown_email = client.post(LOGIN, json={"email": "nobody@example.com", "password": "nope"})

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["error"]["code"] == "invalid_credentials"


# --- access token -------------------------------------------------------------


def test_me_requires_a_token(client: TestClient) -> None:
    response = client.get(ME)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_rejects_an_invalid_token(client: TestClient) -> None:
    response = client.get(ME, headers=bearer("garbage"))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


def test_token_of_deleted_user_is_rejected(client: TestClient, db_session: Session) -> None:
    body = register(client)
    db_session.delete(db_session.get(User, uuid.UUID(body["user"]["id"])))
    db_session.flush()

    response = client.get(ME, headers=bearer(body["access_token"]))

    assert response.status_code == 401


# --- refresh rotation -----------------------------------------------------------


def test_refresh_rotates_the_cookie_and_returns_a_new_access_token(client: TestClient) -> None:
    register(client)
    first_cookie = client.cookies[COOKIE]

    response = client.post(REFRESH)

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert client.cookies[COOKIE] != first_cookie


def test_reusing_a_rotated_refresh_token_revokes_the_whole_family(
    client: TestClient, db_session: Session
) -> None:
    """E2: a replayed (stolen) refresh token ends every session of that login."""
    register(client)
    stolen = client.cookies[COOKIE]
    assert client.post(REFRESH).status_code == 200
    current = client.cookies[COOKIE]
    # Move the rotation outside the grace window.
    db_session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(stolen))
        .values(revoked_at=datetime.now(UTC) - timedelta(minutes=5))
    )

    replay = refresh_with(client, stolen)
    legit = refresh_with(client, current)

    assert replay.status_code == 401
    assert legit.status_code == 401  # the legitimate session was revoked too


def test_concurrent_refresh_within_grace_window_does_not_revoke(client: TestClient) -> None:
    register(client)
    old = client.cookies[COOKIE]
    assert client.post(REFRESH).status_code == 200
    current = client.cookies[COOKIE]

    race = refresh_with(client, old)
    after = refresh_with(client, current)

    assert race.status_code == 401
    assert race.json()["error"]["code"] == "refresh_superseded"
    assert after.status_code == 200


def test_refresh_without_cookie_is_rejected(client: TestClient) -> None:
    response = client.post(REFRESH)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh"


def test_refresh_with_expired_token_is_rejected(client: TestClient, db_session: Session) -> None:
    register(client)
    cookie = client.cookies[COOKIE]
    db_session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(cookie))
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )

    assert refresh_with(client, cookie).status_code == 401


def test_refresh_from_a_foreign_origin_is_rejected(client: TestClient) -> None:
    register(client)

    response = client.post(REFRESH, headers={"Origin": "https://evil.example"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "bad_origin"


def test_refresh_tokens_are_stored_hashed(client: TestClient, db_session: Session) -> None:
    register(client)
    raw = client.cookies[COOKIE]

    stored = db_session.scalars(select(RefreshToken.token_hash)).all()

    assert raw not in stored
    assert hash_token(raw) in stored


# --- logout -------------------------------------------------------------------


def test_logout_revokes_the_session_and_clears_the_cookie(client: TestClient) -> None:
    register(client)
    cookie = client.cookies[COOKIE]

    response = client.post(LOGOUT)

    assert response.status_code == 204
    assert f'{COOKIE}=""' in response.headers["set-cookie"] or "max-age=0" in (
        response.headers["set-cookie"].lower()
    )
    assert refresh_with(client, cookie).status_code == 401


# --- bans -----------------------------------------------------------------------


def test_banned_user_is_locked_out_immediately(client: TestClient, db_session: Session) -> None:
    """E3: a ban applies on the next request, not when the access token expires."""
    body = register(client, email="eve@example.com")
    cookie = client.cookies[COOKIE]
    db_session.execute(
        update(User)
        .where(User.id == uuid.UUID(body["user"]["id"]))
        .values(banned_at=datetime.now(UTC))
    )

    me = client.get(ME, headers=bearer(body["access_token"]))
    login = client.post(LOGIN, json={"email": "eve@example.com", "password": DEFAULT_PASSWORD})
    refresh = refresh_with(client, cookie)

    assert me.status_code == 403
    assert me.json()["error"]["code"] == "account_banned"
    assert login.status_code == 403
    assert refresh.status_code == 403


# --- change password ------------------------------------------------------------


def test_change_password_signs_out_other_sessions(client: TestClient) -> None:
    body = register(client, email="frank@example.com")
    first_session = client.cookies[COOKIE]
    client.cookies.clear()
    client.post(LOGIN, json={"email": "frank@example.com", "password": DEFAULT_PASSWORD})
    second_session = client.cookies[COOKIE]

    response = client.post(
        CHANGE_PASSWORD,
        headers=bearer(body["access_token"]),
        json={"current_password": DEFAULT_PASSWORD, "new_password": "brand-new-password"},
    )

    assert response.status_code == 200
    new_session = client.cookies[COOKIE]
    assert refresh_with(client, first_session).status_code == 401
    assert refresh_with(client, second_session).status_code == 401
    assert refresh_with(client, new_session).status_code == 200
    old = client.post(LOGIN, json={"email": "frank@example.com", "password": DEFAULT_PASSWORD})
    new = client.post(LOGIN, json={"email": "frank@example.com", "password": "brand-new-password"})
    assert old.status_code == 401
    assert new.status_code == 200


def test_change_password_requires_the_current_password(client: TestClient) -> None:
    body = register(client)

    response = client.post(
        CHANGE_PASSWORD,
        headers=bearer(body["access_token"]),
        json={"current_password": "not-my-password", "new_password": "brand-new-password"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "wrong_password"


# --- rate limits ------------------------------------------------------------------


def test_login_is_rate_limited_per_account(client: TestClient) -> None:
    """E5"""
    register(client, email="grace@example.com")
    attempt = {"email": "grace@example.com", "password": "wrong-password"}

    statuses = [client.post(LOGIN, json=attempt).status_code for _ in range(5)]
    blocked = client.post(LOGIN, json=attempt)

    assert statuses == [401] * 5
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1


def test_register_is_rate_limited_per_ip(client: TestClient) -> None:
    statuses = [client.post(REGISTER, json=register_payload()).status_code for _ in range(6)]

    assert statuses == [201] * 5 + [429]


def test_auth_fails_closed_when_rate_limiter_is_down(client: TestClient) -> None:
    unreachable = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2, socket_timeout=0.2)
    app.dependency_overrides[get_redis] = lambda: unreachable

    response = client.post(LOGIN, json={"email": "x@example.com", "password": "whatever"})

    assert response.status_code == 503


# --- security review regressions --------------------------------------------------


def test_change_password_applies_the_registration_policy(client: TestClient) -> None:
    """Review L1: the new password may not equal the email or handle."""
    body = register(client, email="henry@example.com", handle="henry_h")

    response = client.post(
        CHANGE_PASSWORD,
        headers=bearer(body["access_token"]),
        json={"current_password": DEFAULT_PASSWORD, "new_password": "henry@example.com"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "weak_password"


def test_change_password_is_rate_limited_per_account(client: TestClient) -> None:
    """Review L2"""
    body = register(client)
    attempt = {"current_password": "wrong-guess", "new_password": "brand-new-password"}

    statuses = [
        client.post(CHANGE_PASSWORD, headers=bearer(body["access_token"]), json=attempt).status_code
        for _ in range(6)
    ]

    assert statuses == [400] * 5 + [429]


def test_cross_site_refresh_attempts_do_not_consume_the_rate_limit(client: TestClient) -> None:
    """Review L3: rejected cross-origin requests must not lock the victim out."""
    register(client)
    for _ in range(35):
        assert client.post(REFRESH, headers={"Origin": "https://evil.example"}).status_code == 403

    assert client.post(REFRESH).status_code == 200


def test_a_login_cannot_be_refreshed_forever(client: TestClient, db_session: Session) -> None:
    """Absolute session lifetime, however often the token is rotated."""
    register(client)
    cookie = client.cookies[COOKIE]
    db_session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(cookie))
        .values(created_at=datetime.now(UTC) - timedelta(days=91))
    )

    assert refresh_with(client, cookie).status_code == 401
