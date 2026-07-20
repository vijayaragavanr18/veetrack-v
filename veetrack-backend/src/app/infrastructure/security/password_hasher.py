"""bcrypt password hashing — direct bcrypt (no passlib) for Python 3.11+ / bcrypt ≥4."""

from __future__ import annotations

import bcrypt

from app.domain.interfaces.security import PasswordHasher


class BcryptPasswordHasher:
    """Implements PasswordHasher using bcrypt directly."""

    def hash(self, plain: str) -> str:
        return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

    def verify(self, plain: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(plain.encode(), hashed.encode())
        except Exception:
            return False


# Module-level convenience functions for direct use outside DI (e.g., migrations, CLI).
def hash_password(plain: str) -> str:
    return BcryptPasswordHasher().hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return BcryptPasswordHasher().verify(plain, hashed)


# Static Protocol assertion.
_: PasswordHasher = BcryptPasswordHasher()
