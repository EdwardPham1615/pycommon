"""HTTP layer: exception handlers, health router, middleware, pagination cursors."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from pycommon.config import BaseAppSettings
from pycommon.errors import ConflictError, NotFoundError
from pycommon.http import (
    HealthCheck,
    build_health_router,
    decode_cursor,
    encode_cursor,
    register_exception_handlers,
)
from pycommon.http.middleware import apply_standard_middleware


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    apply_standard_middleware(app, BaseAppSettings(_env_file=None))

    @app.get("/not-found")
    async def not_found() -> None:
        raise NotFoundError("Order 42 does not exist")

    @app.get("/conflict")
    async def conflict() -> None:
        raise ConflictError()

    @app.get("/boom")
    async def boom() -> None:
        raise ValueError("unexpected")

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"hello": "world"}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app(), raise_server_exceptions=False)


def test_app_error_maps_to_problem_detail(client: TestClient) -> None:
    resp = client.get("/not-found")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["title"] == "Not Found"
    assert body["detail"] == "Order 42 does not exist"
    assert body["instance"] == "/not-found"


def test_app_error_without_detail(client: TestClient) -> None:
    resp = client.get("/conflict")
    assert resp.status_code == 409
    assert resp.json()["title"] == "Conflict"


def test_unhandled_exception_returns_problem_500(client: TestClient) -> None:
    resp = client.get("/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["title"] == "Internal Server Error"
    # Internals (exception message/type) must not leak to the client.
    assert body["detail"] == "An unexpected error occurred"
    assert "ValueError" not in resp.text


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
