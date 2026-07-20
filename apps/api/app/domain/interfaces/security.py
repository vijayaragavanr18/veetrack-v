"""Security service Protocols for the application layer.

These abstractions keep use cases free from infrastructure imports (passlib, jose).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PasswordHasher(Protocol):
    def hash(self, plain: str) -> str: ...

    def verify(self, plain: str, hashed: str) -> bool: ...


@runtime_checkable
class TokenService(Protocol):
    def create_access_token(self, user_id: str, workspace_id: str, role: str) -> str: ...

    def create_refresh_token(self, user_id: str) -> str: ...

    def decode_access_token(self, token: str) -> dict[str, Any]: ...

    def decode_refresh_token(self, token: str) -> str: ...
