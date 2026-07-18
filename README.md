# pycommon

Reusable platform library for FastAPI (and related) Python services: config, logging, telemetry, security, storage, HTTP helpers, runtime, persistence, cache, and shared utilities.

## Install

### From a Git URL (recommended for consumers)

```bash
# uv
uv add "pycommon[all] @ git+https://github.com/EdwardPham1615/pycommon.git@v0.1.0"

# pip
pip install "pycommon[all] @ git+https://github.com/EdwardPham1615/pycommon.git@v0.1.0"
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

Core always installs: `pydantic`, `pydantic-settings`, `structlog`, `ecs-logging`, `opentelemetry-api`, `anyio`, `tenacity`.

| Extra | Pulls in |
|-------|----------|
| `http` | FastAPI / Starlette / httpx (Problem Details, pagination, health, middleware, client factory) |
| `storage` | aioboto3 (S3-compatible object storage) |
| `security` | FastAPI + httpx + PyJWT (Keycloak JWT / RBAC, service tokens) |
| `telemetry` | OpenTelemetry SDK + exporters + instrumentors |
| `grpc` | grpcio + OTel gRPC instrumentation |
| `runtime` | FastAPI + uvicorn + multipart + grpcio |
| `persistence` | SQLAlchemy asyncio |
| `cache` | redis (client factory, distributed lock, rate limiting) |
| `profiling` | fastapi_profiler / pyinstrument (opt-in request profiler) |
| `all` | Everything above |
| `dev` | ruff, mypy, pytest, pre-commit, aiosqlite, fakeredis |

Example: `uv add "pycommon[http,persistence,runtime] @ git+https://github.com/EdwardPham1615/pycommon.git@v0.1.0"`

## Modules

| Module | Responsibility |
|--------|----------------|
| `config` | `BaseAppSettings`, nested DB/Redis/Keycloak/OTel/S3/`ProfilerSettings` (via `POSTGRES__HOST`-style env keys) |
| `logging` | ECS JSON via `structlog` + `ecs-logging` + OTel correlation |
| `telemetry` | OpenTelemetry bootstrap + instrumentors + shutdown/flush + opt-in `enable_profiler` |
| `errors` | `ErrorCode` + `AppError` factories → RFC 9457 Problem Details with `type` URI + `error_code` |
| `security` | Keycloak JWT/JWKS validation, RBAC deps, `client_credentials` token provider |
| `storage` | S3-compatible `ObjectStorageClient` (`aioboto3`, long-lived client) |
| `http` | Problem Details + handlers + `/problems` docs, `ApiResponse` envelope, pagination, health, httpx client |
| `http.middleware` | Request-ID/trace context, security headers, access log, `apply_standard_middleware`, rate-limit dependency |
| `cache` | Redis factory, distributed lock (auto-extend), fixed-window rate limiter |
| `runtime` | FastAPI shell, lifespan composer, gRPC server + client channel pool (request-id interceptors), uvicorn runner |
| `persistence` | Engine/sessionmaker factory, `Repository` ABC, `SqlAlchemyRepository`, `UnitOfWork` |
| `utils` | `retry_async` (tenacity), `new_nanoid` / `new_uuid7`, `Clock` / `FixedClock`, `AsyncCircuitBreaker` |
| `testing` | `FakeUnitOfWork`, `InMemoryRepository`, JWT test-token factory |

## Correlation IDs

Every HTTP request gets an `X-Request-ID` (generated or propagated). It is:

- echoed in the response header
- bound into structlog contextvars (every log line)
- set as span attribute `http.request.id`
- forwarded on outbound HTTP via `create_http_client`
- forwarded on outbound gRPC via `RequestIdClientInterceptor` / read on inbound by `RequestIdServerInterceptor`

`trace_id` (W3C `traceparent`, automatic via OTel instrumentation) is the primary distributed correlation ID; `X-Request-ID` is the human-friendly complement for clients and log grep.

## Rate limiting note

Business rate limiting (per-user / per-route, Redis-backed) lives in `pycommon.cache` + `build_rate_limit_dep`. We intentionally do **not** vendor fastapi-guard into this library — it is a full security suite that would conflict with our middleware stack (CORS, headers, auth). Services that need IP ban / geo-block / bot detection can add fastapi-guard themselves at the service layer, or better: enforce those at the API gateway.

## Quick usage

```python
from pycommon.config import BaseAppSettings, DatabaseSettings, ProfilerSettings
from pycommon.http import (
    build_health_router,
    build_problem_types_router,
    register_exception_handlers,
)
from pycommon.http.middleware import apply_standard_middleware
from pycommon.logging import setup_logging
from pycommon.persistence import create_engine_and_sessionmaker, database_lifespan_resource
from pycommon.runtime import build_lifespan, create_base_app, run_uvicorn
from pycommon.telemetry import enable_profiler

class Settings(BaseAppSettings):
    app_name: str = "my-service"
    postgres: DatabaseSettings = DatabaseSettings()
    profiler: ProfilerSettings = ProfilerSettings()

settings = Settings()
setup_logging(
    level=settings.log_level,
    service_name=settings.app_name,
    environment=settings.environment.value,
)

engine, session_factory = create_engine_and_sessionmaker(settings.postgres)

app = create_base_app(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=build_lifespan([database_lifespan_resource(engine)]),
    is_dev=settings.is_dev,
)
register_exception_handlers(app, problem_type_base_url=settings.problem_type_base_url)
apply_standard_middleware(app, settings)
enable_profiler(app, settings.profiler, environment=settings.environment.value)
app.include_router(build_health_router([]))
app.include_router(build_problem_types_router(problem_type_base_url=settings.problem_type_base_url))

if __name__ == "__main__":
    run_uvicorn("main:app", reload=True)
```

Raise application errors with shared `ErrorCode` values (HTTP status is fixed per code):

```python
from pycommon.errors import AppError

raise AppError.input("Order 42 does not exist")
# → application/problem+json with type=/problems/input, error_code=3, status=400
```

Success envelope (optional):

```python
from pycommon.http import ApiResponse

return ApiResponse.ok({"id": order.id}, request_id=request_id)
```

Set `PROBLEM_TYPE_BASE_URL=https://docs.example.com/problems` to emit absolute `type` URIs.

## Governance

This library is shared by multiple services, so a change here ships to all of them at once:

- **Backward compatibility first.** Breaking a public API requires a major-version bump and a migration note. Prefer additive changes (new parameters with defaults, new modules).
- **Semantic versioning.** Consumers pin a tag (`@v0.1.0`); never re-tag.
- **No domain logic.** Business entities, service-specific constants, or third-party partner integrations belong in the owning service, not here.
- **No silent failures.** Infrastructure setup errors must be logged or raised, never swallowed.

## Development

```bash
uv sync --extra all --extra dev
uv run ruff check src tests
uv run pytest
uv run mypy src/pycommon
```

## License

Proprietary / internal — adjust as needed.
