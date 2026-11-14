"""Migrations are reversible and match the SQLAlchemy models exactly."""

from alembic import command
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.pool import NullPool

from tests.conftest import alembic_config, drop_database, get_test_database_url, recreate_database

EXPECTED_TABLES = {
    "alembic_version",
    "channels",
    "comments",
    "moderation_actions",
    "playlist_videos",
    "playlists",
    "refresh_tokens",
    "reports",
    "roles",
    "subscriptions",
    "users",
    "video_permissions",
    "video_reactions",
    "video_views",
    "videos",
}


def test_upgrade_downgrade_upgrade_on_empty_database() -> None:
    url = get_test_database_url("_migrations_test")
    recreate_database(url)
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            config = alembic_config(conn)
            command.upgrade(config, "head")
            assert set(inspect(conn).get_table_names()) == EXPECTED_TABLES

            command.downgrade(config, "base")
            assert set(inspect(conn).get_table_names()) == {"alembic_version"}

            command.upgrade(config, "head")
            assert set(inspect(conn).get_table_names()) == EXPECTED_TABLES
    finally:
        engine.dispose()
        drop_database(url)


def test_models_and_migrations_have_no_drift(db_engine: Engine) -> None:
    """`alembic check` fails if autogenerate would produce a new migration."""
    with db_engine.connect() as conn:
        command.check(alembic_config(conn))
