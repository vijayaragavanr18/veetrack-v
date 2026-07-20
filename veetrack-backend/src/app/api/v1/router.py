"""Aggregates all v1 sub-routers into a single APIRouter.

Future phases add their routers here:
  Phase 06: auth_router (POST /auth/login, /auth/refresh)
  Phase 18: feed_router (GET /feed)
  Phase 18: stories_router (GET /stories/{id}, ...)
  Phase 24: watchlists_router
  Phase 25: exports_router
  Phase 26: admin_router
"""

from fastapi import APIRouter

from app.api.v1.admin.dashboard import router as admin_dashboard_router
from app.api.v1.admin.review_queue import router as admin_review_queue_router
from app.api.v1.admin.rss_feeds import router as admin_rss_feeds_router
from app.api.v1.admin.sources import router as admin_sources_router
from app.api.v1.auth import router as auth_router
from app.api.v1.entities import router as entities_router
from app.api.v1.exports import router as exports_router
from app.api.v1.feed import router as feed_router
from app.api.v1.health import router as health_router
from app.api.v1.internal.clustering_debug import router as internal_clustering_router
from app.api.v1.internal.similarity import router as internal_similarity_router
from app.api.v1.stories import router as stories_router
from app.api.v1.system import router as system_router
from app.api.v1.watchlists import router as watchlists_router

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(health_router)
v1_router.include_router(system_router)
v1_router.include_router(auth_router)
v1_router.include_router(admin_dashboard_router)
v1_router.include_router(admin_sources_router)
v1_router.include_router(admin_rss_feeds_router)
v1_router.include_router(admin_review_queue_router)
v1_router.include_router(entities_router)
v1_router.include_router(feed_router)
v1_router.include_router(stories_router)
v1_router.include_router(internal_similarity_router)
v1_router.include_router(internal_clustering_router)
v1_router.include_router(watchlists_router)
v1_router.include_router(exports_router)
