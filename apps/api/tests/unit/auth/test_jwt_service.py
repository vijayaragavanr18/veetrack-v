"""Unit tests for JwtService — no DB or Redis required."""

from __future__ import annotations

import pytest

from app.domain.exceptions import UnauthorizedError
from app.infrastructure.security.jwt_service import JwtService

_SECRET = "unit-test-secret-long-enough-for-hs256-algorithm"
_SVC = JwtService(_SECRET)


def test_access_token_roundtrip() -> None:
    token = _SVC.create_access_token("u1", "w1", "analyst")
    payload = _SVC.decode_access_token(token)
    assert payload["sub"] == "u1"
    assert payload["wid"] == "w1"
    assert payload["role"] == "analyst"
    assert payload["type"] == "access"


def test_refresh_token_roundtrip() -> None:
    token = _SVC.create_refresh_token("u2")
    user_id = _SVC.decode_refresh_token(token)
    assert user_id == "u2"


def test_wrong_token_type_rejected_for_access() -> None:
    refresh = _SVC.create_refresh_token("u3")
    with pytest.raises(UnauthorizedError, match="Invalid token type"):
        _SVC.decode_access_token(refresh)


def test_wrong_token_type_rejected_for_refresh() -> None:
    access = _SVC.create_access_token("u4", "w4", "viewer")
    with pytest.raises(UnauthorizedError, match="Invalid token type"):
        _SVC.decode_refresh_token(access)


def test_tampered_token_rejected() -> None:
    token = _SVC.create_access_token("u5", "w5", "owner")
    tampered = token[:-4] + "XXXX"
    with pytest.raises(UnauthorizedError):
        _SVC.decode_access_token(tampered)


def test_wrong_secret_rejected() -> None:
    token = _SVC.create_access_token("u6", "w6", "viewer")
    other_svc = JwtService("completely-different-secret-that-is-long-enough")
    with pytest.raises(UnauthorizedError):
        other_svc.decode_access_token(token)
