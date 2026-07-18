"""Reusable server runtime: FastAPI shell, lifespan composition, gRPC, uvicorn."""

from pycommon.runtime.app import create_base_app
from pycommon.runtime.grpc import GrpcServer, ServicerRegistrar, default_otel_interceptors
from pycommon.runtime.grpc_client import GrpcChannelPool
from pycommon.runtime.grpc_interceptors import (
    RequestIdClientInterceptor,
    RequestIdServerInterceptor,
    request_id_client_interceptors,
    request_id_server_interceptors,
)
from pycommon.runtime.lifespan import LifespanResource, build_lifespan
from pycommon.runtime.uvicorn import run_uvicorn

__all__ = [
    "GrpcChannelPool",
    "GrpcServer",
    "LifespanResource",
    "RequestIdClientInterceptor",
    "RequestIdServerInterceptor",
    "ServicerRegistrar",
    "build_lifespan",
    "create_base_app",
    "default_otel_interceptors",
    "request_id_client_interceptors",
    "request_id_server_interceptors",
    "run_uvicorn",
]
