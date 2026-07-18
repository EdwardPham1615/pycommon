"""Cache layer: distributed lock and rate limiting."""

from __future__ import annotations

import pytest
from fakeredis import FakeAsyncRedis

from pycommon.cache import (
    InMemoryRateLimiter,
    LockAcquireError,
    RedisRateLimiter,
    redis_lock,
)


@pytest.fixture
async def redis() -> FakeAsyncRedis:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


async def test_lock_acquire_and_release(redis: FakeAsyncRedis) -> None:
    async with redis_lock(redis, "job:1", ttl_seconds=5):
        assert await redis.exists("lock:job:1")
    assert not await redis.exists("lock:job:1")


async def test_lock_contention_raises(redis: FakeAsyncRedis) -> None:
    async with redis_lock(redis, "job:1", ttl_seconds=5):
        with pytest.raises(LockAcquireError):
            async with redis_lock(redis, "job:1", ttl_seconds=5, blocking_timeout=0.05):
                pass


async def test_lock_released_on_error(redis: FakeAsyncRedis) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        async with redis_lock(redis, "job:1", ttl_seconds=5):
            raise RuntimeError("boom")
    assert not await redis.exists("lock:job:1")


async def test_redis_rate_limiter_fixed_window(redis: FakeAsyncRedis) -> None:
    limiter = RedisRateLimiter(client=redis)

    for i in range(3):
        result = await limiter.hit("user-1", times=3, seconds=60)
        assert result.allowed, f"hit {i + 1} should be allowed"

    result = await limiter.hit("user-1", times=3, seconds=60)
    assert not result.allowed
    assert result.remaining == 0

    # Different key has its own window.
    other = await limiter.hit("user-2", times=3, seconds=60)
    assert other.allowed


async def test_in_memory_rate_limiter() -> None:
    limiter = InMemoryRateLimiter()
    assert (await limiter.hit("k", times=2, seconds=60)).allowed
    assert (await limiter.hit("k", times=2, seconds=60)).allowed
    assert not (await limiter.hit("k", times=2, seconds=60)).allowed


async def test_rate_limit_dependency() -> None:
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from pycommon.http.middleware.rate_limit import build_rate_limit_dep

    limiter = InMemoryRateLimiter()
    dep = build_rate_limit_dep(limiter, times=2, seconds=60)

    app = FastAPI()

    @app.get("/limited", dependencies=[Depends(dep)])
    async def limited() -> dict[str, str]:
        return {"ok": "yes"}

    client = TestClient(app)
    assert client.get("/limited").status_code == 200
    assert client.get("/limited").status_code == 200
    resp = client.get("/limited")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
