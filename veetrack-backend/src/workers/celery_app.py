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
        "workers.tasks.ingestion.*": {"queue": "ingestion"},
        "workers.tasks.nlp.*": {"queue": "nlp"},
        "workers.tasks.llm.*": {"queue": "llm"},
        "workers.tasks.alerts.*": {"queue": "alerts"},
        "workers.tasks.exports.*": {"queue": "llm"},
        "workers.tasks.search.*": {"queue": "ingestion"},
        "workers.tasks.system.*": {"queue": "ingestion"},  # system tasks share the ingestion queue
    },
    task_default_queue="ingestion",
    # Beat schedule stubs — implementations added per phase
    beat_schedule={
        "daily-digest-example": {
            # Per-workspace digest; kwargs populated via admin API or env config.
            # This entry serves as the template — real workspaces add their own entries.
            "task": "workers.tasks.exports.scheduled_digest",
            "schedule": crontab(hour=7, minute=0),  # 07:00 UTC daily
            "kwargs": {
                "workspace_id": "default",
                "entity_keyword": "Tesla",
                "recipient_emails": [],   # populated at runtime
                "window_days": 1,
                "format": "pdf",
            },
            "options": {"queue": "llm"},
            "enabled": False,  # off by default; enable per workspace
        },
        "nightly-recluster": {
            "task": "workers.tasks.nlp.clustering.full_recluster",  # Phase 15
            "schedule": crontab(hour=0, minute=30),
            "options": {"queue": "nlp"},
        },
        "newsdata-pull-every-15min": {
            "task": "workers.tasks.ingestion.watch_newsdata.run",
            "schedule": crontab(minute="*/15"),
            "kwargs": {
                "source_id": "newsdata-default",
                "query": "Tesla OR Apple OR Microsoft",
            },
            "options": {"queue": "ingestion"},
        },
        "twitter-pull-every-15min": {
            "task": "workers.tasks.ingestion.watch_twitter.run",
            "schedule": crontab(minute="*/15"),
            "kwargs": {
                "source_id": "twitter-default",
                "query": "Tesla OR Apple OR Microsoft",
            },
            "options": {"queue": "ingestion"},
        },
        "rss-pull-every-15min": {
            "task": "workers.tasks.ingestion.watch_rss.run",
            "schedule": crontab(minute="*/15"),
            "kwargs": {
                "source_id": "rss-default",
                "feed_urls": [],  # populated via admin API at runtime
            },
            "options": {"queue": "ingestion"},
        },
        "youtube-pull-every-6h": {
            # Conservative: YouTube Data API has a very low daily unit quota.
            # 4 pulls/day × 10 results × 100 units/call = 4 000 units/day (well within 10 000).
            "task": "workers.tasks.ingestion.watch_youtube.run",
            "schedule": crontab(minute=0, hour="*/6"),
            "kwargs": {
                "source_id": "youtube-default",
                "query": "Tesla OR Apple OR Microsoft",
            },
            "options": {"queue": "ingestion"},
        },
    },
)

# Wire Prometheus counters + Sentry breadcrumbs onto Celery signals.
register_celery_signals(app)
