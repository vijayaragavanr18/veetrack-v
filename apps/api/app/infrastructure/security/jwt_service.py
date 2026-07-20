"""JWT access + refresh token issuance and verification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt  # type: ignore[import-untyped]

from app.domain.exceptions import UnauthorizedError
from app.domain.interfaces.security import TokenService

# Token type claim used to distinguish access from refresh tokens
_ACCESS_TYPE = "access"
_REFRESH_TYPE = "refresh"
_ALGORITHM = "HS256"

ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 7


class JwtService:
    def __init__(self, secret: str) -> None:
        self._secret = secret

    # ------------------------------------------------------------------
    # Issue
    # ------------------------------------------------------------------

    def create_access_token(self, user_id: str, workspace_id: str, role: str) -> str:
        return self._encode(
            {
                "sub": user_id,
                "wid": workspace_id,
                "role": role,
                "type": _ACCESS_TYPE,
            },
            expires_delta=timedelta(minutes=ACCESS_TOKEN_MINUTES),
        )

    def create_refresh_token(self, user_id: str) -> str:
        return self._encode(
            {"sub": user_id, "type": _REFRESH_TYPE},
            expires_delta=timedelta(days=REFRESH_TOKEN_DAYS),
        )

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------

    def decode_access_token(self, token: str) -> dict[str, Any]:
        """Decode and validate an access token; raise UnauthorizedError on any failure."""
        payload = self._decode(token)
        if payload.get("type") != _ACCESS_TYPE:
            raise UnauthorizedError("Invalid token type")
        return payload

    def decode_refresh_token(self, token: str) -> str:
        """Return the user_id from a valid refresh token."""
        payload = self._decode(token)
        if payload.get("type") != _REFRESH_TYPE:
            raise UnauthorizedError("Invalid token type")
        sub = payload.get("sub")
        if not isinstance(sub, str):
            raise UnauthorizedError("Malformed token")
        return sub

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _encode(self, claims: dict[str, Any], *, expires_delta: timedelta) -> str:
        payload = {
            **claims,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + expires_delta,
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)  # type: ignore[no-any-return]

    def _decode(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(token, self._secret, algorithms=[_ALGORITHM])  # type: ignore[no-any-return]
        except JWTError as exc:
            raise UnauthorizedError("Invalid or expired token") from exc


# Static Protocol assertion.
_: TokenService = JwtService.__new__(JwtService)
