"""Config behavior: nested settings must not read bare env vars; env validation."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import BaseModel

from pycommon.config import (
    BaseAppSettings,
    DatabaseSettings,
    Environment,
    KeycloakSettings,
    get_environment,
    resolve_env_files,
)
from pycommon.config.environment import resolve_environment


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


class _EnvSettings(BaseAppSettings):
    api_key: str = "unset"


@pytest.fixture
def env_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Run in an empty directory so stray .env files cannot reach the test."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    get_environment.cache_clear()
    yield tmp_path
    get_environment.cache_clear()


def test_environment_read_from_env_file_when_not_exported(env_dir: Path) -> None:
    """The bug this whole resolution order exists for.

    ``ENVIRONMENT=production`` declared only in ``.env`` used to resolve to
    ``dev``, so ``.env.production`` was never loaded — while ``.env`` still set
    ``settings.environment`` to production. The service passed an
    ``is_production`` check while running on dev infrastructure.
    """
    (env_dir / ".env").write_text("ENVIRONMENT=production\nAPI_KEY=from-base\n")
    (env_dir / ".env.production").write_text("API_KEY=from-production\n")
    (env_dir / ".env.dev").write_text("API_KEY=from-dev\n")

    assert resolve_environment() is Environment.PRODUCTION
    assert resolve_env_files() == [".env", ".env.production"]

    settings = _EnvSettings()
    assert settings.environment is Environment.PRODUCTION
    assert settings.api_key == "from-production"


def test_process_environment_beats_env_file(env_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A real env var outranks .env — that is how a deployment overrides an image."""
    (env_dir / ".env").write_text("ENVIRONMENT=dev\n")
    (env_dir / ".env.staging").write_text("API_KEY=from-staging\n")
    monkeypatch.setenv("ENVIRONMENT", "staging")

    assert resolve_environment() is Environment.STAGING
    assert _EnvSettings().api_key == "from-staging"


def test_defaults_to_dev_without_any_signal(env_dir: Path) -> None:
    assert resolve_environment() is Environment.DEV
    assert resolve_env_files() == []


def test_invalid_environment_in_env_file_raises(env_dir: Path) -> None:
    """A typo must not silently downgrade to dev, and the error must name the file."""
    (env_dir / ".env").write_text("ENVIRONMENT=prod\n")
    with pytest.raises(ValueError, match=r"Invalid ENVIRONMENT.*from \.env"):
        resolve_environment()


def test_get_environment_agrees_with_settings(env_dir: Path) -> None:
    """One environment, not two — the whole point of routing both through
    ``resolve_environment``."""
    (env_dir / ".env").write_text("ENVIRONMENT=staging\n")
    get_environment.cache_clear()
    assert get_environment() is _EnvSettings().environment is Environment.STAGING


def test_mismatch_between_resolved_files_and_settings_raises(env_dir: Path) -> None:
    """An environment-specific file that reassigns ENVIRONMENT is the one way the
    two can still diverge: files were picked for staging, settings say production."""
    (env_dir / ".env").write_text("ENVIRONMENT=staging\n")
    (env_dir / ".env.staging").write_text("ENVIRONMENT=production\n")

    with pytest.raises(ValueError, match="Environment mismatch"):
        _EnvSettings()


def test_explicit_env_file_skips_resolution(env_dir: Path) -> None:
    """``_env_file`` is an escape hatch; passing it must not trigger the guard."""
    (env_dir / "custom.env").write_text("ENVIRONMENT=production\n")
    settings = _EnvSettings(_env_file=str(env_dir / "custom.env"))
    assert settings.environment is Environment.PRODUCTION
