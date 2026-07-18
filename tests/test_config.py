"""Config behavior: nested settings must not read bare env vars; env validation."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from pycommon.config import (
    BaseAppSettings,
    DatabaseSettings,
    Environment,
    KeycloakSettings,
    get_environment,
)


class _Settings(BaseAppSettings):
    postgres: DatabaseSettings = DatabaseSettings()


def test_nested_settings_ignore_bare_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    # $USER always exists in shells — it must never leak into DatabaseSettings.user.
    monkeypatch.setenv("USER", "shell-user")
    monkeypatch.setenv("HOST", "shell-host")
    db = DatabaseSettings()
    assert db.user == "postgres"
    assert db.host == "localhost"


def test_nested_settings_populated_via_delimiter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES__HOST", "db.internal")
    monkeypatch.setenv("POSTGRES__PASSWORD", "s3cret")
    settings = _Settings(_env_file=None)
    assert settings.postgres.host == "db.internal"
    assert settings.postgres.password == "s3cret"


def test_nested_settings_are_plain_models() -> None:
    assert issubclass(DatabaseSettings, BaseModel)
    from pydantic_settings import BaseSettings

    assert not issubclass(DatabaseSettings, BaseSettings)


def test_dsn_quotes_credentials() -> None:
    db = DatabaseSettings(user="app@svc", password="p@ss:word/1")
    assert "app%40svc" in db.async_dsn
    assert "p%40ss%3Aword%2F1" in db.async_dsn


def test_keycloak_urls() -> None:
    kc = KeycloakSettings(server_url="http://kc:8080/", realm="myrealm")
    assert kc.issuer == "http://kc:8080/realms/myrealm"
    assert kc.jwks_url.endswith("/protocol/openid-connect/certs")


def test_get_environment_rejects_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    get_environment.cache_clear()
    monkeypatch.setenv("ENVIRONMENT", "prod")  # typo of "production"
    with pytest.raises(ValueError, match="Invalid ENVIRONMENT"):
        get_environment()
    get_environment.cache_clear()


def test_get_environment_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    get_environment.cache_clear()
    monkeypatch.setenv("ENVIRONMENT", "staging")
    assert get_environment() is Environment.STAGING
    get_environment.cache_clear()
