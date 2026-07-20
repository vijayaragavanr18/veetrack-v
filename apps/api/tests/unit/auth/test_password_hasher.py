"""Unit tests for bcrypt password hashing."""

from __future__ import annotations

from app.infrastructure.security.password_hasher import hash_password, verify_password


def test_hash_produces_non_plain_string() -> None:
    hashed = hash_password("mysecret")
    assert hashed != "mysecret"
    assert hashed.startswith("$2b$")


def test_verify_correct_password() -> None:
    hashed = hash_password("correct")
    assert verify_password("correct", hashed) is True


def test_verify_wrong_password() -> None:
    hashed = hash_password("correct")
    assert verify_password("wrong", hashed) is False


def test_two_hashes_differ() -> None:
    """bcrypt uses a random salt — same input produces different hashes."""
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2
    assert verify_password("same", h1)
    assert verify_password("same", h2)
