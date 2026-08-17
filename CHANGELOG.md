# Changelog

All notable changes to pycommon are recorded here. This library is shared by
multiple services, so every breaking change carries a migration note.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

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
