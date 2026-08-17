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
| `migrations` | Alembic (thin helpers; versions stay in the service) |
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
| `cache` | Redis factory, value cache (`Cache` / `@cached`, stampede-protected), distributed lock (auto-extend), fixed- and sliding-window rate limiters |
| `runtime` | FastAPI shell, lifespan composer, gRPC server + client channel pool (request-id interceptors), uvicorn runner |
| `persistence` | Engine/sessionmaker, structured query logging, `Base` + naming convention, Alembic helpers, `Repository` / `UnitOfWork` |
| `utils` | `retry_async` (tenacity), `new_nanoid` / `new_uuid7`, `Clock` / `FixedClock`, `AsyncCircuitBreaker` |
| `testing` | `FakeUnitOfWork`, `InMemoryRepository`, JWT test-token factory |

## Correlation IDs

Every HTTP request gets an `X-Request-ID` (generated or propagated). It is:

- echoed in the response header
- bound into structlog contextvars (every log line)
- set as span attribute `http.request.id`
- forwarded on outbound HTTP via `create_http_client`
- forwarded on outbound gRPC (all four RPC shapes) by `request_id_client_interceptors` / read on inbound by `RequestIdServerInterceptor`

`GrpcChannelPool` and `GrpcServer` both attach OTel interceptors by default, so `traceparent` flows in *and* out — pass `use_otel_interceptor=False` to either if you instrument gRPC yourself.

`trace_id` (W3C `traceparent`, automatic via OTel instrumentation) is the primary distributed correlation ID; `X-Request-ID` is the human-friendly complement for clients and log grep.

## Deploying behind a proxy

**If you run behind an ingress or load balancer, you must tell the ASGI server which peers to trust** — otherwise three things fail silently.

uvicorn only honours `X-Forwarded-For` / `X-Forwarded-Proto` when the immediate peer is listed in `forwarded_allow_ips`, which defaults to `127.0.0.1`. In Kubernetes the peer is the ingress pod, never loopback, so the headers are ignored and:

- `scope["scheme"]` stays `http`, so **`SecurityHeadersMiddleware` never emits HSTS** even though `hsts=True` is the default
- `scope["client"]` stays the ingress address, so **every anonymous caller shares one rate-limit bucket** — `build_rate_limit_dep(..., times=10, seconds=60)` on `/login` becomes a global 10/min for the whole internet, which one bot can exhaust for everyone
- access logs record the ingress address instead of the caller

Fix it once, at the server:

```bash
FORWARDED_ALLOW_IPS='10.0.0.0/8'   # or the ingress CIDR / '*' if the proxy is the only reachable peer
```

or explicitly:

```python
run_uvicorn("main:app", forwarded_allow_ips=settings.forwarded_allow_ips)
```

Prefer the narrowest value that matches your proxy. `'*'` trusts `X-Forwarded-For` from *any* peer, which is safe only when nothing but the proxy can reach the port.

pycommon reads the resolved value through a single helper, `pycommon.http.middleware.client_ip`, shared by the access log and the rate-limit dependency so both always agree on who the caller is. It deliberately never parses `X-Forwarded-For` itself: any client can send that header, and trusting it unconditionally lets callers forge their own address in your logs and rate-limit buckets.

## Caching

Cache-aside for **values**, not HTTP responses — it takes no `Request`, so the same code works in a route, a gRPC servicer, a Celery worker or a CLI job.

```python
from pycommon.cache import Cache, cached, pydantic_serializer

@cached(redis, namespace="products", ttl_seconds=300)
async def get_product(product_id: str) -> dict:
    return await repository.get(product_id)

await get_product.invalidate("abc-123")     # after a write

# or explicitly
cache = Cache(redis, namespace="products", ttl_seconds=300)
product = await cache.get_or_set(product_id, lambda: repository.get(product_id))
await cache.delete(product_id)
await cache.clear()                          # whole namespace
```

- **Stampede protection is on by default.** When a popular key expires under load, only one caller computes it; the rest wait briefly and read what it stored. Without it every concurrent request goes to the database at once.
- **`ttl_seconds` is required**, not defaulted. An entry with no expiry is a leak plus permanently stale data if an invalidation is ever missed — pass `None` explicitly for entries you always invalidate by hand.
- **Fails open.** If Redis is unreachable the factory runs and its value is returned uncached. So does a poisoned entry: it counts as a miss instead of failing every request until the TTL expires.
- **Serialization** defaults to JSON (dict / list / scalars). For models use `serializer=pydantic_serializer(Product)`, which returns the model, not a dict.
- Keys are `cache:{namespace}:key` — the braces are a Redis Cluster hash tag, keeping a namespace on one slot so `clear()` scans a single node.

## Rate limiting

```python
from pycommon.cache import RedisRateLimiter, RedisSlidingWindowRateLimiter
from pycommon.http.middleware.rate_limit import build_rate_limit_dep

rate_limited = build_rate_limit_dep(RedisRateLimiter(redis), "10/second")

@router.post("/login", dependencies=[Depends(rate_limited)])
async def login(): ...
```

Rates accept `"100/minute"`, `"10/15seconds"`, `"100 per 2 minutes"`, `"5/s"`, or explicit `times=`/`seconds=`. Every response carries `X-RateLimit-Limit` / `-Remaining` / `-Reset`; 429s add `Retry-After`.

| Limiter | Trade-off |
|---|---|
| `RedisRateLimiter` | Fixed window — one counter per key, cheapest. Allows up to `2 × times` across a window boundary. |
| `RedisSlidingWindowRateLimiter` | Sliding window log — no boundary burst, at one sorted-set entry per allowed request. Scores come from Redis `TIME`, so skewed instance clocks cannot corrupt a shared window. |
| `InMemoryRateLimiter` | Per-process, for dev and tests. Bounded LRU (`max_keys`). |

Both Redis limiters **fail open**: if Redis is unreachable the request is allowed, a warning is logged, and `RateLimitResult.degraded` is set so degraded traffic stays visible in metrics rather than looking like traffic that genuinely passed. Pass `fail_open=False` where exceeding the limit is worse than rejecting traffic (payment retries, SMS sending).

Rate limits are only per-caller if the client IP is resolved correctly — see [Deploying behind a proxy](#deploying-behind-a-proxy).

## Libraries we deliberately don't vendor

Both belong at the **service layer**, not here. Adding either to pycommon would push its opinions onto every service at once.

**fastapi-guard** — a full security suite that would conflict with our middleware stack (CORS, headers, auth). Services needing IP ban / geo-block / bot detection can add it themselves, or better: enforce those at the API gateway. Business rate limiting lives in `pycommon.cache` + `build_rate_limit_dep`.

**fastapi-redis-sdk** (official Redis SDK) — offers HTTP response caching with ETag/304, which pycommon does not. Worth adding to a service that needs it, but not to pycommon, because:

- it is FastAPI-coupled (`FastAPIRedis(app).lifespan()`, everything via `Depends()`, cache keys derived from `Request`), while `pycommon.cache` must also work from gRPC servicers, Celery workers and CLI jobs
- its `.lifespan()` overlaps `build_lifespan`, and its flat `REDIS_*` env keys conflict with `BaseAppSettings`' nested `REDIS__URL`
- its 429 is not problem+json, which would reopen the error-contract inconsistency this library just fixed
- it has no distributed lock, so it does not replace `redis_lock` either
- it requires Redis 7.4+ and is pre-1.0

Ideas worth borrowing from it are already implemented here: fail-open limiting with a `degraded` flag, the rate DSL, and `X-RateLimit-*` headers.

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
from pycommon.persistence import (
    create_engine_and_sessionmaker,
    database_lifespan_resource,
    migration_lifespan_resource,
)
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
    lifespan=build_lifespan(
        [
            migration_lifespan_resource(settings.postgres),  # no-op unless auto_migrate=True
            database_lifespan_resource(engine),
        ]
    ),
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

## Error contract

`register_exception_handlers` makes **every** error response RFC 9457 Problem Details — not just `AppError`:

| Raised | Status | Result |
|--------|--------|--------|
| `AppError.*` | per `ErrorCode` | `application/problem+json` |
| `RequestValidationError` (FastAPI) | 422 | problem+json; field errors in the `errors` member |
| `HTTPException` | as raised | problem+json; `exc.headers` preserved (`WWW-Authenticate`, `Retry-After`) |
| anything else | 500 | problem+json; exception details never leak to the client |

`ErrorCode` values: `OK=0`, `SERVER=1`, `DATABASE=2`, `INPUT=3`, `AUTH=4`, `APP_CHECK=5`, `FORBIDDEN=6`, `NOT_FOUND=7`, `CONFLICT=8`, `RATE_LIMIT=9`. A status with no application meaning (405, 418, …) still returns problem+json but omits `error_code` rather than claiming a misleading one.

**Error responses carry the same headers as successful ones** — `X-Request-ID`, CORS, and security headers. This requires `apply_standard_middleware` (or `RequestContextMiddleware` installed inside your CORS/security layers): Starlette runs the `Exception` handler in `ServerErrorMiddleware`, outside every user middleware, so a 500 built there would otherwise reach a cross-origin SPA with no CORS header at all — unreadable, and without the request ID needed to trace it.

Because `RequestContextMiddleware` fully handles unhandled exceptions, they no longer propagate. In tests use `TestClient(app, raise_server_exceptions=False)` and assert on the 500, or pass `RequestContextMiddleware(handle_exceptions=False)` to let them bubble up.

Success envelope (optional):

```python
from pycommon.http import ApiResponse

return ApiResponse.ok({"id": order.id})
```

Set `PROBLEM_TYPE_BASE_URL=https://docs.example.com/problems` to emit absolute `type` URIs.

## Persistence notes

**Query logging** — set `POSTGRES__LOG_QUERIES=true` for structured SQL logs (statement + `duration_ms`) via structlog. Use `POSTGRES__SLOW_QUERY_THRESHOLD_MS=200` to only warn on slow queries. Failed queries are always logged as `db_query_failed` regardless of the threshold — a deadlock or statement timeout is worth seeing however fast it failed. Keep `POSTGRES__LOG_QUERY_PARAMS=false` unless debugging (params may contain PII). `POSTGRES__ECHO=true` remains available for raw SQLAlchemy echo in local dev.

**Migrations** — pycommon provides thin Alembic helpers; each service owns `alembic.ini`, `alembic/env.py`, and `alembic/versions/`.

```bash
uv add "pycommon[persistence,migrations]"
```

```python
from pycommon.persistence import Base, build_alembic_config, upgrade_to_head

# models inherit Base (shared naming convention for autogenerate)
class Order(Base):
    __tablename__ = "orders"
    ...

# CLI / deploy job
upgrade_to_head(settings.postgres, script_location="alembic")
```

In `alembic/env.py`, set `target_metadata = Base.metadata` and prefer `build_alembic_config(settings)` for the URL. Keep `POSTGRES__AUTO_MIGRATE=false` in production and run upgrades from a deploy job; enable it only for local/dev if desired via `migration_lifespan_resource`.

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
