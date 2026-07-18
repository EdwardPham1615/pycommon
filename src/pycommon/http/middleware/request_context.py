"""Request-ID + OpenTelemetry context binding for structlog (pure ASGI)."""

from __future__ import annotations

import time
import uuid
from typing import Any
from urllib.parse import parse_qsl, urlencode

import structlog
from opentelemetry import trace
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
FORWARDED_FOR_HEADER = "X-Forwarded-For"

# Query keys whose values are replaced with "***" in access logs.
DEFAULT_MASK_QUERY_PARAMS = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "api_key",
        "apikey",
        "authorization",
    }
)


def _client_address(scope: Scope, headers: Headers) -> str | None:
    forwarded = headers.get(FORWARDED_FOR_HEADER)
    if forwarded:
        # First hop is the original client; the rest are proxies.
        return forwarded.split(",")[0].strip() or None
    client = scope.get("client")
    if client and isinstance(client, (list, tuple)) and client:
        return str(client[0])
    return None


def _mask_query(raw_query: bytes | str, mask_params: frozenset[str]) -> str | None:
    if not raw_query:
        return None
    query = raw_query.decode() if isinstance(raw_query, bytes) else raw_query
    if not query:
        return None
    pairs = parse_qsl(query, keep_blank_values=True)
    masked = [(k, "***" if k.lower() in mask_params else v) for k, v in pairs]
    return urlencode(masked)


def _route_template(scope: Scope) -> str | None:
    route = scope.get("route")
    path = getattr(route, "path", None)
    return str(path) if path else None


def _user_id(scope: Scope) -> str | None:
    state = scope.get("state")
    if not isinstance(state, dict):
        # Starlette State object
        user = getattr(state, "user", None) if state is not None else None
    else:
        user = state.get("user")
    if user is None:
        return None
    sub = getattr(user, "sub", None)
    return str(sub) if sub is not None else None


class RequestContextMiddleware:
    """Generate/propagate request ID, bind OTel + request context to structlog,
    and emit one structured access-log line per request.

    Pure-ASGI implementation (no ``BaseHTTPMiddleware``) so it does not break
    streaming responses or spawn an extra task per request.

    Access-log fields (ECS-inspired): ``request_id``, ``status_code``,
    ``duration_ms``, ``http.request.method``, ``url.path``, ``http.route``,
    ``url.query`` (maskable), ``client.address``, ``user_agent.original``,
    ``user.id`` (when ``request.state.user`` is set by auth), plus trace/span IDs.
    """

    def __init__(
        self,
        app: ASGIApp,
        header_name: str = REQUEST_ID_HEADER,
        *,
        mask_query_params: frozenset[str] | set[str] | None = None,
    ) -> None:
        self.app = app
        self.header_name = header_name
        self.mask_query_params = frozenset(mask_query_params or DEFAULT_MASK_QUERY_PARAMS)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = headers.get(self.header_name) or str(uuid.uuid4())
        path = scope.get("path", "")
        method = scope.get("method", "")
        query = _mask_query(scope.get("query_string", b""), self.mask_query_params)
        client_addr = _client_address(scope, headers)
        user_agent = headers.get("user-agent")

        structlog.contextvars.clear_contextvars()
        bind: dict[str, Any] = {
            "request_id": request_id,
            "http": {"request": {"method": method, "id": request_id}},
            "url": {"path": path},
        }
        if query is not None:
            bind["url"]["query"] = query
        if client_addr:
            bind["client"] = {"address": client_addr}
        if user_agent:
            bind["user_agent"] = {"original": user_agent}

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            bind["trace"] = {"id": format(ctx.trace_id, "032x")}
            bind["span"] = {"id": format(ctx.span_id, "016x")}
            span.set_attribute("http.request.id", request_id)
        structlog.contextvars.bind_contextvars(**bind)

        scope.setdefault("state", {})["request_id"] = request_id

        status_code = 500
        start = time.perf_counter()
        logger = structlog.get_logger("access")

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = MutableHeaders(scope=message)
                response_headers[self.header_name] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception("request_failed", duration_ms=round(duration_ms, 2))
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        route = _route_template(scope)
        user_id = _user_id(scope)
        log_extra: dict[str, Any] = {
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
        }
        if route:
            log_extra["http"] = {
                **bind.get("http", {}),
                "route": route,
            }
        if user_id:
            log_extra["user"] = {"id": user_id}
        logger.info("request_completed", **log_extra)
