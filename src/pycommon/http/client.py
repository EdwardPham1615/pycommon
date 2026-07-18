"""Standardized httpx AsyncClient factory for service-to-service calls."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog

if TYPE_CHECKING:
    from pycommon.utils.circuit_breaker import AsyncCircuitBreaker

REQUEST_ID_HEADER = "X-Request-ID"


async def _propagate_request_id(request: httpx.Request) -> None:
    """Forward the current request ID (bound by RequestContextMiddleware) downstream."""
    if REQUEST_ID_HEADER in request.headers:
        return
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    if request_id:
        request.headers[REQUEST_ID_HEADER] = str(request_id)


def create_http_client(
    *,
    base_url: str = "",
    timeout: float = 10.0,
    connect_retries: int = 3,
    propagate_request_id: bool = True,
    circuit_breaker: AsyncCircuitBreaker | None = None,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """Create an ``httpx.AsyncClient`` with standard timeout, connect retries,
    and request-ID propagation.

    When ``circuit_breaker`` is provided, every request is gated by it — open
    circuits raise :class:`~pycommon.utils.CircuitOpenError` before the request
    is sent (useful for partner/payment gateways).

    Trace-context propagation is handled by OTel's httpx instrumentation (see
    ``pycommon.telemetry``). Keep one client per upstream service alive for the
    app's lifetime (e.g. via a ``LifespanResource``) instead of creating one
    per request.
    """
    transport = httpx.AsyncHTTPTransport(retries=connect_retries)
    event_hooks: dict[str, list[Any]] = kwargs.pop("event_hooks", {"request": [], "response": []})
    if propagate_request_id:
        event_hooks.setdefault("request", []).append(_propagate_request_id)

    if circuit_breaker is not None:
        breaker = circuit_breaker

        async def _before_request(request: httpx.Request) -> None:
            breaker._before_call()

        async def _after_response(response: httpx.Response) -> None:
            if response.status_code >= 500:
                breaker._on_failure()
            else:
                breaker._on_success()

        event_hooks.setdefault("request", []).append(_before_request)
        event_hooks.setdefault("response", []).append(_after_response)

    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        transport=transport,
        event_hooks=event_hooks,
        **kwargs,
    )
