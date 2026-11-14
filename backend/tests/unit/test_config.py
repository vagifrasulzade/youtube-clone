"""Production must refuse to start with default or weak secrets."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

STRONG_A = "a" * 48
STRONG_B = "b" * 48


def _settings(**values: str) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_production_rejects_default_secrets() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        _settings(env="production")


def test_production_rejects_short_secret() -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        _settings(env="production", jwt_secret="short", media_token_secret=STRONG_B)


def test_production_rejects_identical_secrets() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        _settings(env="production", jwt_secret=STRONG_A, media_token_secret=STRONG_A)


def test_production_accepts_strong_distinct_secrets() -> None:
    settings = _settings(env="production", jwt_secret=STRONG_A, media_token_secret=STRONG_B)

    assert settings.jwt_secret.get_secret_value() == STRONG_A


def test_development_allows_dev_defaults() -> None:
    assert _settings(env="development").env == "development"


def test_production_refuses_disabled_rate_limiting() -> None:
    with pytest.raises(ValidationError, match="RATE_LIMIT_ENABLED"):
        _settings(
            env="production",
            jwt_secret=STRONG_A,
            media_token_secret=STRONG_B,
            rate_limit_enabled="false",
        )
