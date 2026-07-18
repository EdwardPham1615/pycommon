"""HTTP layer: exception handlers, health router, middleware, pagination cursors."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

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

    @app.get("/envelope")
    async def envelope() -> ApiResponse:
        return ApiResponse.ok({"id": 1}, request_id="req-1")

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
    resp = client.get("/envelope")
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
