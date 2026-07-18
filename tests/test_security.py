"""Security behavior: JWT decode paths, JWKS refresh policy, role mapping."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from pycommon.config import KeycloakSettings
from pycommon.security import KeycloakTokenValidator
from pycommon.testing.tokens import RsaKeyPair, generate_rsa_keypair, issue_test_token

KC = KeycloakSettings(server_url="http://kc:8080", realm="test", client_id="test-api")


@pytest.fixture(scope="module")
def keypair() -> RsaKeyPair:
    return generate_rsa_keypair()


def _validator_with_key(keypair: RsaKeyPair) -> KeycloakTokenValidator:
    """Validator whose JWKS client returns our test public key without network I/O."""
    validator = KeycloakTokenValidator(settings=KC)
    signing_key = MagicMock()
    signing_key.key = keypair.public_pem
    jwks_client = MagicMock()
    jwks_client.get_signing_key_from_jwt.return_value = signing_key
    validator._jwks_client = jwks_client
    validator._jwks_fetched_at = float("inf")  # never expires during the test
    return validator


def test_decode_valid_token(keypair: RsaKeyPair) -> None:
    token = issue_test_token(
        keypair,
        issuer=KC.issuer,
        audience=KC.client_id,
        sub="user-1",
        realm_roles=["admin"],
        client_roles={"test-api": ["orders:write"]},
    )
    claims = _validator_with_key(keypair).decode(token)
    assert claims.sub == "user-1"
    assert claims.realm_roles == ["admin"]
    assert claims.client_roles == ["orders:write"]


def test_expired_token_rejected_without_jwks_refresh(keypair: RsaKeyPair) -> None:
    """Expired tokens must 401 immediately — NOT trigger a JWKS refetch."""
    token = issue_test_token(
        keypair, issuer=KC.issuer, audience=KC.client_id, expires_in_seconds=-60
    )
    validator = _validator_with_key(keypair)
    with (
        patch.object(validator, "_get_jwks_client", wraps=validator._get_jwks_client) as spy,
        pytest.raises(HTTPException) as exc_info,
    ):
        validator.decode(token)

    assert exc_info.value.status_code == 401
    refresh_calls = [c for c in spy.call_args_list if c.kwargs.get("force_refresh")]
    assert refresh_calls == [], "expired token must not force a JWKS refresh"


def test_wrong_audience_rejected(keypair: RsaKeyPair) -> None:
    token = issue_test_token(keypair, issuer=KC.issuer, audience="other-service")
    with pytest.raises(HTTPException) as exc_info:
        _validator_with_key(keypair).decode(token)
    assert exc_info.value.status_code == 401


def test_wrong_issuer_rejected(keypair: RsaKeyPair) -> None:
    token = issue_test_token(keypair, issuer="http://evil/realms/test", audience=KC.client_id)
    with pytest.raises(HTTPException) as exc_info:
        _validator_with_key(keypair).decode(token)
    assert exc_info.value.status_code == 401


def test_unknown_kid_triggers_single_refresh(keypair: RsaKeyPair) -> None:
    """Key rotation (PyJWKClientError) refreshes JWKS exactly once, then succeeds."""
    from jwt.exceptions import PyJWKClientError

    token = issue_test_token(keypair, issuer=KC.issuer, audience=KC.client_id)
    validator = KeycloakTokenValidator(settings=KC)

    signing_key = MagicMock()
    signing_key.key = keypair.public_pem
    good_jwks = MagicMock()
    good_jwks.get_signing_key_from_jwt.return_value = signing_key
    stale_jwks = MagicMock()
    stale_jwks.get_signing_key_from_jwt.side_effect = PyJWKClientError("unknown kid")

    calls: list[bool] = []

    def fake_get(*, force_refresh: bool = False) -> Any:
        calls.append(force_refresh)
        return good_jwks if force_refresh else stale_jwks

    with patch.object(validator, "_get_jwks_client", side_effect=fake_get):
        claims = validator.decode(token)

    assert claims.sub == "test-user"
    assert calls == [False, True]


async def test_decode_async(keypair: RsaKeyPair) -> None:
    token = issue_test_token(keypair, issuer=KC.issuer, audience=KC.client_id)
    claims = await _validator_with_key(keypair).decode_async(token)
    assert claims.sub == "test-user"
