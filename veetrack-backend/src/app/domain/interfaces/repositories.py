"""Repository interface Protocols.

These Protocols define the contract every concrete repository (Phase 04+) must satisfy.
The application layer depends only on these interfaces, never on SQLAlchemy or Redis directly.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.entities import (
    Article,
    Entity,
    QuotaStatus,
    Source,
    Story,
    StoryInsight,
    StoryRecommendation,
    User,
    Workspace,
)
from app.domain.entities.watchlist import AlertRecord, Watchlist


@runtime_checkable
class StoryRepository(Protocol):
    """Read/write access to the stories table."""

    async def get_by_id(self, story_id: str) -> Story:
        """Return a Story by primary key; raise NotFoundError if absent."""
        ...

    async def list_by_entity(
        self,
        entity_id: str,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[Story]:
        """Return paginated stories for a tracked entity, newest first."""
        ...

    async def save(self, story: Story) -> Story:
        """Persist a new or updated story; return the saved instance."""
        ...


@runtime_checkable
class ArticleRepository(Protocol):
    """Read/write access to the articles table."""

    async def get_by_id(self, article_id: str) -> Article:
        """Return an Article by primary key; raise NotFoundError if absent."""
        ...

    async def list_by_story(self, story_id: str) -> list[Article]:
        """Return all articles clustered under a story, chronological."""
        ...

    async def find_by_dedup_hash(self, dedup_hash: str) -> Article | None:
        """Return an existing article with the given hash, or None (dedup check)."""
        ...

    async def save(self, article: Article) -> Article:
        """Persist a new article; raise ConflictError on duplicate dedup_hash."""
        ...


@runtime_checkable
class EntityRepository(Protocol):
    """Read/write access to entities and entity_aliases tables."""

    async def get_by_id(self, entity_id: str) -> Entity:
        """Return an Entity by primary key; raise NotFoundError if absent."""
        ...

    async def resolve_alias(self, alias_text: str) -> Entity | None:
        """Resolve a raw text mention (e.g. '$TSLA') to its canonical Entity, or None."""
        ...

    async def save(self, entity: Entity) -> Entity:
        """Persist a new or updated entity."""
        ...

    async def add_alias(
        self,
        entity_id: str,
        alias_text: str,
        alias_type: str = "name",
    ) -> None:
        """Add an alias for *entity_id*; silently ignore if the alias already exists."""
        ...

    async def list_all_aliases(self) -> list[tuple[str, str]]:
        """Return all (alias_text, entity_id) pairs for fuzzy resolution."""
        ...

    async def search_by_name(self, query: str, limit: int = 10) -> list[Entity]:
        """Return entities whose canonical_name or aliases match *query* (trigram)."""
        ...

    async def save_article_entities(
        self,
        article_id: str,
        entity_scores: list[tuple[str, float]],
    ) -> None:
        """Upsert rows in article_entities for (entity_id, relevance_score) pairs."""
        ...


@runtime_checkable
class StoryInsightRepository(Protocol):
    """Read/write access to the story_insights table."""

    async def get_by_story_id(self, story_id: str) -> StoryInsight | None:
        """Return the latest insight for a story, or None if not yet generated."""
        ...

    async def save(self, insight: StoryInsight) -> StoryInsight:
        """Persist a new insight record."""
        ...


@runtime_checkable
class StoryRecommendationRepository(Protocol):
    """Read/write access to the story_recommendations table."""

    async def list_by_story_id(self, story_id: str) -> list[StoryRecommendation]:
        """Return all recommendations for a story, confidence-descending."""
        ...

    async def save(self, recommendation: StoryRecommendation) -> StoryRecommendation:
        """Persist a new recommendation record."""
        ...


@runtime_checkable
class UserRepository(Protocol):
    """Read/write access to the users table."""

    async def get_by_email(self, email: str, workspace_id: str) -> User | None:
        """Look up a user by email within a workspace; return None if not found."""
        ...

    async def get_by_id(self, user_id: str) -> User:
        """Return a User by primary key; raise NotFoundError if absent."""
        ...

    async def save(self, user: User) -> User:
        """Persist a new or updated user."""
        ...


@runtime_checkable
class WorkspaceRepository(Protocol):
    """Read/write access to the workspaces table."""

    async def get_by_id(self, workspace_id: str) -> Workspace:
        """Return a Workspace by primary key; raise NotFoundError if absent."""
        ...

    async def save(self, workspace: Workspace) -> Workspace:
        """Persist a new workspace."""
        ...


@runtime_checkable
class SourceRepository(Protocol):
    """Read/write access to the sources table."""

    async def get_by_id(self, source_id: str) -> Source:
        """Return a Source by primary key; raise NotFoundError if absent."""
        ...

    async def list_active(self) -> list[Source]:
        """Return all sources with is_active=True."""
        ...

    async def save(self, source: Source) -> Source:
        """Persist a new or updated source."""
        ...


@runtime_checkable
class WatchlistRepository(Protocol):
    """Read/write access to the watchlists and alerts tables."""

    async def get_by_id(self, watchlist_id: str) -> Watchlist:
        """Return a Watchlist by primary key; raise NotFoundError if absent."""
        ...

    async def list_by_workspace_user(
        self,
        workspace_id: str,
        user_id: str,
    ) -> list[Watchlist]:
        """Return all watchlists for a user in a workspace."""
        ...

    async def find_by_entity(
        self,
        workspace_id: str,
        user_id: str,
        entity_id: str,
    ) -> Watchlist | None:
        """Return an existing watchlist for the entity, or None."""
        ...

    async def save(self, watchlist: Watchlist) -> Watchlist:
        """Persist a new watchlist; raise ConflictError on duplicate (workspace, user, entity)."""
        ...

    async def delete(self, watchlist_id: str) -> None:
        """Delete a watchlist by primary key; raise NotFoundError if absent."""
        ...

    async def list_by_entity_across_workspace(
        self,
        entity_id: str,
        workspace_id: str,
    ) -> list[Watchlist]:
        """Return all watchlists tracking entity_id in workspace (for alert fan-out)."""
        ...

    async def save_alert(self, alert: AlertRecord) -> AlertRecord:
        """Persist a new alert record."""
        ...

    async def get_alert_by_id(self, alert_id: str) -> AlertRecord:
        """Return an AlertRecord by primary key; raise NotFoundError if absent."""
        ...

    async def record_alert_feedback(
        self,
        alert_id: str,
        user_id: str,
        feedback: str,
    ) -> AlertRecord:
        """Set user_feedback ('useful'|'not_useful') on an alert row."""
        ...


@runtime_checkable
class ApiUsageLogRepository(Protocol):
    """Read/write access to the api_usage_log table."""

    async def get_current_window(self, source_id: str, window_start: str) -> QuotaStatus | None:
        """Return usage stats for source_id in the given ISO-8601 window, or None."""
        ...

    async def upsert(self, status: QuotaStatus) -> QuotaStatus:
        """Insert or update the usage row for this source+window."""
        ...

    async def list_by_source(self, source_id: str, limit: int = 10) -> list[QuotaStatus]:
        """Return the most recent usage windows for a source, newest first."""
        ...
