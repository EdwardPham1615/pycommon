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

## [0.1.0]

Initial release.
