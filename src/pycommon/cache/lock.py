"""Distributed lock on Redis with optional auto-extend.

Built on redis-py's atomic ``Lock`` (token-checked release/extend via Lua),
with an optional background task that keeps extending the TTL while the
protected block is still running.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis
from redis.exceptions import LockError

from pycommon.logging import get_logger

logger = get_logger(__name__)

LOCK_KEY_PREFIX = "lock:"


class LockAcquireError(Exception):
    """Raised when the lock could not be acquired within ``blocking_timeout``."""


async def _auto_extend_loop(lock: object, ttl_seconds: float, key: str) -> None:
    interval = ttl_seconds / 2
    while True:
        await asyncio.sleep(interval)
        try:
            await lock.extend(ttl_seconds, replace_ttl=True)  # type: ignore[attr-defined]
        except LockError:
            logger.warning("lock_extend_failed", key=key)
            return


@asynccontextmanager
async def redis_lock(
    client: Redis,
    key: str,
    *,
    ttl_seconds: float = 30.0,
    blocking: bool = True,
    blocking_timeout: float | None = 10.0,
    auto_extend: bool = False,
) -> AsyncIterator[None]:
    """Hold a distributed lock while the block runs.

    - ``ttl_seconds``: lock TTL (protects against dead holders).
    - ``blocking`` / ``blocking_timeout``: how long to wait for acquisition;
      raises :class:`LockAcquireError` when it cannot be acquired.
    - ``auto_extend``: keep extending the TTL every ``ttl_seconds / 2``
      while the block is still running (for work of unpredictable duration).

    Usage::

        async with redis_lock(redis, f"order:{order_id}", ttl_seconds=30):
            ...
    """
    lock = client.lock(
        f"{LOCK_KEY_PREFIX}{key}",
        timeout=ttl_seconds,
        blocking=blocking,
        blocking_timeout=blocking_timeout,
    )
    acquired = await lock.acquire()
    if not acquired:
        raise LockAcquireError(f"Could not acquire lock {key!r}")

    extend_task: asyncio.Task[None] | None = None
    if auto_extend:
        extend_task = asyncio.create_task(_auto_extend_loop(lock, ttl_seconds, key))

    try:
        yield
    finally:
        if extend_task is not None:
            extend_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await extend_task
        try:
            await lock.release()
        except LockError:
            # TTL expired before release — the work outlived the lock.
            logger.warning("lock_already_released", key=key)
