"""Every error response uses {"error": {code, message, details}} and leaks nothing."""

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.errors import (
    NotFoundError,
    RateLimitedError,
    UnauthorizedError,
    register_exception_handlers,
)
from app.core.logging import RequestContextMiddleware


class _Credentials(BaseModel):
    email: str
    password: str = Field(min_length=8)


def _make_app() -> FastAPI:
    test_app = FastAPI()
    register_exception_handlers(test_app)
    test_app.add_middleware(RequestContextMiddleware)

    @test_app.get("/missing")
    def missing() -> None:
        raise NotFoundError("Video not found", code="video_not_found")

    @test_app.get("/limited")
    def limited() -> None:
        raise RateLimitedError(retry_after=30)

    @test_app.get("/private")
    def private() -> None:
        raise UnauthorizedError()

    @test_app.post("/login")
    def login(body: _Credentials) -> dict[str, str]:
        return {"email": body.email}

    @test_app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    return test_app


@pytest.fixture
def raw_client() -> TestClient:
    return TestClient(_make_app(), raise_server_exceptions=False)


def test_app_error_is_rendered_as_envelope(raw_client: TestClient) -> None:
    response = raw_client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "video_not_found", "message": "Video not found", "details": None}
    }


def test_rate_limited_error_sets_retry_after(raw_client: TestClient) -> None:
    response = raw_client.get("/limited")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.json()["error"]["code"] == "rate_limited"


def test_unauthorized_error_sets_www_authenticate(raw_client: TestClient) -> None:
    response = raw_client.get("/private")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_validation_error_lists_fields_without_echoing_input(raw_client: TestClient) -> None:
    response = raw_client.post("/login", json={"email": "a@example.com", "password": "short1"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"][0]["loc"] == ["body", "password"]
    assert "short1" not in response.text


def test_unhandled_exception_returns_generic_500(raw_client: TestClient) -> None:
    response = raw_client.get("/boom")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret internal detail" not in response.text


def test_unknown_route_uses_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_wrong_method_uses_envelope(client: TestClient) -> None:
    response = client.post("/api/v1/health/live")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_request_id_is_generated_when_absent(raw_client: TestClient) -> None:
    response = raw_client.get("/missing")

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


def test_valid_incoming_request_id_is_echoed(raw_client: TestClient) -> None:
    response = raw_client.get("/missing", headers={"X-Request-ID": "nginx-abc.123"})

    assert response.headers["X-Request-ID"] == "nginx-abc.123"


def test_malformed_incoming_request_id_is_replaced(raw_client: TestClient) -> None:
    response = raw_client.get("/missing", headers={"X-Request-ID": "bad id; injected=1"})

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])
