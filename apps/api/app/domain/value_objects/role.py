"""RBAC role hierarchy for workspace members."""

from __future__ import annotations

from enum import IntEnum


class Role(IntEnum):
    """Ordered role hierarchy — higher value = more permissions.

    Comparison: Role.admin >= Role.analyst evaluates True.
    """

    viewer = 1
    analyst = 2
    admin = 3
    owner = 4

    @classmethod
    def from_str(cls, value: str) -> Role:
        try:
            return cls[value]
        except KeyError as exc:
            raise ValueError(f"Unknown role: {value!r}") from exc
