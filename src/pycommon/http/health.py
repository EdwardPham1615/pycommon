"""Liveness/readiness endpoints with pluggable dependency checks (k8s probes)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

import anyio
from fastapi import APIRouter, Response, status

from pycommon.logging import get_logger

logger = get_logger(__name__)

CheckFn = Callable[[], Awaitable[None]]


@dataclass(slots=True)
class HealthCheck:
    """One readiness check. ``check`` must raise on failure (e.g. ping the DB)."""

    name: str
    check: CheckFn
    timeout_seconds: float = 5.0


async def _run_check(hc: HealthCheck) -> str | None:
    """Return an error message if the check failed, else None."""
    try:
        with anyio.fail_after(hc.timeout_seconds):
            await hc.check()
        return None
    except TimeoutError:
        return "timeout"
    except Exception as exc:
        return str(exc) or type(exc).__name__


def build_health_router(
    checks: Sequence[HealthCheck] = (),
    *,
    prefix: str = "/health",
) -> APIRouter:
    """Router with ``{prefix}/live`` (always 200) and ``{prefix}/ready`` (runs checks)."""
    router = APIRouter(prefix=prefix, tags=["health"])

    @router.get("/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/ready")
    async def ready(response: Response) -> dict[str, object]:
        results: dict[str, str] = {}
        failed = False
        for hc in checks:
            error = await _run_check(hc)
            if error is None:
                results[hc.name] = "ok"
            else:
                failed = True
                results[hc.name] = f"failed: {error}"
                logger.warning("readiness_check_failed", check=hc.name, error=error)

        if failed:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded" if failed else "ok", "checks": results}

    return router
