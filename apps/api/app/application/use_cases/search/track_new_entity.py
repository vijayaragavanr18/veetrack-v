"""Use case: promote an untracked keyword to a tracked entity.

Called by the Cold Path background task (tasks.search.track_new_entity.run).
Steps:
  1. Resolve or create an entity for the keyword.
  2. Add the lowercase keyword as an alias (if not already present).
  3. Enqueue connector pull tasks so fresh articles arrive.

Zero infrastructure imports — uses Protocols only.
"""

from __future__ import annotations

import structlog

from app.domain.interfaces.repositories import EntityRepository
from app.domain.interfaces.services import TaskDispatcher

logger = structlog.get_logger(__name__)


class TrackNewEntity:
    def __init__(
        self,
        entity_repo: EntityRepository,
        dispatcher: TaskDispatcher,
    ) -> None:
        self._entity_repo = entity_repo
        self._dispatcher = dispatcher

    async def execute(self, keyword: str) -> str:
        """Return the entity_id (newly created or pre-existing)."""
        keyword = keyword.strip()
        if not keyword:
            raise ValueError("keyword must not be empty")

        # Try exact alias match first
        existing = await self._entity_repo.resolve_alias(keyword.lower())
        if existing is not None:
            entity_id = existing.id
            logger.info("track_entity.already_exists", keyword=keyword, entity_id=entity_id)
        else:
            # Create new entity for the keyword
            from app.domain.entities import Entity

            entity = Entity(canonical_name=keyword.title(), type="topic")
            saved = await self._entity_repo.save(entity)
            entity_id = saved.id
            await self._entity_repo.add_alias(entity_id, keyword.lower(), alias_type="search")
            logger.info("track_entity.created", keyword=keyword, entity_id=entity_id)

        # Trigger connector pulls for this new keyword
        for task_name in (
            "tasks.ingestion.watch_newsdata.run",
            "tasks.ingestion.watch_rss.run",
        ):
            self._dispatcher.send(
                task_name,
                kwargs={"source_id": f"auto-{entity_id[:8]}", "query": keyword},
                queue="ingestion",
            )

        logger.info("track_entity.connectors_triggered", keyword=keyword, entity_id=entity_id)
        return entity_id
