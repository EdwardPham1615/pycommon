"""Rate limiting primitives (fixed window) with Redis and in-memory backends."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

from redis.asyncio import Redis

_INCR_WITH_TTL = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('PTTL', KEYS[1])
return {count, ttl}
"""


@dataclass(slots=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_after_seconds: float


class RateLimiter(Protocol):
    async def hit(self, key: str, *, times: int, seconds: float) -> RateLimitResult:
        """Register one hit for ``key``; report whether it is within ``times`` per ``seconds``."""
        ...


@dataclass
class RedisRateLimiter:
    """Fixed-window limiter shared across all instances (one Redis counter per key)."""

    client: Redis
    prefix: str = "rate_limit"

    async def hit(self, key: str, *, times: int, seconds: float) -> RateLimitResult:
        window_ms = int(seconds * 1000)
        count, ttl_ms = await self.client.eval(_INCR_WITH_TTL, 1, f"{self.prefix}:{key}", window_ms)
        reset_after = (ttl_ms / 1000) if ttl_ms and ttl_ms > 0 else seconds
        return RateLimitResult(
            allowed=count <= times,
            remaining=max(times - count, 0),
            reset_after_seconds=reset_after,
        )


@dataclass
class InMemoryRateLimiter:
    """Per-process fixed-window limiter for dev and tests (not shared across instances)."""

    _windows: dict[str, tuple[float, int]] = field(default_factory=dict)

    async def hit(self, key: str, *, times: int, seconds: float) -> RateLimitResult:
        now = time.monotonic()
        window_start, count = self._windows.get(key, (now, 0))
        if now - window_start >= seconds:
            window_start, count = now, 0
        count += 1
        self._windows[key] = (window_start, count)
        return RateLimitResult(
            allowed=count <= times,
            remaining=max(times - count, 0),
            reset_after_seconds=max(seconds - (now - window_start), 0.0),
        )
