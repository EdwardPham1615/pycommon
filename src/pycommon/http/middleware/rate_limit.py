"""FastAPI dependency for per-route rate limiting.

Requires a limiter from ``pycommon.cache`` (Redis-backed for multi-instance
deployments, in-memory for dev/tests).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request, status

from pycommon.cache.rate_limit import RateLimiter

KeyFunc = Callable[[Request], str | None]


def _default_key(request: Request) -> str | None:
    """Key by authenticated user when available, else by client IP; scoped per route."""
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    user = getattr(request.state, "user", None)
    identity = getattr(user, "sub", None)
    if identity is None:
        identity = request.client.host if request.client else None
    if identity is None:
        return None
    return f"{request.method}:{path}:{identity}"


def build_rate_limit_dep(
    limiter: RateLimiter,
    *,
    times: int,
    seconds: float,
    key_func: KeyFunc | None = None,
) -> Callable[[Request], Any]:
    """Build a dependency enforcing ``times`` requests per ``seconds`` window.

    Usage::

        limiter = RedisRateLimiter(redis)
        rate_limited = build_rate_limit_dep(limiter, times=10, seconds=1)

        @router.get("/items", dependencies=[Depends(rate_limited)])
        async def list_items(): ...
    """
    get_key = key_func or _default_key

    async def dependency(request: Request) -> None:
        key = get_key(request)
        if key is None:
            return
        result = await limiter.hit(key, times=times, seconds=seconds)
        if not result.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(math.ceil(result.reset_after_seconds))},
            )

    return dependency
