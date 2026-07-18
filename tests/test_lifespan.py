"""Lifespan composer: startup order, reverse shutdown, rollback on failure."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from pycommon.runtime import LifespanResource, build_lifespan


def _resource(name: str, events: list[str], *, fail_startup: bool = False) -> LifespanResource:
    async def startup() -> None:
        if fail_startup:
            raise RuntimeError(f"{name} failed")
        events.append(f"start:{name}")

    async def shutdown() -> None:
        events.append(f"stop:{name}")

    return LifespanResource(name=name, startup=startup, shutdown=shutdown)


async def test_startup_in_order_shutdown_reversed() -> None:
    events: list[str] = []
    lifespan = build_lifespan([_resource("db", events), _resource("cache", events)])

    async with lifespan(FastAPI()):
        assert events == ["start:db", "start:cache"]

    assert events == ["start:db", "start:cache", "stop:cache", "stop:db"]


async def test_startup_failure_unwinds_started_resources() -> None:
    events: list[str] = []
    lifespan = build_lifespan(
        [
            _resource("db", events),
            _resource("broken", events, fail_startup=True),
            _resource("never", events),
        ]
    )

    with pytest.raises(RuntimeError, match="broken failed"):
        async with lifespan(FastAPI()):
            pass

    # Only the successfully started resource is stopped; "never" is untouched.
    assert events == ["start:db", "stop:db"]


async def test_shutdown_error_does_not_block_others() -> None:
    events: list[str] = []

    async def failing_shutdown() -> None:
        raise RuntimeError("boom")

    bad = LifespanResource(
        name="bad",
        startup=_resource("unused", []).startup,
        shutdown=failing_shutdown,
    )
    lifespan = build_lifespan([_resource("db", events), bad])

    async with lifespan(FastAPI()):
        pass

    assert "stop:db" in events
