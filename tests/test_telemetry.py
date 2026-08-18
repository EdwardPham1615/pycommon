"""setup_telemetry / shutdown_telemetry control flow.

These exercise the wiring without installing a real SDK pipeline: the tracer
provider is process-global, and a test that sets it for real would leak into
every other test in the run.
"""

from __future__ import annotations

from typing import Any

import pytest

import pycommon.telemetry as tel


@pytest.fixture(autouse=True)
def _reset_provider() -> Any:
    original = tel._provider
    yield
    tel._provider = original


def test_disabled_sets_up_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """``enabled=False`` must be inert — no provider, and no metrics pipeline
    either. A service that opts out should not open exporter connections."""
    called: list[str] = []
    monkeypatch.setattr(tel, "setup_metrics", lambda **kw: called.append("metrics"))
    monkeypatch.setattr(tel, "_instrument_libraries", lambda app: called.append("instrument"))
    tel._provider = None

    assert tel.setup_telemetry(None, service_name="svc", enabled=False) is None  # type: ignore[arg-type]
    assert called == []
    assert tel._provider is None


def test_second_call_reuses_provider_and_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reusing the provider is right — but silently ignoring new exporter settings
    would leave someone debugging why their endpoint change had no effect."""
    monkeypatch.setattr(tel, "setup_metrics", lambda **kw: None)
    monkeypatch.setattr(tel, "_instrument_libraries", lambda app: None)
    warnings: list[str] = []
    monkeypatch.setattr(tel.logger, "warning", lambda event, **kw: warnings.append(event))

    sentinel = object()
    tel._provider = sentinel  # type: ignore[assignment]

    result = tel.setup_telemetry(None, service_name="svc", otlp_endpoint="http://other:4317")  # type: ignore[arg-type]
    assert result is sentinel
    assert warnings == ["telemetry_already_initialized"]


def test_shutdown_without_provider_still_flushes_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(tel, "shutdown_metrics", lambda: called.append("metrics"))
    tel._provider = None

    tel.shutdown_telemetry()
    assert called == ["metrics"]


def test_shutdown_survives_a_failing_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shutdown runs while the process is already going down. A raising exporter
    must not stop the rest of shutdown, and must not leave a dead provider
    installed for whatever runs next."""
    monkeypatch.setattr(tel, "shutdown_metrics", lambda: None)
    logged: list[str] = []
    monkeypatch.setattr(tel.logger, "exception", lambda event, **kw: logged.append(event))

    class _Boom:
        def shutdown(self) -> None:
            raise RuntimeError("exporter is gone")

    tel._provider = _Boom()  # type: ignore[assignment]
    tel.shutdown_telemetry()

    assert logged == ["telemetry_shutdown_failed"]
    assert tel._provider is None
