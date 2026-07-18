"""Keycloak OIDC JWT validation and RBAC helpers."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

import anyio.to_thread
import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError
from pydantic import BaseModel, Field

from pycommon.config import KeycloakSettings

_bearer = HTTPBearer(auto_error=False)


class TokenClaims(BaseModel):
    sub: str
    email: str | None = None
    preferred_username: str | None = None
    name: str | None = None
    realm_roles: list[str] = Field(default_factory=list)
    client_roles: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


def _unauthorized(detail: str = "Invalid or expired token") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


@dataclass
class KeycloakTokenValidator:
    settings: KeycloakSettings
    _jwks_client: PyJWKClient | None = field(default=None, init=False, repr=False)
    _jwks_fetched_at: float = field(default=0.0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def _get_jwks_client(self, *, force_refresh: bool = False) -> PyJWKClient:
        now = time.monotonic()
        ttl = self.settings.jwks_cache_ttl_seconds
        with self._lock:
            expired = self._jwks_client is None or (now - self._jwks_fetched_at) > ttl
            if force_refresh or expired:
                self._jwks_client = PyJWKClient(
                    self.settings.jwks_url,
                    cache_keys=True,
                    lifespan=ttl,
                )
                self._jwks_fetched_at = now
            assert self._jwks_client is not None
            return self._jwks_client

    def _decode_once(self, token: str, *, force_refresh: bool = False) -> dict[str, Any]:
        jwks = self._get_jwks_client(force_refresh=force_refresh)
        signing_key = jwks.get_signing_key_from_jwt(token)
        audience = self.settings.audience or self.settings.client_id
        result: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=self.settings.algorithms,
            audience=audience if self.settings.verify_aud else None,
            issuer=self.settings.issuer,
            options={"verify_aud": self.settings.verify_aud},
        )
        return result

    def decode(self, token: str) -> TokenClaims:
        """Validate a bearer token and map its payload to :class:`TokenClaims`.

        Note: JWKS fetches use blocking I/O — from async code call
        :meth:`decode_async` instead.
        """
        try:
            payload = self._decode_once(token)
        except PyJWKClientError:
            # Unknown kid — likely key rotation. Refresh JWKS exactly once.
            # Other JWT errors (expired, bad audience/signature) must NOT
            # trigger a refetch, or garbage tokens would hammer Keycloak.
            try:
                payload = self._decode_once(token, force_refresh=True)
            except jwt.PyJWTError as retry_exc:
                raise _unauthorized() from retry_exc
        except jwt.PyJWTError as exc:
            raise _unauthorized() from exc

        realm_access = payload.get("realm_access") or {}
        resource_access = payload.get("resource_access") or {}
        client_roles = (resource_access.get(self.settings.client_id) or {}).get("roles") or []

        return TokenClaims(
            sub=payload["sub"],
            email=payload.get("email"),
            preferred_username=payload.get("preferred_username"),
            name=payload.get("name"),
            realm_roles=list(realm_access.get("roles") or []),
            client_roles=list(client_roles),
            raw=payload,
        )

    async def decode_async(self, token: str) -> TokenClaims:
        """Like :meth:`decode` but in a worker thread so JWKS fetches never block the event loop."""
        return await anyio.to_thread.run_sync(self.decode, token)

    async def fetch_openid_config(self) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(self.settings.openid_config_url, timeout=10.0)
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result


def create_auth_deps(validator: KeycloakTokenValidator) -> tuple[Any, Any]:
    """Return (get_current_user, require_roles) FastAPI dependencies bound to validator."""

    async def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> TokenClaims:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise _unauthorized("Not authenticated")
        return await validator.decode_async(credentials.credentials)

    def require_roles(*roles: str, any_of: bool = True) -> Any:
        async def _checker(user: TokenClaims = Depends(get_current_user)) -> TokenClaims:
            user_roles = set(user.realm_roles) | set(user.client_roles)
            required = set(roles)
            ok = bool(user_roles & required) if any_of else required.issubset(user_roles)
            if not ok:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions",
                )
            return user

        return _checker

    return get_current_user, require_roles
