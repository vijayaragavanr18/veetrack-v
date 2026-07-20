from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Article
from app.domain.exceptions import ConflictError, NotFoundError
from app.infrastructure.db.models.article import ArticleModel
from app.infrastructure.db.models.story_article import StoryArticleModel


def _to_domain(row: ArticleModel) -> Article:
    return Article(
        id=row.id,
        source_id=row.source_id,
        external_id=row.external_id,
        url=row.url,
        headline=row.headline,
        hero_image_url=row.hero_image_url,
        publisher=row.publisher,
        published_at=row.published_at,
        clean_content=row.clean_content,
        language=row.language,
        sentiment_label=row.sentiment_label,  # type: ignore[arg-type]
        sentiment_score=row.sentiment_score,
        dedup_hash=row.dedup_hash,
        ingested_at=row.ingested_at,
    )


def _to_model(entity: Article) -> ArticleModel:
    return ArticleModel(
        id=entity.id,
        source_id=entity.source_id,
        external_id=entity.external_id,
        url=entity.url,
        headline=entity.headline,
        hero_image_url=entity.hero_image_url,
        publisher=entity.publisher,
        published_at=entity.published_at,
        clean_content=entity.clean_content,
        language=entity.language,
        sentiment_label=entity.sentiment_label,
        sentiment_score=entity.sentiment_score,
        dedup_hash=entity.dedup_hash,
        ingested_at=entity.ingested_at,
    )


class SqlAlchemyArticleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, article_id: str) -> Article:
        result = await self._session.get(ArticleModel, article_id)
        if result is None:
            raise NotFoundError(f"Article {article_id!r} not found")
        return _to_domain(result)

    async def list_by_story(self, story_id: str) -> list[Article]:
        stmt = (
            select(ArticleModel)
            .join(StoryArticleModel, StoryArticleModel.article_id == ArticleModel.id)
            .where(StoryArticleModel.story_id == story_id)
            .order_by(ArticleModel.published_at.asc())
        )
        rows = await self._session.scalars(stmt)
        return [_to_domain(r) for r in rows]

    async def find_by_dedup_hash(self, dedup_hash: str) -> Article | None:
        stmt = select(ArticleModel).where(ArticleModel.dedup_hash == dedup_hash)
        result = await self._session.scalar(stmt)
        return _to_domain(result) if result is not None else None

    async def save(self, article: Article) -> Article:
        existing = await self._session.get(ArticleModel, article.id)
        if existing is None:
            row = _to_model(article)
            self._session.add(row)
            try:
                await self._session.flush()
            except IntegrityError as exc:
                raise ConflictError(f"Article with dedup_hash {article.dedup_hash!r} already exists") from exc
        else:
            existing.headline = article.headline
            existing.clean_content = article.clean_content
            existing.sentiment_label = article.sentiment_label
            existing.sentiment_score = article.sentiment_score
            row = existing
            await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)
