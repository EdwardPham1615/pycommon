"""gRPC request-id interceptor unit tests (no live server required)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import structlog

from pycommon.runtime.grpc_interceptors import (
    REQUEST_ID_METADATA_KEY,
    RequestIdClientInterceptor,
    RequestIdServerInterceptor,
)


async def test_server_interceptor_binds_incoming_request_id() -> None:
    interceptor = RequestIdServerInterceptor()
    details = SimpleNamespace(invocation_metadata=((REQUEST_ID_METADATA_KEY, "incoming-rid"),))
    continuation = AsyncMock(return_value="handler")

    structlog.contextvars.clear_contextvars()
    result = await interceptor.intercept_service(continuation, details)
    assert result == "handler"
    assert structlog.contextvars.get_contextvars().get("request_id") == "incoming-rid"
    continuation.assert_awaited_once()


async def test_server_interceptor_generates_when_missing() -> None:
    interceptor = RequestIdServerInterceptor()
    details = SimpleNamespace(invocation_metadata=())
    continuation = AsyncMock(return_value=None)

    structlog.contextvars.clear_contextvars()
    await interceptor.intercept_service(continuation, details)
    rid = structlog.contextvars.get_contextvars().get("request_id")
    assert rid and isinstance(rid, str) and len(rid) > 0


async def test_client_interceptor_attaches_request_id() -> None:
    interceptor = RequestIdClientInterceptor()
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="outbound-rid")

    captured: dict[str, object] = {}

    async def continuation(details: object, request: object) -> str:
        captured["details"] = details
        return "ok"

    details = MagicMock()
    details.method = "/svc/Method"
    details.timeout = None
    details.metadata = None
    details.credentials = None
    details.wait_for_ready = None

    result = await interceptor.intercept_unary_unary(continuation, details, {})
    assert result == "ok"
    new_details = captured["details"]
    metadata = list(getattr(new_details, "metadata", []))
    assert (REQUEST_ID_METADATA_KEY, "outbound-rid") in metadata
