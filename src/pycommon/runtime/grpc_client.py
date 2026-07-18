"""Generic gRPC aio channel pool for service-to-service calls.

Unlike a per-call ``grpc.aio.insecure_channel(...)``, channels here are created
once per target and reused (a gRPC channel multiplexes many concurrent RPCs
over shared HTTP/2 connections). Consumers wrap the channel with their own
generated stubs — this module knows nothing about specific services.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import grpc
from grpc import aio

from pycommon.logging import get_logger
from pycommon.runtime.grpc_interceptors import request_id_client_interceptors

logger = get_logger(__name__)

DEFAULT_MAX_MESSAGE_MB = 32


class GrpcChannelPool:
    """Caches one channel per target. Close via :meth:`aclose` on app shutdown.

    Usage::

        pool = GrpcChannelPool()
        channel = await pool.get_channel("user-service:50051")
        stub = user_pb2_grpc.UserServiceStub(channel)
    """

    def __init__(
        self,
        *,
        max_message_mb: int = DEFAULT_MAX_MESSAGE_MB,
        default_options: Sequence[tuple[str, object]] | None = None,
        interceptors: Sequence[aio.ClientInterceptor] | None = None,
        use_request_id_interceptor: bool = True,
    ) -> None:
        max_bytes = max_message_mb * 1024 * 1024
        self._options: list[tuple[str, object]] = [
            ("grpc.max_send_message_length", max_bytes),
            ("grpc.max_receive_message_length", max_bytes),
            *(default_options or []),
        ]
        self._interceptors: list[aio.ClientInterceptor] = []
        if use_request_id_interceptor:
            self._interceptors.extend(request_id_client_interceptors())
        self._interceptors.extend(interceptors or [])
        self._channels: dict[str, aio.Channel] = {}
        self._lock = asyncio.Lock()

    async def get_channel(
        self,
        target: str,
        *,
        credentials: grpc.ChannelCredentials | None = None,
    ) -> aio.Channel:
        """Return a cached channel for ``target``, creating it on first use."""
        async with self._lock:
            channel = self._channels.get(target)
            if channel is None:
                if credentials is not None:
                    channel = aio.secure_channel(
                        target,
                        credentials,
                        options=self._options,
                        interceptors=self._interceptors or None,
                    )
                else:
                    channel = aio.insecure_channel(
                        target,
                        options=self._options,
                        interceptors=self._interceptors or None,
                    )
                self._channels[target] = channel
                logger.info("grpc_channel_created", target=target, secure=credentials is not None)
            return channel

    async def aclose(self) -> None:
        """Close all pooled channels (call from app shutdown/lifespan)."""
        async with self._lock:
            for target, channel in self._channels.items():
                try:
                    await channel.close()
                except Exception:
                    logger.exception("grpc_channel_close_failed", target=target)
            self._channels.clear()
