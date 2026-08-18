# Changelog

All notable changes to pycommon are recorded here. This library is shared by
multiple services, so every breaking change carries a migration note.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- **`ENVIRONMENT` declared in `.env` now selects the right env file.**
  `resolve_env_files()` read `ENVIRONMENT` from `os.environ` only, so putting
  `ENVIRONMENT=production` in `.env` — without also exporting it — resolved to
  `dev`, and `.env.production` was never loaded. `.env` still set
  `settings.environment` to `production`, so the service reported itself as
  production, passed `is_production` checks, and ran against development
  database and broker addresses. Nothing logged a warning, because from each
  component's point of view nothing had gone wrong.

  Resolution order is now: explicit argument, then the real `ENVIRONMENT`
  variable, then `ENVIRONMENT` inside `.env`, then `dev`. An invalid value
  raises and names where it came from.

  *Migration:* if a deployment relied on the old behaviour — `ENVIRONMENT` in
  `.env` while intending the `dev` files to load — it now loads
  `.env.{environment}` instead. Check which env files each environment
  actually ships before upgrading. `BaseAppSettings` also raises on start-up if
  the env files were resolved for one environment while the loaded settings
  claim another, which only happens when an environment-specific file
  reassigns `ENVIRONMENT`.

- **`get_environment()` and `settings.environment` can no longer disagree.**
  Both now resolve through `resolve_environment()`; previously the first read
  `os.environ` and the second read the env files, so they answered differently
  in exactly the case above.

- **One definition of the current request ID.** `problem.py` read
  `request.state.request_id` while the response envelope, the httpx client and
  the gRPC interceptors read structlog contextvars. Problem Details now falls
  back to the logging context when the scope carries nothing, so an error body
  no longer reports `request_id: null` for a request whose logs have one.

- **Readiness checks run concurrently.** `/health/ready` awaited each check in
  turn, so its worst case was the *sum* of the timeouts — three dependencies at
  the 5s default is 15 seconds, well past the 1 to 5 seconds a Kubernetes
  readiness probe waits. The probe timed out and marked the pod unready before
  the endpoint could answer that everything was fine. A timing-out check no
  longer delays or cancels its siblings.

- **Database connections are recycled before a proxy closes them.** The engine
  was created without `pool_recycle`, so a pooled connection that pgbouncer or a
  cloud load balancer had silently dropped stayed in the pool until some
  unlucky request checked it out and failed with "server closed the connection
  unexpectedly". Now `POSTGRES__POOL_RECYCLE_SECONDS` (default 1800) — set it
  below the shortest idle timeout in front of your database.

- **`SqlAlchemyRepository` resolves its primary key once per model.**
  `_pk_column` ran `inspect()` on every access, so each `get()` and `delete()`
  re-derived an answer fixed at import time, and a repository built per request
  never got to reuse it.

- **`InMemoryRepository.get_list` accepts `order_by`.** The real repository had
  it and the fake did not, so the fake could not stand in for it in any test
  that ordered results. `order_by` is now part of the `Repository` contract.

- **Error responses now carry `X-Request-ID`, CORS and security headers.**
  Starlette runs the `Exception` handler in `ServerErrorMiddleware`, outside
  every user middleware, so 500 responses previously reached the client with
  none of them. A cross-origin SPA could not read the body at all — the browser
  turned it into an opaque CORS error, taking the request ID with it.
  `RequestContextMiddleware` now renders unhandled exceptions itself, inside the
  CORS and security-header layers.

- **Unhandled exceptions are logged once, and 500s appear in the access log.**
  Each 500 previously emitted two full tracebacks (middleware and handler), while
  the `request_completed` access-log line was skipped entirely — so dashboards
  counting status codes never saw a single 500 and error-rate alerts could not
  fire.

- **`apply_standard_middleware` ordering.** `SecurityHeadersMiddleware` now wraps
  `RequestContextMiddleware` instead of sitting inside it, so middleware-rendered
  error responses also get security headers.

- **Circuit breakers now open on connection failures.** `create_http_client`
  gated requests through httpx *response* event hooks, which never fire when
  there is no response — so a breaker counted 5xx only and stayed closed
  through connect refusals and timeouts, exactly the outage it exists to
  contain. Gating moved to `CircuitBreakerTransport`, which sees both. It wraps
  the retrying transport, so one logical request counts as one outcome however
  many connect retries it took. 4xx still leaves the breaker closed.

- **`redis_lock(auto_extend=True)` no longer leaks the lock.** The auto-extend
  task only caught `LockError`, so a `ConnectionError` killed it; reaping it in
  the `finally` block re-raised that error, which skipped `lock.release()` and
  replaced the guarded block's own exception with an infrastructure one. The
  lock then stayed held for the rest of its TTL, blocking every other worker.

- **Failed SQL queries are now logged, and query timings no longer leak.**
  `install_query_logger` pushed a timestamp per execution onto `conn.info` and
  popped it in `after_cursor_execute` — which never fires for a failing query.
  Entries accumulated for the whole life of each pooled connection and could
  mis-pair later measurements. Worse, deadlocks, statement timeouts and
  constraint violations were logged nowhere at all. Timing now lives on the
  per-execution context, and a `handle_error` listener emits `db_query_failed`
  regardless of `slow_query_threshold_ms`.

- **Access logs no longer trust a spoofable client address.** The access log
  parsed `X-Forwarded-For` unconditionally while the rate limiter used
  `request.client.host` — two different answers to "who is the caller" in one
  library, and the logged one could be forged by any client. Both now read the
  address the ASGI server resolved, through the shared
  `http.middleware.client_ip`.

- **Outbound gRPC calls are traced again.** `GrpcChannelPool` attached no OTel
  client interceptor, so channels sent no `traceparent` and a callee's spans
  started a brand-new trace instead of joining the caller's. Inbound calls were
  instrumented, which made the gap easy to miss: the trace broke at every
  service boundary. Disable with `GrpcChannelPool(use_otel_interceptor=False)`.

- **Request IDs propagate on streaming RPCs.** gRPC dispatches to a different
  interceptor class per RPC shape, and only the unary-unary one was registered,
  so unary-stream, stream-unary and stream-stream calls silently dropped the
  correlation ID.

- **Rate limiting no longer takes the API down when Redis does.** `hit()` raised
  straight through, so a Redis outage turned every rate-limited endpoint into a
  500. Both Redis limiters now fail open by default and set
  `RateLimitResult.degraded`; `fail_open=False` restores the strict behaviour.

- **`InMemoryRateLimiter` is bounded.** Its window map grew one entry per
  distinct key — per client IP in practice — and never shrank.

- **`RedisRateLimiter` no longer ships its Lua script on every request.** It
  uses `register_script` (EVALSHA) instead.

- **`create_redis` sets socket timeouts and health checks.** redis-py blocks
  forever by default, so a hung connection pinned an event-loop task; idle
  connections are now pinged before reuse, which is what stops a pool behind a
  load balancer handing out sockets the balancer already dropped.

### Changed

- **`pycommon.__version__` now comes from installed package metadata**
  (`importlib.metadata`) instead of a literal that had to be kept in step with
  `pyproject.toml` by hand. Imported from a source tree with nothing installed
  it reads `0.0.0+unknown` rather than a stale number.

- **BREAKING — `AsyncCircuitBreaker._before_call` / `_on_success` /
  `_on_failure` are now public** (`before_call`, `on_success`, `on_failure`).
  `pycommon.http` was already calling them across module boundaries; they are
  the supported way to drive a breaker from an integration that cannot use
  `call()` or the context manager.

- **BREAKING — validation errors and `HTTPException` now return
  `application/problem+json`.** Previously only `AppError` and unhandled
  exceptions used RFC 9457; everything else returned FastAPI's default
  `{"detail": ...}`. This affected pycommon's own dependencies: the 429 from
  `build_rate_limit_dep` and the 401/403 from `create_auth_deps` all used the
  non-standard shape, so the library broke the contract it defines.

  *Migration:* clients parsing `{"detail": ...}` for 4xx must read the Problem
  Details envelope instead. Validation failures keep their field-level detail —
  it moves from `detail` to the `errors` member:

  ```jsonc
  // before                          // after
  {"detail": [{"loc": ["body","n"],  {"type": "/problems/input",
               "type": "int_parsing", "title": "Input Error",
               "msg": "..."}]}        "status": 422,
                                      "detail": "Request validation failed",
                                      "error_code": 3,
                                      "errors": [{"loc": ["body","n"],
                                                  "type": "int_parsing",
                                                  "msg": "..."}]}
  ```

  `exc.headers` is preserved, so `WWW-Authenticate` on 401 and `Retry-After` on
  429 still reach the client.

- **BREAKING — unhandled exceptions no longer propagate out of the ASGI stack.**
  `RequestContextMiddleware` handles them and returns a 500. Tests relying on
  `TestClient(app)` raising must use `raise_server_exceptions=False` and assert
  on the response, or install the middleware with `handle_exceptions=False`.

### Added

- `config.resolve_environment()` — the single resolution used by
  `resolve_env_files()`, `get_environment()` and `BaseAppSettings`.
- `logging.current_request_id()` — one reader for the request ID bound to the
  current context, working in HTTP handlers, outbound clients, gRPC servicers
  and workers alike.
- `SecurityHeadersMiddleware(content_security_policy=...)` and
  `apply_standard_middleware(content_security_policy=...)`, plus
  `API_CONTENT_SECURITY_POLICY` (`default-src 'none'; frame-ancestors 'none'`)
  for JSON-only services. Off by default: that policy blanks out Swagger UI and
  ReDoc, and a policy loose enough for them protects nothing — so shipping
  either as a default would silently break some services and silently fail to
  protect others.
- **RED metrics for HTTP and gRPC.** `pycommon.telemetry` set up traces only, so
  a service could be debugged one request at a time but not alerted on: no rate,
  no error ratio, no latency distribution. `setup_telemetry` now installs a
  `MeterProvider` alongside the tracer (same OTLP endpoint) and two layers record
  through it — `http.middleware.MetricsMiddleware`, on by default in
  `apply_standard_middleware`, and `runtime.MetricsServerInterceptor`, on by
  default in `GrpcServer`. Instruments come from the OTel *API*, so they stay
  free no-ops in a service that exports no metrics.

  Emitted: `http.server.request.duration`, `http.server.active_requests`,
  `rpc.server.duration`, with semconv attributes and bucket advisories. Series
  are labelled by the **route template**, never the raw path, and by a bounded
  method set — both are caller-controlled, and recording them verbatim lets any
  scanner mint unbounded cardinality in the metrics backend.
- `telemetry.setup_metrics` / `shutdown_metrics` — usable without a FastAPI app,
  for workers, gRPC servers and CLIs. `shutdown_telemetry` now flushes both
  providers.
- `telemetry.build_metrics_router` — Prometheus `/metrics` for clusters that
  scrape rather than receive OTLP, enabled by
  `setup_telemetry(prometheus_metrics=True)`. It answers 503 until metrics are
  initialized instead of serving an empty page a scraper would read as healthy.
- `OtelSettings.metrics_enabled`, `metrics_export_interval_ms`,
  `prometheus_enabled`, `prometheus_path`. Metrics are switchable separately
  from traces: sampling traces down is normal, but a sampled rate or error
  ratio means nothing.
- `apply_standard_middleware(metrics=...)`, `GrpcServer(use_metrics_interceptor=...)`.
- `DatabaseSettings.pool_recycle_seconds`, `pool_timeout_seconds`.
- `InMemoryRepository(default_order_by=...)`, and `order_by` on
  `Repository.get_list`. Ordering in the fake is by attribute name
  (`"-created_at"`); a SQLAlchemy expression raises rather than being ignored,
  because a silently unsorted page is a test that passes while asserting
  nothing.
- `ErrorCode.FORBIDDEN` (403), `NOT_FOUND` (404), `CONFLICT` (409),
  `RATE_LIMIT` (429), with matching `PROBLEM_TYPES` entries, `/problems/*` docs
  pages, and `AppError.forbidden()` / `.not_found()` / `.conflict()` /
  `.rate_limit()` factories.
- `errors.error_code_for_status()` — maps an HTTP status to an `ErrorCode`,
  returning `None` when no application code fits.
- `http.validation_exception_handler`, `http.http_exception_handler`, and
  `http.unhandled_problem_response` (builds the canonical 500 body from plain
  values, for pure-ASGI callers with no `Request` object).
- `RequestContextMiddleware(handle_exceptions=...)`.
- `problem_response(headers=...)`.
- `http.CircuitBreakerTransport` and `create_http_client(transport=...)` — swap
  the network layer for `httpx.MockTransport` in tests, or a custom transport.
- `http.middleware.client_ip(scope)` — one definition of the caller's address,
  shared by the access log and the rate-limit dependency.
- `run_uvicorn(forwarded_allow_ips=...)`, plus a "Deploying behind a proxy"
  section in the README. uvicorn's `127.0.0.1` default never matches a
  Kubernetes ingress pod, so until this is configured HSTS is never emitted and
  every anonymous caller shares one rate-limit bucket.

- **`cache.Cache` and the `@cached` decorator** — cache-aside for values and
  async functions, closing the gap where a module named `cache` could hold a
  lock and count requests but not actually cache anything. Takes no `Request`,
  so it works from gRPC servicers, Celery workers and CLI jobs as well as
  routes. Stampede protection (built on the existing `redis_lock`) is on by
  default, `ttl_seconds` is required rather than defaulted, and both reads and
  writes fail open. Ships `JsonSerializer` and `pydantic_serializer`.
- `cache.RedisSlidingWindowRateLimiter` — sliding window log, no burst at
  window boundaries. Scores come from Redis `TIME`, so instances with skewed
  clocks cannot corrupt a shared window, and denied requests are not recorded
  so a client hammering a closed limit cannot keep extending it.
- `cache.parse_rate` and `build_rate_limit_dep(limiter, "100/minute")` — also
  accepts `"10/15seconds"`, `"100 per 2 minutes"`, `"5/s"`.
- `X-RateLimit-Limit` / `-Remaining` / `-Reset` on every rate-limited response.
- `RedisSettings.socket_timeout_seconds`, `socket_connect_timeout_seconds`,
  `health_check_interval_seconds`, `retry_on_timeout`.
- `runtime.default_otel_client_interceptors` and
  `GrpcChannelPool(use_otel_interceptor=...)`, mirroring the server side.
- `RequestIdUnaryStreamClientInterceptor`,
  `RequestIdStreamUnaryClientInterceptor`,
  `RequestIdStreamStreamClientInterceptor`.

### Removed

- `http.middleware.request_context.FORWARDED_FOR_HEADER` — the middleware no
  longer parses that header (see above).

## [0.1.0]

Initial release.
