"""Domain-level exceptions.

These are the only exception types that cross layer boundaries.
Infrastructure and application code raise these; the API layer maps them to HTTP responses.
"""


class DomainError(Exception):
    """Base class for all domain exceptions."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    """Raised when a requested resource does not exist."""


class ConflictError(DomainError):
    """Raised when an operation would violate a uniqueness constraint."""


class ValidationError(DomainError):
    """Raised when domain invariants are violated."""


class UnauthorizedError(DomainError):
    """Raised when the caller is not authenticated (missing/invalid credentials)."""


class ForbiddenError(DomainError):
    """Raised when the caller is authenticated but lacks the required role."""


class ServiceUnavailableError(DomainError):
    """Raised when a required downstream service (cache, LLM, connector) is unreachable."""
