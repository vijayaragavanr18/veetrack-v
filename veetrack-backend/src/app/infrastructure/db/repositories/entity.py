from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Entity
from app.domain.exceptions import NotFoundError
from app.infrastructure.db.models.article_entity import ArticleEntityModel
from app.infrastructure.db.models.entity import EntityModel
from app.infrastructure.db.models.entity_alias import EntityAliasModel


def _to_domain(row: EntityModel) -> Entity:
    return Entity(
        id=row.id,
        canonical_name=row.canonical_name,
        type=row.type,  # type: ignore[arg-type]
        metadata=row.metadata_json,
    )


def _to_model(entity: Entity) -> EntityModel:
    return EntityModel(
        id=entity.id,
        canonical_name=entity.canonical_name,
        type=entity.type,
        metadata_json=entity.metadata,
    )


class SqlAlchemyEntityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, entity_id: str) -> Entity:
        result = await self._session.get(EntityModel, entity_id)
        if result is None:
            raise NotFoundError(f"Entity {entity_id!r} not found")
        return _to_domain(result)

    async def resolve_alias(self, alias_text: str) -> Entity | None:
        stmt = (
            select(EntityModel)
            .join(EntityAliasModel, EntityAliasModel.entity_id == EntityModel.id)
            .where(EntityAliasModel.alias_text == alias_text)
            .limit(1)
        )
        result = await self._session.scalar(stmt)
        return _to_domain(result) if result is not None else None

    async def save(self, entity: Entity) -> Entity:
        existing = await self._session.get(EntityModel, entity.id)
        if existing is None:
            row = _to_model(entity)
            self._session.add(row)
        else:
            existing.canonical_name = entity.canonical_name
            existing.type = entity.type
            existing.metadata_json = entity.metadata
            row = existing
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)

    async def add_alias(
        self,
        entity_id: str,
        alias_text: str,
        alias_type: str = "name",
    ) -> None:
        """Add an alias; silently ignore if (entity_id, alias_text) already exists."""
        stmt = (
            pg_insert(EntityAliasModel)
            .values(
                id=str(uuid.uuid4()),
                entity_id=entity_id,
                alias_text=alias_text,
                alias_type=alias_type,
            )
            .on_conflict_do_nothing()
        )
        await self._session.execute(stmt)

    async def list_all_aliases(self) -> list[tuple[str, str]]:
        """Return all (alias_text, entity_id) pairs."""
        stmt = select(EntityAliasModel.alias_text, EntityAliasModel.entity_id)
        rows = await self._session.execute(stmt)
        return [(r.alias_text, r.entity_id) for r in rows]

    async def search_by_name(self, query: str, limit: int = 10) -> list[Entity]:
        """Return entities whose canonical_name trigram-matches *query*."""
        stmt = (
            select(EntityModel)
            .where(func.similarity(EntityModel.canonical_name, query) > 0.1)
            .order_by(func.similarity(EntityModel.canonical_name, query).desc())
            .limit(limit)
        )
        rows = await self._session.scalars(stmt)
        return [_to_domain(r) for r in rows]

    async def save_article_entities(
        self,
        article_id: str,
        entity_scores: list[tuple[str, float]],
    ) -> None:
        """Upsert (article_id, entity_id, relevance_score) rows."""
        if not entity_scores:
            return
        for entity_id, score in entity_scores:
            stmt = (
                pg_insert(ArticleEntityModel)
                .values(
                    article_id=article_id,
                    entity_id=entity_id,
                    relevance_score=score,
                )
                .on_conflict_do_update(
                    index_elements=["article_id", "entity_id"],
                    set_={"relevance_score": score},
                )
            )
            await self._session.execute(stmt)
