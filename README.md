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
| `telemetry` | OpenTelemetry bootstrap (traces + metrics) + instrumentors + shutdown/flush + opt-in `enable_profiler` |
| `errors` | `ErrorCode` + `AppError` factories → RFC 9457 Problem Details with `type` URI + `error_code` |
| `security` | Keycloak JWT/JWKS validation, RBAC deps, `client_credentials` token provider |
| `storage` | S3-compatible `ObjectStorageClient` (`aioboto3`, long-lived client) |
| `http` | Problem Details + handlers + `/problems` docs, `ApiResponse` envelope, pagination, health, httpx client |
| `http.middleware` | Request-ID/trace context, security headers, access log, RED metrics, `apply_standard_middleware`, rate-limit dependency |
| `cache` | Redis factory, value cache (`Cache` / `@cached`, stampede-protected), distributed lock (auto-extend), fixed- and sliding-window rate limiters |
| `runtime` | FastAPI shell, lifespan composer, gRPC server + client channel pool (request-id interceptors), uvicorn runner |
| `persistence` | Engine/sessionmaker, structured query logging, `Base` + naming convention, Alembic helpers, `Repository` / `UnitOfWork` |
| `utils` | `retry_async` (tenacity), `new_nanoid` / `new_uuid7`, `Clock` / `FixedClock`, `AsyncCircuitBreaker` |
| `testing` | `FakeUnitOfWork`, `InMemoryRepository`, JWT test-token factory |

## Configuration and environments

`BaseAppSettings` loads `.env` first, then `.env.{environment}`, which
overrides it. The environment itself is resolved in this order:

1. an explicit argument to `resolve_environment()`
2. the real `ENVIRONMENT` process environment variable
3. `ENVIRONMENT` inside `.env`
4. `dev`

Step 3 matters more than it looks. Declaring `ENVIRONMENT=production` in `.env`
without exporting it is the natural thing to do, and reading only `os.environ`
resolves that to `dev` — so `.env.production` never loads, while `.env` still
sets `settings.environment` to `production`. The service then reports itself as
production, passes `is_production` checks, and talks to development
infrastructure, with nothing in the logs to say so.

An invalid value (`prod`, say) raises and names where it came from, rather than
falling back to `dev` and quietly relaxing security. `get_environment()` and
`settings.environment` resolve identically, so they cannot disagree, and
start-up fails outright if the env files were chosen for one environment while
the settings claim another.

```bash
ENVIRONMENT=production   # exported, or in .env — either works
```

## Correlation IDs

Every HTTP request gets an `X-Request-ID` (generated or propagated). It is:

- echoed in the response header
- bound into structlog contextvars (every log line)
- set as span attribute `http.request.id`
- forwarded on outbound HTTP via `create_http_client`
- forwarded on outbound gRPC (all four RPC shapes) by `request_id_client_interceptors` / read on inbound by `RequestIdServerInterceptor`

`GrpcChannelPool` and `GrpcServer` both attach OTel interceptors by default, so `traceparent` flows in *and* out — pass `use_otel_interceptor=False` to either if you instrument gRPC yourself.

`trace_id` (W3C `traceparent`, automatic via OTel instrumentation) is the primary distributed correlation ID; `X-Request-ID` is the human-friendly complement for clients and log grep.

## Metrics

`setup_telemetry` installs a `MeterProvider` alongside the tracer and pushes metrics to the same OTLP endpoint. Traces let you debug one request; metrics are what you alert on. Two RED instruments come for free:

| Instrument | Attributes |
|---|---|
| `http.server.request.duration` (histogram, `s`) | `http.request.method`, `http.response.status_code`, `http.route`, `error.type` |
| `http.server.active_requests` (up-down counter) | `http.request.method` |
| `rpc.server.duration` (histogram, `ms`) | `rpc.system`, `rpc.service`, `rpc.method`, `rpc.grpc.status_code`, `error.type` |

HTTP metrics come from `MetricsMiddleware` (on by default in `apply_standard_middleware`, disable with `metrics=False`); gRPC metrics from `MetricsServerInterceptor` (`GrpcServer(use_metrics_interceptor=False)` to disable). Both label by the **route template** and a bounded method set — never the raw path or verb, which are caller-controlled and would let anyone mint unbounded time series in your metrics backend. Requests that match no route carry no `http.route` at all rather than their path. Probe traffic (`/health`, `/live`, `/ready`) and `/metrics` are excluded so they do not dominate the request rate.

The instruments are created from the OTel **API**, so they are no-ops with no measurable cost until a provider exists — a service that exports nothing pays nothing for leaving them on.

To be scraped instead of pushed:

```python
from pycommon.telemetry import build_metrics_router, setup_telemetry

setup_telemetry(app, service_name=..., prometheus_metrics=True)
app.include_router(build_metrics_router())   # GET /metrics
```

Workers, gRPC servers and CLIs have no FastAPI app; they call `setup_metrics(service_name=...)` directly. Call `shutdown_telemetry()` on shutdown — it flushes both providers, and the unflushed window is exactly the one where a crashing pod's metrics matter most.

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

## Content Security Policy

`SecurityHeadersMiddleware` emits the OWASP baseline headers by default;
`Content-Security-Policy` is opt-in because there is no value that is right for
every service. The policy a JSON API wants blanks out Swagger UI and ReDoc,
which load their assets from a CDN, and a policy permissive enough for them
protects nothing:

```python
from pycommon.http.middleware import API_CONTENT_SECURITY_POLICY, apply_standard_middleware

apply_standard_middleware(app, settings, content_security_policy=API_CONTENT_SECURITY_POLICY)
```

`API_CONTENT_SECURITY_POLICY` is `default-src 'none'; frame-ancestors 'none'`.
If you serve interactive docs in production, exclude their path or widen the
policy to permit their CDN.

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

**Connection pooling** — `POSTGRES__POOL_RECYCLE_SECONDS` defaults to 1800: pooled connections are dropped and reopened once they reach that age. Whatever sits between the app and Postgres — pgbouncer, a cloud load balancer, a NAT gateway — closes idle connections on its own schedule without telling the pool, and the next checkout then fails with `server closed the connection unexpectedly` at random. **Set this below the shortest idle timeout in front of your database**; the default is wrong if yours is five minutes. `pool_pre_ping` (on by default) catches the same case but pays a round-trip on every checkout, so treat it as the safety net rather than the fix. `POSTGRES__POOL_TIMEOUT_SECONDS` caps how long a request waits for a free connection instead of blocking forever behind an exhausted pool.

**`delete()` bypasses ORM cascades.** `SqlAlchemyRepository.delete` issues a bulk `DELETE` — one round-trip instead of load-then-delete, but `cascade="all, delete-orphan"` relationships are not walked and `before_delete` / `after_delete` listeners never fire. Express cascades as database-level `ON DELETE CASCADE`, or override `delete()` in your subclass.

**Ordering in tests** — `InMemoryRepository.get_list(order_by=...)` takes attribute names (`"created_at"`, `"-created_at"`, or a list of them), since a fake has no SQL to sort with. Hand it a SQLAlchemy column expression and it raises rather than returning an unsorted page that would make the assertion meaningless.

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

## Pagination

`Page` / `PageMeta` and the cursor codec live in `pycommon.http.pagination`; the
two helpers that turn a `Select` into a `Page` live in
`pycommon.persistence.pagination`, because they take a session rather than a
request and are just as useful from a worker or a CLI job.

```python
from pycommon.persistence import paginate_cursor, paginate_offset

page = await paginate_offset(session, select(User), limit=20, offset=40)
page = await paginate_cursor(session, select(User), key_column=User.id, limit=20, cursor=cursor)
```

Which to use:

| | `paginate_offset` | `paginate_cursor` |
|---|---|---|
| Jump to page N | yes | no |
| Total count | optional (`with_total`) | no |
| Stable under concurrent inserts | **no** | yes |
| Cost at high offsets | grows | flat |

Offset pagination shifts under the reader: a row inserted before the current
offset moves everything down, so items get skipped or repeated between pages.
For a feed that changes while it is being read, use the cursor.

`key_column` must be **unique and sortable** — a UUIDv7 or bigint primary key.
A non-unique column such as `created_at` silently drops or repeats rows sharing
a value at a page boundary. `limit` is clamped to `max_limit` (default 100),
since it usually comes straight from a query string and an unbounded one asks
the database for the whole table.

`with_total=False` skips the count query. The count scans the whole filtered
set, which is free on a small table and the most expensive thing on the page
once it is not.

## ORM mixins

```python
from pycommon.persistence import Base, SoftDeleteMixin, TimestampMixin, UUIDv7PrimaryKeyMixin

class User(Base, UUIDv7PrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"
```

- **`UUIDv7PrimaryKeyMixin`** — time-ordered `id`, so inserts land at the end of
  the index rather than scattering across it the way v4 does. Generated by the
  application at INSERT, so no `RETURNING` round trip; the attribute is `None`
  until the session flushes.
- **`TimestampMixin`** — `created_at` / `updated_at` as `TIMESTAMP WITH TIME
  ZONE`, defaulted by the *database* clock. Application instances with drifting
  clocks would otherwise write timestamps that do not order consistently, and
  ordering is what these columns are for.
- **`SoftDeleteMixin`** — `deleted_at` plus `is_active()` / `is_deleted()`
  predicates. Deliberately **not** a global query filter: one that applies
  itself to every query is one people forget exists, and the symptom is a report
  that comes out short with nothing at the call site to explain it.

```python
stmt = select(User).where(User.is_active())
```

## Governance

This library is shared by multiple services, so a change here ships to all of them at once:

- **Backward compatibility first.** Breaking a public API requires a version bump and a migration note. Prefer additive changes (new parameters with defaults, new modules).
- **Semantic versioning.** Consumers pin a tag (`@v0.1.0`); never re-tag. While the major version is `0`, SemVer permits a *minor* bump to break compatibility — the migration note is what makes that safe, not the version number. See [RELEASING.md](RELEASING.md).
- **No domain logic.** Business entities, service-specific constants, or third-party partner integrations belong in the owning service, not here.
- **No silent failures.** Infrastructure setup errors must be logged or raised, never swallowed.

## Development

```bash
make install      # uv sync --extra all --extra dev
make check        # lint + format check + mypy --strict + tests (what CI runs)
```

`make help` lists every target. See [CONTRIBUTING.md](CONTRIBUTING.md) for
branching, commit and pull-request conventions, and [RELEASING.md](RELEASING.md)
for cutting a release.

## License

Proprietary / internal — adjust as needed.
