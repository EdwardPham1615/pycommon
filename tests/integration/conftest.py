"""Integration tests against a real Redis.

Skipped unless ``REDIS_TEST_URL`` is set, so the default `pytest` run stays
offline and fast. CI sets it to a service container; locally, point it at any
throwaway Redis::

    REDIS_TEST_URL=redis://localhost:6379/15 uv run pytest tests/integration

The URL is read from the environment rather than hardcoded because a developer's
Redis may require a password, and a credential does not belong in the tree.

These exist because the rest of the suite runs on ``fakeredis``, which does not
faithfully model the three things this module actually depends on: Lua script
execution, server-side ``TIME``, and real key expiry. A green fakeredis test
proves the Python is coherent, not that the script runs on Redis.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import redis.asyncio as redis_asyncio
from redis.asyncio import Redis


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    """A client on a flushed database, or a skip when no Redis was provided.

    The skip lives in the fixture rather than a module-level ``pytestmark``
    because a ``pytestmark`` in conftest.py is silently ignored — the tests then
    run and fail on a null URL instead of skipping.

    Flushes on entry rather than exit so a failed run leaves its keys behind to
    inspect.
    """
    url = os.getenv("REDIS_TEST_URL")
    if not url:
        pytest.skip("REDIS_TEST_URL is not set; skipping real-Redis integration tests")
    client: Redis = redis_asyncio.from_url(url, decode_responses=False)
    await client.flushdb()
    try:
        yield client
    finally:
        await client.aclose()
