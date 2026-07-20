"""Pipeline orchestrator: Celery chain for per-article NLP pipeline.

Current stages (Phase 15):
  normalize → deduplicate → extract_entities → analyze_sentiment
    → embed_article → cluster_article

Future stages (Phase 16+) can be appended to the chain without touching
the ingestion tasks — just extend the chain here.
"""

from __future__ import annotations

from celery_app import app


def dispatch_pipeline(article_id: str) -> None:
    """Fire the full NLP chain for *article_id*."""
    from tasks.nlp.analyze_sentiment import run as analyze_sentiment_task
    from tasks.nlp.cluster_article import run as cluster_article_task
    from tasks.nlp.deduplicate import run as deduplicate_task
    from tasks.nlp.embed_article import run as embed_article_task
    from tasks.nlp.extract_entities import run as extract_entities_task
    from tasks.nlp.normalize import run as normalize_task

    (
        normalize_task.si(article_id=article_id)
        | deduplicate_task.si(article_id=article_id)
        | extract_entities_task.si(article_id=article_id)
        | analyze_sentiment_task.si(article_id=article_id)
        | embed_article_task.si(article_id=article_id)
        | cluster_article_task.si(article_id=article_id)
    ).apply_async()


@app.task(
    name="tasks.nlp.pipeline_orchestrator.run",
    queue="nlp",
    bind=False,
)
def run(*, article_id: str) -> None:
    """Entry-point task: kick off the full NLP pipeline for *article_id*."""
    dispatch_pipeline(article_id)
