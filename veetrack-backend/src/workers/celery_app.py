"""Celery application and shared worker settings.

Queues:
  ingestion  — source connector pulls, normalisation, dedup
  nlp        — entity extraction, sentiment, embeddings, clustering
  llm        — executive summaries, recommendations (hosted LLM calls)
  alerts     — watchlist evaluation, WebSocket/email/Slack push

Beat schedule:
  nightly_recluster — placeholder for Phase 15 HDBSCAN full re-cluster (00:30 UTC daily)
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from pydantic_settings import BaseSettings, SettingsConfigDict

from workers.observability import init_worker_sentry, register_celery_signals


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    redis_url: str = "redis://localhost:6379/0"
    celery_result_expires: int = 3600  # TTL for task result records (seconds)


worker_settings = WorkerSettings()

# Sentry must be initialised before the Celery app so the CeleryIntegration
# can hook into task dispatching from the very first task.
init_worker_sentry()

app = Celery(
    "veetrack",
    broker=worker_settings.redis_url,
    backend=worker_settings.redis_url,
    include=[
        "workers.tasks.ingestion",
        "workers.tasks.nlp",
        "workers.tasks.llm",
        "workers.tasks.alerts",
        "workers.tasks.exports.scheduled_digest",
        "workers.tasks.search",
        "workers.tasks.system.ping",
        "workers.tasks.system.purge_old_articles",
        "workers.tasks.search.refresh_tracked_keywords",
    ],
)

app.conf.update(
    # Serialisation
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Time
    timezone="UTC",
    enable_utc=True,
    # Results
    result_expires=worker_settings.celery_result_expires,
    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # one task at a time per worker process (fair dispatch)
    # Queue routing
    task_routes={
        "tasks.ingestion.*": {"queue": "ingestion"},
        "tasks.nlp.*": {"queue": "nlp"},
        "tasks.llm.*": {"queue": "llm"},
        "tasks.alerts.*": {"queue": "alerts"},
        "tasks.exports.*": {"queue": "llm"},
        "tasks.search.*": {"queue": "ingestion"},
        "tasks.system.*": {"queue": "ingestion"},
        "tasks.search.refresh_tracked_keywords.*": {"queue": "ingestion"},
        "tasks.system.purge_old_articles.*": {"queue": "ingestion"},
    },
    task_default_queue="ingestion",
    # Beat schedule stubs — implementations added per phase
    beat_schedule={
        # daily-digest-example: disabled — enable per workspace via admin API
        "nightly-recluster": {
            "task": "tasks.nlp.clustering.full_recluster",
            "schedule": crontab(hour=0, minute=30),
            "options": {"queue": "nlp"},
        },
        "newsdata-pull-every-15min": {
            "task": "tasks.ingestion.watch_newsdata.run",
            "schedule": crontab(minute="*/15"),
            "kwargs": {
                "source_id": "newsdata-default",
                "query": "Tesla OR Apple OR Microsoft OR AI OR Technology",
            },
            "options": {"queue": "ingestion"},
        },
        "twitter-pull-every-15min": {
            "task": "tasks.ingestion.watch_twitter.run",
            "schedule": crontab(minute="*/15"),
            "kwargs": {
                "source_id": "twitter-default",
                "query": "Tesla OR Apple OR Microsoft OR AI OR Technology",
            },
            "options": {"queue": "ingestion"},
        },
        "rss-pull-every-15min": {
            "task": "tasks.ingestion.watch_rss.run",
            "schedule": crontab(minute="*/15"),
            "kwargs": {
                "source_id": "rss-default",
                "feed_urls": [
                    "https://feeds.bbci.co.uk/news/technology/rss.xml",
                    "https://feeds.feedburner.com/TechCrunch",
                    "https://www.theverge.com/rss/index.xml",
                    "https://www.wired.com/feed/rss",
                ],
            },
            "options": {"queue": "ingestion"},
        },
        "youtube-pull-every-6h": {
            "task": "tasks.ingestion.watch_youtube.run",
            "schedule": crontab(minute=0, hour="*/6"),
            "kwargs": {
                "source_id": "youtube-default",
                "query": "Tesla OR Apple OR Microsoft OR AI OR Technology",
            },
            "options": {"queue": "ingestion"},
        },
        "purge-old-articles-hourly": {
            "task": "tasks.system.purge_old_articles.run",
            "schedule": crontab(minute=0),  # every hour on the hour
            "options": {"queue": "ingestion"},
        },
        "refresh-tracked-keywords-30min": {
            "task": "tasks.search.refresh_tracked_keywords.run",
            "schedule": crontab(minute="*/30"),
            "options": {"queue": "ingestion"},
        },
    },
)

# Wire Prometheus counters + Sentry breadcrumbs onto Celery signals.
register_celery_signals(app)
