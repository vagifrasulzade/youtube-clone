"""Health probes used by Docker health checks and deploy.sh."""

from fastapi.testclient import TestClient
from redis import Redis

from app.core.redis import get_redis
from app.main import app


def test_live_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_database_redis_and_storage_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "ok", "storage": "ok"},
    }


def test_ready_returns_503_when_redis_is_unreachable(client: TestClient) -> None:
    unreachable = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2, socket_timeout=0.2)
    app.dependency_overrides[get_redis] = lambda: unreachable

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "checks": {"database": "ok", "redis": "error", "storage": "ok"},
    }


def test_openapi_docs_are_served(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "/api/v1/health/ready" in schema["paths"]
