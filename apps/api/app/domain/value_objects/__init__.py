"""Domain value objects — immutable, self-validating types.

Value objects have no identity; two instances with the same value are equal.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SentimentScore:
    """Sentiment score in the range [-1.0, 1.0]."""

    value: float

    def __post_init__(self) -> None:
        """Validate that the score is within [-1.0, 1.0]."""
        if not -1.0 <= self.value <= 1.0:
            raise ValueError(f"SentimentScore must be in [-1.0, 1.0], got {self.value}")

    @property
    def label(self) -> str:
        """Derive a human-readable label from the numeric score."""
        if self.value > 0.3:
            return "positive"
        if self.value < -0.3:
            return "negative"
        return "neutral"


@dataclass(frozen=True)
class ConfidenceScore:
    """Confidence score in the range [0.0, 1.0]."""

    value: float

    def __post_init__(self) -> None:
        """Validate that the score is within [0.0, 1.0]."""
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"ConfidenceScore must be in [0.0, 1.0], got {self.value}")

    @property
    def needs_human_review(self) -> bool:
        """Return True if confidence is below the gating threshold."""
        return self.value < 0.75


@dataclass(frozen=True)
class RiskScore:
    """Normalised risk score mapped to a risk level label."""

    value: float

    def __post_init__(self) -> None:
        """Validate that the score is within [0.0, 1.0]."""
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"RiskScore must be in [0.0, 1.0], got {self.value}")

    @property
    def level(self) -> str:
        """Derive a risk level label from the numeric score."""
        if self.value >= 0.75:
            return "critical"
        if self.value >= 0.5:
            return "high"
        if self.value >= 0.25:
            return "medium"
        return "low"


@dataclass(frozen=True)
class Cursor:
    """Opaque pagination cursor wrapping an encoded offset or timestamp."""

    value: str

    def __post_init__(self) -> None:
        """Validate that cursor is non-empty."""
        if not self.value:
            raise ValueError("Cursor value must not be empty")
