"""Concrete SQLAlchemy repository implementations."""

from app.infrastructure.db.repositories.article import SqlAlchemyArticleRepository
from app.infrastructure.db.repositories.entity import SqlAlchemyEntityRepository
from app.infrastructure.db.repositories.story import SqlAlchemyStoryRepository
from app.infrastructure.db.repositories.story_insight import SqlAlchemyStoryInsightRepository
from app.infrastructure.db.repositories.story_recommendation import (
    SqlAlchemyStoryRecommendationRepository,
)
from app.infrastructure.db.repositories.user import SqlAlchemyUserRepository
from app.infrastructure.db.repositories.workspace import SqlAlchemyWorkspaceRepository

__all__ = [
    "SqlAlchemyArticleRepository",
    "SqlAlchemyEntityRepository",
    "SqlAlchemyStoryInsightRepository",
    "SqlAlchemyStoryRecommendationRepository",
    "SqlAlchemyStoryRepository",
    "SqlAlchemyUserRepository",
    "SqlAlchemyWorkspaceRepository",
]
