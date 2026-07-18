"""Redis async client factory."""

from __future__ import annotations

from redis.asyncio import ConnectionPool, Redis

from pycommon.config import RedisSettings


def create_redis(settings: RedisSettings, *, decode_responses: bool = True) -> Redis:
    """Create a Redis client from settings.

    Keep one client per app alive for the process lifetime (e.g. via a
    ``LifespanResource`` that calls ``client.aclose()`` on shutdown).
    """
    pool = ConnectionPool.from_url(
        settings.url,
        max_connections=settings.max_connections,
        decode_responses=decode_responses,
    )
    return Redis(connection_pool=pool)
