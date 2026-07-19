"""Structured SQL query logging via SQLAlchemy event listeners."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from pycommon.logging import get_logger

_QUERY_START_KEY = "_pycommon_query_start"
_INSTALLED_KEY = "_pycommon_query_logger"
_MAX_STATEMENT_CHARS = 2000

logger = get_logger(__name__)


def install_query_logger(
    engine: AsyncEngine,
    *,
    slow_query_threshold_ms: float = 0.0,
    log_params: bool = False,
    log: Any | None = None,
) -> AsyncEngine:
    """Attach before/after cursor listeners that emit structured query logs.

    - ``slow_query_threshold_ms == 0``: log every query at ``debug``.
    - ``slow_query_threshold_ms > 0``: log only queries at/above the threshold at ``warning``.

    Idempotent: subsequent calls on the same engine are no-ops.
    """
    sync_engine = engine.sync_engine
    if getattr(sync_engine, _INSTALLED_KEY, False):
        return engine

    bound_logger = log or logger

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        conn.info.setdefault(_QUERY_START_KEY, []).append(time.perf_counter())

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        starts: list[float] = conn.info.get(_QUERY_START_KEY, [])
        if not starts:
            return
        started = starts.pop()
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        if slow_query_threshold_ms > 0 and duration_ms < slow_query_threshold_ms:
            return

        truncated = (
            statement
            if len(statement) <= _MAX_STATEMENT_CHARS
            else statement[:_MAX_STATEMENT_CHARS] + "…"
        )
        payload: dict[str, Any] = {
            "db": {
                "statement": truncated,
                "rows_affected": cursor.rowcount if cursor.rowcount is not None else -1,
            },
            "duration_ms": duration_ms,
            "executemany": executemany,
        }
        if log_params:
            payload["db"]["params"] = parameters

        if slow_query_threshold_ms > 0:
            bound_logger.warning("slow_query", **payload)
        else:
            bound_logger.debug("db_query", **payload)

    setattr(sync_engine, _INSTALLED_KEY, True)
    return engine
