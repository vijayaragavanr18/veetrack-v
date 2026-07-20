"""Unit tests for Role value object hierarchy."""

from __future__ import annotations

import pytest

from app.domain.value_objects.role import Role


def test_ordering() -> None:
    assert Role.viewer < Role.analyst < Role.admin < Role.owner


def test_from_str_round_trips() -> None:
    for name in ("viewer", "analyst", "admin", "owner"):
        assert Role.from_str(name).name == name


def test_from_str_invalid() -> None:
    with pytest.raises(ValueError, match="Unknown role"):
        Role.from_str("superuser")


def test_min_role_satisfied() -> None:
    assert Role.from_str("admin") >= Role.analyst


def test_min_role_violated() -> None:
    assert not (Role.from_str("viewer") >= Role.admin)
