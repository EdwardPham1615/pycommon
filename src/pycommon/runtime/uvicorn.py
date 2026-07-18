"""Reusable uvicorn entrypoint wrapper."""

from __future__ import annotations

import uvicorn


def run_uvicorn(
    app_import_string: str,
    *,
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = False,
    log_config: dict | None = None,
    **kwargs: object,
) -> None:
    """Run uvicorn with structlog-friendly defaults (log_config=None disables uvicorn's logging)."""
    uvicorn.run(
        app_import_string,
        host=host,
        port=port,
        reload=reload,
        log_config=log_config,
        **kwargs,  # type: ignore[arg-type]
    )
