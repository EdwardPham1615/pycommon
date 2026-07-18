"""Async circuit breaker (closed → open → half-open) to prevent retry storms."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self

from pycommon.errors import AppError, ErrorCode
from pycommon.logging import get_logger

logger = get_logger(__name__)


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(AppError):
    """Raised when the circuit is open and calls are short-circuited."""

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            detail,
            error_code=ErrorCode.SERVER,
            status_code=503,
            title="Circuit Open",
        )


@dataclass
class AsyncCircuitBreaker:
    """Simple three-state circuit breaker.

    - **closed**: calls pass through; failures are counted.
    - **open**: calls raise :class:`CircuitOpenError` until ``recovery_timeout`` elapses.
    - **half_open**: one probe call is allowed; success closes, failure re-opens.

    Usage::

        breaker = AsyncCircuitBreaker(failure_threshold=5, recovery_timeout=30)

        async with breaker:
            await partner_client.charge(...)

        # or
        result = await breaker.call(lambda: partner_client.charge(...))
    """

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1
    name: str = "default"

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False, repr=False)
    _failure_count: int = field(default=0, init=False, repr=False)
    _opened_at: float = field(default=0.0, init=False, repr=False)
    _half_open_calls: int = field(default=0, init=False, repr=False)

    @property
    def state(self) -> CircuitState:
        if (
            self._state is CircuitState.OPEN
            and time.monotonic() - self._opened_at >= self.recovery_timeout
        ):
            self._transition(CircuitState.HALF_OPEN)
        return self._state

    def _transition(self, new_state: CircuitState) -> None:
        if new_state is self._state:
            return
        logger.warning(
            "circuit_breaker_state_change",
            name=self.name,
            from_state=self._state.value,
            to_state=new_state.value,
        )
        self._state = new_state
        if new_state is CircuitState.OPEN:
            self._opened_at = time.monotonic()
            self._half_open_calls = 0
        elif new_state is CircuitState.HALF_OPEN:
            self._half_open_calls = 0
        elif new_state is CircuitState.CLOSED:
            self._failure_count = 0
            self._half_open_calls = 0

    def _before_call(self) -> None:
        state = self.state
        if state is CircuitState.OPEN:
            raise CircuitOpenError(f"Circuit '{self.name}' is open")
        if state is CircuitState.HALF_OPEN:
            if self._half_open_calls >= self.half_open_max_calls:
                raise CircuitOpenError(f"Circuit '{self.name}' is half-open (probe in flight)")
            self._half_open_calls += 1

    def _on_success(self) -> None:
        if self._state is CircuitState.HALF_OPEN:
            self._transition(CircuitState.CLOSED)
        else:
            self._failure_count = 0

    def _on_failure(self) -> None:
        if self._state is CircuitState.HALF_OPEN:
            self._transition(CircuitState.OPEN)
            return
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._transition(CircuitState.OPEN)

    async def call[T](self, fn: Callable[[], Awaitable[T]]) -> T:
        self._before_call()
        try:
            result = await fn()
        except Exception:
            self._on_failure()
            raise
        self._on_success()
        return result

    async def __aenter__(self) -> Self:
        self._before_call()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        if exc_type is None:
            self._on_success()
        else:
            self._on_failure()

    def reset(self) -> None:
        """Force the breaker back to closed (e.g. after a manual recovery)."""
        self._transition(CircuitState.CLOSED)
