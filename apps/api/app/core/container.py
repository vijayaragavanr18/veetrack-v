"""Composition root — explicit dependency wiring.

No magic auto-wiring. Each provider function constructs exactly the concrete
objects it needs and exposes them as FastAPI Depends-compatible callables.
The API layer imports provider functions from here; it never imports from infrastructure directly.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Annotated

import structlog
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.auth.get_current_user import GetCurrentUser
from app.application.use_cases.auth.login import Login
from app.application.use_cases.auth.refresh_token import RefreshToken
from app.application.use_cases.auth.register_user import RegisterUser
from app.application.use_cases.get_health_status import GetHealthStatus
from app.application.use_cases.ping_worker import PingWorker
from app.core.config import Settings, get_settings
from app.domain.interfaces.repositories import (
    ArticleRepository,
    EntityRepository,
    StoryInsightRepository,
    StoryRecommendationRepository,
    StoryRepository,
    UserRepository,
    WatchlistRepository,
    WorkspaceRepository,
)
from app.domain.interfaces.services import CacheGateway, TaskDispatcher
from app.infrastructure.cache.redis_client import RedisCacheGateway
from app.infrastructure.db.base import create_session_factory
from app.infrastructure.db.repositories.article import SqlAlchemyArticleRepository
from app.infrastructure.db.repositories.entity import SqlAlchemyEntityRepository
from app.infrastructure.db.repositories.story import SqlAlchemyStoryRepository
from app.infrastructure.db.repositories.story_insight import SqlAlchemyStoryInsightRepository
from app.infrastructure.db.repositories.story_recommendation import (
    SqlAlchemyStoryRecommendationRepository,
)
from app.infrastructure.db.repositories.user import SqlAlchemyUserRepository
from app.infrastructure.db.repositories.watchlist import SqlAlchemyWatchlistRepository
from app.infrastructure.db.repositories.workspace import SqlAlchemyWorkspaceRepository
from app.infrastructure.security.jwt_service import JwtService
from app.infrastructure.security.password_hasher import BcryptPasswordHasher
from app.infrastructure.tasks.celery_dispatcher import CeleryTaskDispatcher

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Infrastructure singletons
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _build_celery_app() -> object:
    """Build the Celery app used for dispatching tasks (broker-only, no worker).

    Returns `object` so we avoid importing celery at module level in the API process.
    The concrete type is only needed inside CeleryTaskDispatcher.
    """
    from celery import Celery as _Celery  # deferred — keeps startup fast if celery absent

    settings = get_settings()
    celery_app = _Celery(
        "veetrack",
        broker=settings.redis_url,
        backend=settings.redis_url,
    )
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
    )
    return celery_app


def get_task_dispatcher() -> TaskDispatcher:
    """Provide a TaskDispatcher backed by Celery (dispatch-only, no worker running here)."""
    return CeleryTaskDispatcher(_build_celery_app())


@lru_cache(maxsize=1)
def _build_cache_gateway() -> RedisCacheGateway:
    """Construct and cache the Redis cache gateway singleton (called once at startup)."""
    settings = get_settings()
    logger.info("container.building_cache_gateway", redis_url=settings.redis_url[:20] + "…")
    return RedisCacheGateway.from_url(settings.redis_url)


def get_cache_gateway() -> CacheGateway:
    """Provide a CacheGateway dependency."""
    return _build_cache_gateway()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a per-request async database session."""
    settings = get_settings()
    factory = create_session_factory(settings.database_url)
    async with factory() as session, session.begin():
        yield session


# ---------------------------------------------------------------------------
# Repository providers
# ---------------------------------------------------------------------------


def get_story_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StoryRepository:
    return SqlAlchemyStoryRepository(session)


def get_article_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ArticleRepository:
    return SqlAlchemyArticleRepository(session)


def get_entity_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EntityRepository:
    return SqlAlchemyEntityRepository(session)


def get_story_insight_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StoryInsightRepository:
    return SqlAlchemyStoryInsightRepository(session)


def get_story_recommendation_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StoryRecommendationRepository:
    return SqlAlchemyStoryRecommendationRepository(session)


def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserRepository:
    return SqlAlchemyUserRepository(session)


def get_workspace_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceRepository:
    return SqlAlchemyWorkspaceRepository(session)


def get_watchlist_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WatchlistRepository:
    return SqlAlchemyWatchlistRepository(session)


# ---------------------------------------------------------------------------
# Use case providers
# ---------------------------------------------------------------------------


def get_health_use_case(
    cache: Annotated[CacheGateway, Depends(get_cache_gateway)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GetHealthStatus:
    """Provide a GetHealthStatus use case with its dependencies injected."""
    return GetHealthStatus(cache=cache, settings=settings)


def get_ping_worker_use_case(
    cache: Annotated[CacheGateway, Depends(get_cache_gateway)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
) -> PingWorker:
    """Provide the PingWorker use case (cache read + task dispatch)."""
    return PingWorker(cache=cache, dispatcher=dispatcher)


# ---------------------------------------------------------------------------
# Auth use case providers
# ---------------------------------------------------------------------------


def get_jwt_service() -> JwtService:
    return JwtService(get_settings().jwt_secret)


def get_register_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    jwt_service: Annotated[JwtService, Depends(get_jwt_service)],
) -> RegisterUser:
    return RegisterUser(
        user_repo=SqlAlchemyUserRepository(session),
        workspace_repo=SqlAlchemyWorkspaceRepository(session),
        password_hasher=BcryptPasswordHasher(),
        token_service=jwt_service,
    )


def get_login_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    jwt_service: Annotated[JwtService, Depends(get_jwt_service)],
) -> Login:
    return Login(
        user_repo=SqlAlchemyUserRepository(session),
        password_hasher=BcryptPasswordHasher(),
        token_service=jwt_service,
    )


def get_refresh_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    jwt_service: Annotated[JwtService, Depends(get_jwt_service)],
) -> RefreshToken:
    return RefreshToken(
        user_repo=SqlAlchemyUserRepository(session),
        token_service=jwt_service,
    )


def get_get_current_user_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GetCurrentUser:
    return GetCurrentUser(user_repo=SqlAlchemyUserRepository(session))
