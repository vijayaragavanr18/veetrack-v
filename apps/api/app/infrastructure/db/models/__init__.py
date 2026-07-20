"""ORM models — import all here so Alembic autogenerate picks them up."""

from app.infrastructure.db.models.alert import AlertModel
from app.infrastructure.db.models.api_usage_log import ApiUsageLogModel
from app.infrastructure.db.models.article import ArticleModel
from app.infrastructure.db.models.article_entity import ArticleEntityModel
from app.infrastructure.db.models.audit_log import AuditLogModel
from app.infrastructure.db.models.entity import EntityModel
from app.infrastructure.db.models.entity_alias import EntityAliasModel
from app.infrastructure.db.models.source import SourceModel
from app.infrastructure.db.models.story import StoryModel
from app.infrastructure.db.models.story_article import StoryArticleModel
from app.infrastructure.db.models.story_insight import StoryInsightModel
from app.infrastructure.db.models.story_recommendation import StoryRecommendationModel
from app.infrastructure.db.models.user import UserModel
from app.infrastructure.db.models.watchlist import WatchlistModel
from app.infrastructure.db.models.workspace import WorkspaceModel

__all__ = [
    "AlertModel",
    "ApiUsageLogModel",
    "ArticleEntityModel",
    "ArticleModel",
    "AuditLogModel",
    "EntityAliasModel",
    "EntityModel",
    "SourceModel",
    "StoryArticleModel",
    "StoryInsightModel",
    "StoryModel",
    "StoryRecommendationModel",
    "UserModel",
    "WatchlistModel",
    "WorkspaceModel",
]
