# pycommon

Reusable platform library for FastAPI (and related) Python services: config, logging, telemetry, security, storage, HTTP helpers, runtime, and persistence.

## Install

### From a Git URL (recommended for consumers)

```bash
# uv
uv add "pycommon[all] @ git+https://github.com/<you>/pycommon.git@v0.1.0"

# pip
pip install "pycommon[all] @ git+https://github.com/<you>/pycommon.git@v0.1.0"
```

Pin a tag or commit SHA for reproducible builds.

### Local editable (monorepo co-development)

```toml
# in your service pyproject.toml
dependencies = ["pycommon[all]"]

[tool.uv.sources]
pycommon = { path = "../pycommon", editable = true }
```

### Optional extras

Core always installs: `pydantic`, `pydantic-settings`, `structlog`, `ecs-logging`, `opentelemetry-api`.

| Extra | Pulls in |
|-------|----------|
| `http` | FastAPI / Starlette / httpx (Problem Details, pagination, middleware) |
| `storage` | aioboto3 (S3-compatible object storage) |
| `security` | FastAPI + httpx + PyJWT (Keycloak JWT / RBAC) |
| `telemetry` | OpenTelemetry SDK + exporters + instrumentors |
| `grpc` | grpcio + OTel gRPC instrumentation |
| `runtime` | FastAPI + uvicorn + multipart + grpcio |
| `persistence` | SQLAlchemy asyncio |
| `all` | Everything above |
| `dev` | ruff, mypy, pytest, pre-commit |

Example: `uv add "pycommon[http,persistence,runtime] @ git+https://..."`

## Modules

| Module | Responsibility |
|--------|----------------|
| `config` | `BaseAppSettings`, nested DB/Redis/Keycloak/OTel/S3 settings |
| `logging` | ECS JSON via `structlog` + `ecs-logging` + OTel correlation |
| `telemetry` | OpenTelemetry bootstrap + instrumentors |
| `security` | Keycloak JWT/JWKS validation + RBAC deps |
| `storage` | S3-compatible `ObjectStorageClient` (`aioboto3`) |
| `http` | RFC 9457 Problem Details, pagination |
| `http.middleware` | Request-ID/trace context, CORS factory, security headers |
| `runtime` | FastAPI shell, lifespan composer, gRPC server, uvicorn runner |
| `persistence` | `Repository` ABC, `SqlAlchemyRepository`, `UnitOfWork` |

## Quick usage

```python
from pycommon.config import BaseAppSettings
from pycommon.logging import setup_logging, get_logger
from pycommon.runtime import create_base_app, build_lifespan, LifespanResource, run_uvicorn

class Settings(BaseAppSettings):
    app_name: str = "my-service"

settings = Settings()
setup_logging(
    level=settings.log_level,
    service_name=settings.app_name,
    environment=settings.environment.value,
)

app = create_base_app(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=build_lifespan([]),
    is_dev=settings.environment.value == "dev",
)

if __name__ == "__main__":
    run_uvicorn("main:app", reload=True)
```

## Development

```bash
uv sync --extra all --extra dev
uv run ruff check src tests
uv run pytest
uv run mypy src/pycommon
```

## License

Proprietary / internal — adjust as needed.
