"""Base settings and environment resolution."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


def resolve_env_files(environment: str | None = None) -> list[str]:
    """Return ordered env files to load (.env then .env.{environment})."""
    env = environment or Environment.DEV
    files = [".env", f".env.{env}"]
    return [f for f in files if Path(f).exists()]


class BaseAppSettings(BaseSettings):
    """Shared settings base. Subclass in each service to add domain-specific fields."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Environment = Environment.DEV
    app_name: str = "app"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])


class DatabaseSettings(BaseSettings):
    """Nested under Settings as `postgres` — env keys: POSTGRES__HOST, etc."""

    model_config = SettingsConfigDict(extra="ignore")

    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = "postgres"
    db: str = "ecommerce"
    pool_size: int = 5
    max_overflow: int = 10
    echo: bool = False

    @property
    def async_dsn(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"

    @property
    def sync_dsn(self) -> str:
        return f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class MongoSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    uri: str = "mongodb://localhost:27017"
    db: str = "ecommerce"


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    url: str = "redis://localhost:6379/0"
    lock_timeout_seconds: int = 30


class KeycloakSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    server_url: str = "http://localhost:8080"
    realm: str = "ecommerce"
    client_id: str = "ecommerce-api"
    client_secret: str = ""
    audience: str | None = None
    jwks_cache_ttl_seconds: int = 3600
    verify_aud: bool = True

    @property
    def issuer(self) -> str:
        return f"{self.server_url.rstrip('/')}/realms/{self.realm}"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/certs"

    @property
    def token_url(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/token"

    @property
    def openid_config_url(self) -> str:
        return f"{self.issuer}/.well-known/openid-configuration"


class OtelSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = True
    service_name: str = "ecommerce-service"
    exporter_otlp_endpoint: str = "http://localhost:4317"
    exporter_otlp_insecure: bool = True
    traces_sampler_arg: float = 1.0


class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    endpoint_url: str = "http://localhost:8333"
    access_key: str = "any"
    secret_key: str = "any"
    region: str = "us-east-1"
    bucket: str = "ecommerce"
    use_path_style: bool = True
    public_base_url: str | None = None


class CelerySettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    broker_url: str = "redis://localhost:6379/1"
    result_backend: str = "redis://localhost:6379/2"
    task_always_eager: bool = False


@lru_cache
def get_environment() -> Environment:
    import os

    raw = os.getenv("ENVIRONMENT", Environment.DEV)
    try:
        return Environment(raw)
    except ValueError:
        return Environment.DEV
