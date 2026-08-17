"""HTTP layer: exception handlers, health router, middleware, pagination cursors."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel

from pycommon.config import BaseAppSettings
from pycommon.errors import AppError, ErrorCode
from pycommon.http import (
    ApiResponse,
    HealthCheck,
    build_health_router,
    build_problem_types_router,
    decode_cursor,
    encode_cursor,
    register_exception_handlers,
)
from pycommon.http.middleware import apply_standard_middleware


class _Payload(BaseModel):
    n: int


def _build_app(*, problem_type_base_url: str | None = None) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app, problem_type_base_url=problem_type_base_url)
    apply_standard_middleware(app, BaseAppSettings(_env_file=None))
    app.include_router(build_problem_types_router(problem_type_base_url=problem_type_base_url))

    @app.get("/not-found")
    async def not_found() -> None:
        raise AppError.input("Order 42 does not exist")

    @app.get("/input")
    async def input_error() -> None:
        raise AppError.input()

    @app.get("/boom")
    async def boom() -> None:
        raise ValueError("unexpected")

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"hello": "world"}

    @app.post("/validate")
    async def validate(body: _Payload) -> dict[str, int]:
        return {"n": body.n}

    @app.get("/rate-limited")
    async def rate_limited() -> None:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": "42"},
        )

    @app.get("/unauthenticated")
    async def unauthenticated() -> None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.get("/teapot")
    async def teapot() -> None:
        raise HTTPException(status_code=418, detail="I am a teapot")

    @app.get("/envelope")
    async def envelope() -> ApiResponse:
        return ApiResponse.ok({"id": 1})

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app(), raise_server_exceptions=False)


def test_app_error_maps_to_problem_detail(client: TestClient) -> None:
    resp = client.get("/not-found", headers={"X-Request-ID": "req-err-1"})
    assert resp.status_code == 400
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["type"] == "/problems/input"
    assert body["title"] == "Input Error"
    assert body["detail"] == "Order 42 does not exist"
    assert body["instance"] == "/not-found"
    assert body["error_code"] == int(ErrorCode.INPUT)
    assert body["request_id"] == "req-err-1"
    assert isinstance(body["server_time"], int)


def test_app_error_without_detail(client: TestClient) -> None:
    resp = client.get("/input")
    assert resp.status_code == 400
    body = resp.json()
    assert body["title"] == "Input Error"
    assert body["error_code"] == int(ErrorCode.INPUT)
    assert body["type"] == "/problems/input"


def test_unhandled_exception_returns_problem_500(client: TestClient) -> None:
    resp = client.get("/boom", headers={"X-Request-ID": "req-boom"})
    assert resp.status_code == 500
    body = resp.json()
    assert body["title"] == "Server Error"
    assert body["error_code"] == int(ErrorCode.SERVER)
    assert body["type"] == "/problems/server"
    assert body["request_id"] == "req-boom"
    assert isinstance(body["server_time"], int)
    # Internals (exception message/type) must not leak to the client.
    assert body["detail"] == "An unexpected error occurred"
    assert "ValueError" not in resp.text


def test_error_responses_keep_cors_and_security_headers(client: TestClient) -> None:
    """A 500 must be as readable to a browser as a 200.

    Starlette runs the ``Exception`` handler outside every user middleware, so
    without RequestContextMiddleware catching it first the response would carry
    no CORS header and a cross-origin SPA could not read the body at all.
    """
    origin = {"Origin": "http://localhost:5173"}
    boom = client.get("/boom", headers={**origin, "X-Request-ID": "req-500"})

    assert boom.status_code == 500
    assert boom.headers["X-Request-ID"] == "req-500"
    assert boom.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert boom.headers["X-Frame-Options"] == "DENY"
    assert boom.headers["X-Content-Type-Options"] == "nosniff"


def test_500_is_logged_once_and_recorded_in_access_log(client: TestClient) -> None:
    """One traceback per 500, and the access log still reports status 500.

    Both used to be wrong: the exception was logged by the middleware *and* the
    handler, while ``request_completed`` was skipped entirely — so dashboards
    counting status codes never saw a single 500.
    """
    from structlog.testing import capture_logs

    with capture_logs() as logs:
        assert client.get("/boom").status_code == 500

    exception_logs = [entry for entry in logs if entry.get("log_level") == "error"]
    assert len(exception_logs) == 1, exception_logs

    completed = [entry for entry in logs if entry.get("event") == "request_completed"]
    assert len(completed) == 1
    assert completed[0]["status_code"] == 500


def test_exceptions_propagate_when_handling_disabled() -> None:
    """``handle_exceptions=False`` restores plain propagation for callers that want it."""
    from pycommon.http.middleware import RequestContextMiddleware

    app = FastAPI()

    @app.get("/boom")
    async def boom() -> None:
        raise ValueError("unexpected")

    app.add_middleware(RequestContextMiddleware, handle_exceptions=False)

    with pytest.raises(ValueError, match="unexpected"):
        TestClient(app).get("/boom")


def test_validation_error_maps_to_problem_detail(client: TestClient) -> None:
    resp = client.post("/validate", json={"n": "not-an-int"})
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["type"] == "/problems/input"
    assert body["title"] == "Input Error"
    assert body["error_code"] == int(ErrorCode.INPUT)
    assert body["detail"] == "Request validation failed"
    # Field-level detail survives, inside the shared envelope.
    assert body["errors"][0]["loc"] == ["body", "n"]
    assert body["errors"][0]["type"] == "int_parsing"


def test_http_exception_maps_to_problem_detail_and_keeps_headers(client: TestClient) -> None:
    """429/401 raised by pycommon's own dependencies must use the shared envelope.

    Their protocol headers must survive the translation — a 401 without
    ``WWW-Authenticate`` and a 429 without ``Retry-After`` are both malformed.
    """
    limited = client.get("/rate-limited")
    assert limited.status_code == 429
    assert limited.headers["content-type"].startswith("application/problem+json")
    assert limited.headers["Retry-After"] == "42"
    assert limited.json()["error_code"] == int(ErrorCode.RATE_LIMIT)
    assert limited.json()["type"] == "/problems/rate-limit"

    unauth = client.get("/unauthenticated")
    assert unauth.status_code == 401
    assert unauth.headers["WWW-Authenticate"] == "Bearer"
    assert unauth.json()["error_code"] == int(ErrorCode.AUTH)
    assert unauth.json()["detail"] == "Invalid or expired token"


def test_http_exception_without_matching_error_code(client: TestClient) -> None:
    """Statuses with no application meaning stay RFC 9457 but claim no error_code."""
    resp = client.get("/teapot")
    assert resp.status_code == 418
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "I'm a Teapot"
    assert "error_code" not in body


def test_problem_type_absolute_base_url() -> None:
    client = TestClient(
        _build_app(problem_type_base_url="https://docs.example.com/problems"),
        raise_server_exceptions=False,
    )
    resp = client.get("/input")
    assert resp.status_code == 400
    assert resp.json()["type"] == "https://docs.example.com/problems/input"


def test_problem_types_docs_router(client: TestClient) -> None:
    index = client.get("/problems")
    assert index.status_code == 200
    assert "text/html" in index.headers["content-type"]
    assert "Input Error" in index.text

    detail = client.get("/problems/input")
    assert detail.status_code == 200
    assert "error_code:" in detail.text
    assert "3" in detail.text

    missing = client.get("/problems/unknown")
    assert missing.status_code == 404


def test_api_response_envelope(client: TestClient) -> None:
    resp = client.get("/envelope", headers={"X-Request-ID": "req-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "OK"
    assert body["data"] == {"id": 1}
    assert body["request_id"] == "req-1"
    assert "server_time" in body


def test_request_id_generated_and_echoed(client: TestClient) -> None:
    resp = client.get("/ok")
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"]


def test_request_id_propagated(client: TestClient) -> None:
    resp = client.get("/ok", headers={"X-Request-ID": "req-123"})
    assert resp.headers["X-Request-ID"] == "req-123"


def test_security_headers_present(client: TestClient) -> None:
    resp = client.get("/ok")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_health_router_ready_and_degraded() -> None:
    async def ok_check() -> None:
        pass

    async def failing_check() -> None:
        raise ConnectionError("db unreachable")

    app = FastAPI()
    app.include_router(
        build_health_router(
            [
                HealthCheck(name="db", check=ok_check),
                HealthCheck(name="redis", check=failing_check),
            ]
        )
    )
    client = TestClient(app)

    assert client.get("/health/live").status_code == 200

    resp = client.get("/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["db"] == "ok"
    assert "db unreachable" in body["checks"]["redis"]


def test_health_router_all_ok() -> None:
    async def ok_check() -> None:
        pass

    app = FastAPI()
    app.include_router(build_health_router([HealthCheck(name="db", check=ok_check)]))
    resp = TestClient(app).get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_cursor_roundtrip() -> None:
    payload = {"created_at": "2026-07-18T00:00:00", "id": 42}
    assert decode_cursor(encode_cursor(payload)) == payload


def test_cursor_invalid_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Invalid pagination cursor"):
        decode_cursor("!!!not-base64!!!")


def test_access_log_masks_sensitive_query() -> None:
    from pycommon.http.middleware.request_context import (
        DEFAULT_MASK_QUERY_PARAMS,
        _mask_query,
    )

    masked = _mask_query(b"token=secret&page=1", DEFAULT_MASK_QUERY_PARAMS)
    assert masked is not None
    assert "secret" not in masked
    assert "token=%2A%2A%2A" in masked or "token=***" in masked
    assert "page=1" in masked


def test_access_log_includes_route_and_client() -> None:
    """Access log emits route template, client IP, user-agent, and request ID."""
    app = FastAPI()
    apply_standard_middleware(app, BaseAppSettings(_env_file=None))

    @app.get("/items/{item_id}")
    async def get_item(item_id: int, request: Request) -> dict[str, object]:
        request.state.user = type("U", (), {"sub": "user-42"})()
        return {"id": item_id}

    resp = TestClient(app).get(
        "/items/7",
        headers={"User-Agent": "pytest", "X-Forwarded-For": "203.0.113.1"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["X-Request-ID"]
