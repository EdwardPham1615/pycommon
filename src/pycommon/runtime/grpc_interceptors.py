"""gRPC interceptors that propagate X-Request-ID across service boundaries."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import grpc
import structlog
from grpc import aio

from pycommon.logging import current_request_id

REQUEST_ID_METADATA_KEY = "x-request-id"


def _metadata_value(metadata: Any, key: str) -> str | None:
    if metadata is None:
        return None
    for k, v in metadata:
        if k.lower() == key:
            return v if isinstance(v, str) else str(v)
    return None


class RequestIdServerInterceptor(aio.ServerInterceptor):  # type: ignore[misc]
    """Read ``x-request-id`` from inbound metadata (or generate one) and bind it
    to structlog contextvars so all logs / outbound calls share the same ID.
    """

    async def intercept_service(
        self,
        continuation: Callable[[grpc.HandlerCallDetails], Awaitable[Any]],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> Any:
        request_id = _metadata_value(
            handler_call_details.invocation_metadata, REQUEST_ID_METADATA_KEY
        ) or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)
        return await continuation(handler_call_details)


def _with_request_id(client_call_details: aio.ClientCallDetails) -> aio.ClientCallDetails:
    """Return call details carrying the current request ID, if there is one."""
    request_id = current_request_id()
    if not request_id:
        return client_call_details

    metadata = list(client_call_details.metadata or [])
    if any(k.lower() == REQUEST_ID_METADATA_KEY for k, _ in metadata):
        return client_call_details
    metadata.append((REQUEST_ID_METADATA_KEY, str(request_id)))

    return aio.ClientCallDetails(
        client_call_details.method,
        client_call_details.timeout,
        metadata,
        client_call_details.credentials,
        client_call_details.wait_for_ready,
    )


class RequestIdClientInterceptor(aio.UnaryUnaryClientInterceptor):  # type: ignore[misc]
    """Attach the current request ID (from structlog contextvars) to outbound
    gRPC metadata so downstream services can correlate.
    """

    async def intercept_unary_unary(
        self,
        continuation: Callable[[aio.ClientCallDetails, Any], Awaitable[Any]],
        client_call_details: aio.ClientCallDetails,
        request: Any,
    ) -> Any:
        return await continuation(_with_request_id(client_call_details), request)


class RequestIdUnaryStreamClientInterceptor(aio.UnaryStreamClientInterceptor):  # type: ignore[misc]
    async def intercept_unary_stream(
        self,
        continuation: Callable[[aio.ClientCallDetails, Any], Awaitable[Any]],
        client_call_details: aio.ClientCallDetails,
        request: Any,
    ) -> Any:
        return await continuation(_with_request_id(client_call_details), request)


class RequestIdStreamUnaryClientInterceptor(aio.StreamUnaryClientInterceptor):  # type: ignore[misc]
    async def intercept_stream_unary(
        self,
        continuation: Callable[[aio.ClientCallDetails, Any], Awaitable[Any]],
        client_call_details: aio.ClientCallDetails,
        request_iterator: Any,
    ) -> Any:
        return await continuation(_with_request_id(client_call_details), request_iterator)


class RequestIdStreamStreamClientInterceptor(aio.StreamStreamClientInterceptor):  # type: ignore[misc]
    async def intercept_stream_stream(
        self,
        continuation: Callable[[aio.ClientCallDetails, Any], Awaitable[Any]],
        client_call_details: aio.ClientCallDetails,
        request_iterator: Any,
    ) -> Any:
        return await continuation(_with_request_id(client_call_details), request_iterator)


def request_id_server_interceptors() -> list[aio.ServerInterceptor]:
    return [RequestIdServerInterceptor()]


def request_id_client_interceptors() -> list[aio.ClientInterceptor]:
    """All four RPC shapes.

    gRPC dispatches to a different interceptor class per shape, so registering
    only the unary-unary one silently dropped the request ID from every
    streaming call.
    """
    return [
        RequestIdClientInterceptor(),
        RequestIdUnaryStreamClientInterceptor(),
        RequestIdStreamUnaryClientInterceptor(),
        RequestIdStreamStreamClientInterceptor(),
    ]
