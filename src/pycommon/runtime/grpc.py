"""Generic gRPC aio server lifecycle — no service-specific stubs."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from grpc import aio

from pycommon.logging import get_logger

logger = get_logger(__name__)

ServicerRegistrar = Callable[[aio.Server], None]


def default_otel_interceptors() -> list[aio.ServerInterceptor]:
    """Return OTel aio server interceptors when the instrumentation package is available."""
    try:
        from opentelemetry.instrumentation.grpc import (  # type: ignore[attr-defined]
            aio_server_interceptor,
        )

        return [aio_server_interceptor()]
    except Exception:
        return []


class GrpcServer:
    """Reusable gRPC aio server. Consumers pass registrars for their own servicers."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        registrars: Sequence[ServicerRegistrar],
        enabled: bool = True,
        interceptors: Sequence[aio.ServerInterceptor] | None = None,
        use_otel_interceptor: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._registrars = list(registrars)
        self._enabled = enabled
        self._interceptors: list[aio.ServerInterceptor] = list(interceptors or [])
        if use_otel_interceptor and not self._interceptors:
            self._interceptors.extend(default_otel_interceptors())
        self._server: aio.Server | None = None

    @property
    def server(self) -> aio.Server | None:
        return self._server

    async def start(self) -> None:
        if not self._enabled:
            logger.info("grpc_server_disabled")
            return

        kwargs: dict = {}
        if self._interceptors:
            kwargs["interceptors"] = self._interceptors

        server = aio.server(**kwargs)
        for registrar in self._registrars:
            registrar(server)

        listen = f"{self._host}:{self._port}"
        server.add_insecure_port(listen)
        await server.start()
        self._server = server
        logger.info("grpc_server_started", address=listen)

    async def stop(self, grace: float = 5.0) -> None:
        if self._server is None:
            return
        await self._server.stop(grace)
        self._server = None
        logger.info("grpc_server_stopped")
