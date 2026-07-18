"""Keycloak OIDC JWT validation and RBAC helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
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


@dataclass
class KeycloakTokenValidator:
    settings: KeycloakSettings
    _jwks_client: PyJWKClient | None = field(default=None, init=False, repr=False)
    _jwks_fetched_at: float = field(default=0.0, init=False, repr=False)

    def _get_jwks_client(self) -> PyJWKClient:
        now = time.monotonic()
        ttl = self.settings.jwks_cache_ttl_seconds
        if self._jwks_client is None or (now - self._jwks_fetched_at) > ttl:
            self._jwks_client = PyJWKClient(
                self.settings.jwks_url,
                cache_keys=True,
                lifespan=ttl,
            )
            self._jwks_fetched_at = now
        return self._jwks_client

    def decode(self, token: str) -> TokenClaims:
        try:
            jwks = self._get_jwks_client()
            signing_key = jwks.get_signing_key_from_jwt(token)
            options = {"verify_aud": self.settings.verify_aud}
            audience = self.settings.audience or self.settings.client_id
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=audience if self.settings.verify_aud else None,
                issuer=self.settings.issuer,
                options=options,
            )
        except jwt.PyJWTError:
            # Refresh JWKS once on unknown kid / key rotation
            self._jwks_client = None
            try:
                jwks = self._get_jwks_client()
                signing_key = jwks.get_signing_key_from_jwt(token)
                audience = self.settings.audience or self.settings.client_id
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    audience=audience if self.settings.verify_aud else None,
                    issuer=self.settings.issuer,
                    options={"verify_aud": self.settings.verify_aud},
                )
            except jwt.PyJWTError as retry_exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from retry_exc

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

    async def fetch_openid_config(self) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(self.settings.openid_config_url, timeout=10.0)
            resp.raise_for_status()
            return resp.json()


def create_auth_deps(validator: KeycloakTokenValidator) -> tuple[Any, Any]:
    """Return (get_current_user, require_roles) FastAPI dependencies bound to validator."""

    async def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> TokenClaims:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return validator.decode(credentials.credentials)

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
