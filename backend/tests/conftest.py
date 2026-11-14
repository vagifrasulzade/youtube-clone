"""Shared fixtures.

Integration tests use the real PostgreSQL and Redis (docker-compose.dev.yml locally,
service containers in CI). Nothing is mocked at the database level:

- The test database ``<DATABASE_URL db>_test`` (or ``TEST_DATABASE_URL``) is dropped
  and rebuilt **from the Alembic migrations** once per session, so every run also
  proves the migrations apply to an empty database.
- Each test runs inside a transaction rolled back at teardown (SQLAlchemy savepoint
  mode); application code may call ``commit()`` freely.
- Redis uses logical DB 15 (or ``TEST_REDIS_URL``), flushed around each test.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.redis import get_redis
from app.db.session import get_db
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]
_DB_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def get_test_database_url(suffix: str = "_test") -> URL:
    override = os.environ.get("TEST_DATABASE_URL")
    url = make_url(override) if override else make_url(get_settings().database_url)
    if override and suffix == "_test":
        return url
    return url.set(database=f"{url.database}{suffix}")


def _admin_engine(url: URL) -> Engine:
    """Engine on the maintenance DB, used to create/drop the test databases."""
    return create_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )


def recreate_database(url: URL) -> None:
    name = url.database or ""
    if not _DB_NAME_RE.match(name):
        raise ValueError(f"Refusing to recreate database with unexpected name: {name!r}")
    admin = _admin_engine(url)
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()


def drop_database(url: URL) -> None:
    name = url.database or ""
    if not _DB_NAME_RE.match(name):
        raise ValueError(f"Refusing to drop database with unexpected name: {name!r}")
    admin = _admin_engine(url)
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def alembic_config(connection: Connection) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def get_test_redis_url() -> str:
    override = os.environ.get("TEST_REDIS_URL")
    if override:
        return override
    return urlsplit(get_settings().redis_url)._replace(path="/15").geturl()


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    url = get_test_database_url()
    recreate_database(url)
    engine = create_engine(url)
    with engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def redis_client() -> Iterator[Redis]:
    client = Redis.from_url(get_test_redis_url(), decode_responses=True)
    client.flushdb()
    try:
        yield client
    finally:
        client.flushdb()
        client.close()


@pytest.fixture
def client(db_session: Session, redis_client: Redis) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: redis_client
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
