"""Reusable uvicorn entrypoint wrapper."""

from __future__ import annotations

import uvicorn


def run_uvicorn(
    app_import_string: str,
    *,
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = False,
    forwarded_allow_ips: str | list[str] | None = None,
    log_config: dict[str, object] | None = None,
    **kwargs: object,
) -> None:
    """Run uvicorn with structlog-friendly defaults (log_config=None disables uvicorn's logging).

    ``forwarded_allow_ips`` lists the peers whose ``X-Forwarded-*`` headers are
    trusted. Leave it ``None`` to keep uvicorn's own resolution (the
    ``FORWARDED_ALLOW_IPS`` environment variable, else ``127.0.0.1``).

    Set it when running behind a reverse proxy. The ``127.0.0.1`` default never
    matches a Kubernetes ingress pod, so until it is set uvicorn ignores the
    proxy headers and three things quietly go wrong: ``scope["scheme"]`` stays
    ``http`` and HSTS is never emitted, and every anonymous caller shares the
    ingress address in access logs and rate-limit buckets. See "Deploying behind
    a proxy" in the README.
    """
    uvicorn.run(
        app_import_string,
        host=host,
        port=port,
        reload=reload,
        forwarded_allow_ips=forwarded_allow_ips,
        log_config=log_config,
        **kwargs,  # type: ignore[arg-type]
    )
