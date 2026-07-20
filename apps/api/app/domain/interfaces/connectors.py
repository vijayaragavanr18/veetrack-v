"""SourceConnector Protocol — the domain contract every source connector must satisfy.

All concrete connectors live in app.infrastructure.connectors and are the only
callers of external HTTP APIs. No connector-specific logic may leak outside that package.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.entities import QuotaStatus, RawArticle


class SourceConnector(Protocol):
    """Read-only pull interface over an external data source."""

    @property
    def source_type(self) -> str:
        """Canonical source type string, e.g. 'newsdata'."""
        ...

    async def fetch(
        self,
        query: str,
        since: datetime,
    ) -> list[RawArticle]:
        """Pull articles matching *query* published after *since*.

        Rate limiting, retries, and circuit-breaker are handled internally.
        Raises ServiceUnavailableError if the circuit is open or quota is exhausted.
        """
        ...

    async def remaining_quota(self) -> QuotaStatus:
        """Return the current rate-limit and circuit-breaker state."""
        ...
