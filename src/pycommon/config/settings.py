"""Base settings and reusable nested settings groups.

Nested groups are plain ``BaseModel`` (not ``BaseSettings``) on purpose: a
``BaseSettings`` subclass instantiated standalone reads *bare* environment
variables (e.g. field ``user`` would pick up the shell's ``$USER``). As plain
models they are only populated through the parent settings class via the
``__`` nested delimiter (e.g. ``POSTGRES__HOST``).

Usage in a service::

    class Settings(BaseAppSettings):
        app_name: str = "my-service"
        postgres: DatabaseSettings = DatabaseSettings()
        keycloak: KeycloakSettings = KeycloakSettings()
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from pycommon.config.environment import Environment, resolve_env_files


class BaseAppSettings(BaseSettings):
    """Shared settings base. Subclass in each service to add domain-specific fields.

    Env files are resolved at instantiation time: ``.env`` first, then
    ``.env.{ENVIRONMENT}`` (which takes priority). Pass ``_env_file`` explicitly
    to override.
    """

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

    # Prefix for RFC 9457 Problem Details ``type`` URIs (e.g. https://docs.example.com/problems).
    # When unset, handlers emit path-absolute types like ``/problems/input``.
    problem_type_base_url: str | None = None

    def __init__(self, **kwargs: Any) -> None:
        if "_env_file" not in kwargs:
            env_files = resolve_env_files()
            if env_files:
                kwargs["_env_file"] = env_files
        super().__init__(**kwargs)

    @property
    def is_dev(self) -> bool:
        return self.environment is Environment.DEV

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


class DatabaseSettings(BaseModel):
    """Nested under a service's settings as ``postgres`` — env keys: ``POSTGRES__HOST``, etc."""

    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = "postgres"
    db: str = "app"
    pool_size: int = 5
    max_overflow: int = 10
    pool_pre_ping: bool = True
    echo: bool = False

    def _dsn(self, driver: str) -> str:
        auth = f"{quote_plus(self.user)}:{quote_plus(self.password)}"
        return f"postgresql+{driver}://{auth}@{self.host}:{self.port}/{self.db}"

    @property
    def async_dsn(self) -> str:
        return self._dsn("asyncpg")

    @property
    def sync_dsn(self) -> str:
        return self._dsn("psycopg")


class MongoSettings(BaseModel):
    uri: str = "mongodb://localhost:27017"
    db: str = "app"


class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379/0"
    max_connections: int = 10
    lock_timeout_seconds: int = 30


class KeycloakSettings(BaseModel):
    server_url: str = "http://localhost:8080"
    realm: str = "app"
    client_id: str = "app-api"
    client_secret: str = ""
    audience: str | None = None
    algorithms: list[str] = Field(default_factory=lambda: ["RS256"])
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


class OtelSettings(BaseModel):
    enabled: bool = True
    service_name: str = "app"
    exporter_otlp_endpoint: str = "http://localhost:4317"
    exporter_otlp_insecure: bool = True
    traces_sampler_arg: float = 1.0


class StorageSettings(BaseModel):
    endpoint_url: str = "http://localhost:8333"
    access_key: str = "any"
    secret_key: str = "any"
    region: str = "us-east-1"
    bucket: str = "app"
    use_path_style: bool = True
    public_base_url: str | None = None


class CelerySettings(BaseModel):
    broker_url: str = "redis://localhost:6379/1"
    result_backend: str = "redis://localhost:6379/2"
    task_always_eager: bool = False


class ProfilerSettings(BaseModel):
    """Opt-in pyinstrument profiler (requires the ``profiling`` extra).

    Defaults are safe for production: disabled, low sample rate, only profile
    slow requests / 5xx, dashboard off.
    """

    enabled: bool = False
    sample_rate: float = 0.1
    slow_request_threshold_ms: float = 200.0
    always_profile_errors: bool = True
    enable_dashboard: bool = False
    dashboard_path: str = "/__profiler__"
    allow_dashboard_in_production: bool = False
    filter_paths: list[str] = Field(
        default_factory=lambda: ["/health", "/health/live", "/health/ready"]
    )
