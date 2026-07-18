"""Reusable server runtime: FastAPI shell, lifespan composition, gRPC, uvicorn."""

from pycommon.runtime.app import create_base_app
from pycommon.runtime.grpc import GrpcServer, ServicerRegistrar, default_otel_interceptors
from pycommon.runtime.lifespan import LifespanResource, build_lifespan
from pycommon.runtime.uvicorn import run_uvicorn

__all__ = [
    "GrpcServer",
    "LifespanResource",
    "ServicerRegistrar",
    "build_lifespan",
    "create_base_app",
    "default_otel_interceptors",
    "run_uvicorn",
]
