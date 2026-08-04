"""Unit tests: pipeline_orchestrator.dispatch_pipeline.

Verifies the chain is constructed and launched without touching a real broker.
All task .run references are replaced with MagicMock objects that support
the .si() → | → .apply_async() protocol.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task_mock(name: str = "task") -> MagicMock:
    """Return a mock that mimics a Celery task's .si() and | chaining API."""
    task_mock = MagicMock(name=name)
    # si() returns a signature mock that supports | and .apply_async()
    sig_mock = MagicMock(name=f"{name}.si()")
    sig_mock.__or__ = MagicMock(return_value=sig_mock)  # support `a | b`
    sig_mock.__ror__ = MagicMock(return_value=sig_mock)
    task_mock.si = MagicMock(return_value=sig_mock)
    return task_mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_dispatch_pipeline_calls_normalize() -> None:
    """dispatch_pipeline calls normalize_task.si(article_id=...)."""
    normalize = _make_task_mock("normalize")
    deduplicate = _make_task_mock("deduplicate")
    extract_entities = _make_task_mock("extract_entities")
    analyze_sentiment = _make_task_mock("analyze_sentiment")
    embed_article = _make_task_mock("embed_article")
    cluster_article = _make_task_mock("cluster_article")

    with (
        patch("workers.tasks.nlp.normalize.run", normalize),
        patch("workers.tasks.nlp.deduplicate.run", deduplicate),
        patch("workers.tasks.nlp.extract_entities.run", extract_entities),
        patch("workers.tasks.nlp.analyze_sentiment.run", analyze_sentiment),
        patch("workers.tasks.nlp.embed_article.run", embed_article),
        patch("workers.tasks.nlp.cluster_article.run", cluster_article),
    ):
        from workers.tasks.nlp.pipeline_orchestrator import dispatch_pipeline

        dispatch_pipeline("art-1")

    normalize.si.assert_called_once_with(article_id="art-1")


def test_dispatch_pipeline_calls_all_tasks() -> None:
    """dispatch_pipeline calls .si() on all 6 tasks in the chain."""
    normalize = _make_task_mock("normalize")
    deduplicate = _make_task_mock("deduplicate")
    extract_entities = _make_task_mock("extract_entities")
    analyze_sentiment = _make_task_mock("analyze_sentiment")
    embed_article = _make_task_mock("embed_article")
    cluster_article = _make_task_mock("cluster_article")

    with (
        patch("workers.tasks.nlp.normalize.run", normalize),
        patch("workers.tasks.nlp.deduplicate.run", deduplicate),
        patch("workers.tasks.nlp.extract_entities.run", extract_entities),
        patch("workers.tasks.nlp.analyze_sentiment.run", analyze_sentiment),
        patch("workers.tasks.nlp.embed_article.run", embed_article),
        patch("workers.tasks.nlp.cluster_article.run", cluster_article),
    ):
        from workers.tasks.nlp.pipeline_orchestrator import dispatch_pipeline

        dispatch_pipeline("article-xyz")

    normalize.si.assert_called_once_with(article_id="article-xyz")
    deduplicate.si.assert_called_once_with(article_id="article-xyz")
    extract_entities.si.assert_called_once_with(article_id="article-xyz")
    analyze_sentiment.si.assert_called_once_with(article_id="article-xyz")
    embed_article.si.assert_called_once_with(article_id="article-xyz")
    cluster_article.si.assert_called_once_with(article_id="article-xyz")


def test_dispatch_pipeline_chains_in_order_and_calls_apply_async() -> None:
    """dispatch_pipeline produces a chain and calls .apply_async() on it."""
    # Track the chain construction order via the | operator
    chain_steps: list[str] = []

    def make_mock(step_name: str) -> MagicMock:
        m = MagicMock(name=step_name)
        sig = MagicMock(name=f"{step_name}_sig")

        def _or(other: object) -> MagicMock:
            chain_steps.append(step_name)
            return sig  # return same sig so chaining continues

        sig.__or__ = MagicMock(side_effect=_or)
        m.si = MagicMock(return_value=sig)
        return m

    normalize = make_mock("normalize")
    deduplicate = make_mock("deduplicate")
    extract_entities = make_mock("extract_entities")
    analyze_sentiment = make_mock("analyze_sentiment")
    embed_article = make_mock("embed_article")
    cluster_article = make_mock("cluster_article")

    with (
        patch("workers.tasks.nlp.normalize.run", normalize),
        patch("workers.tasks.nlp.deduplicate.run", deduplicate),
        patch("workers.tasks.nlp.extract_entities.run", extract_entities),
        patch("workers.tasks.nlp.analyze_sentiment.run", analyze_sentiment),
        patch("workers.tasks.nlp.embed_article.run", embed_article),
        patch("workers.tasks.nlp.cluster_article.run", cluster_article),
    ):
        from workers.tasks.nlp.pipeline_orchestrator import dispatch_pipeline

        dispatch_pipeline("pipeline-test-id")

    # 5 | operations happen (6 tasks = 5 joins)
    assert len(chain_steps) == 5
    # normalize is the first step (left-hand side of first |)
    assert chain_steps[0] == "normalize"

    # apply_async is called on the final signature mock (from the last | result)
    # Verify at least one of the sig mocks had apply_async called
    all_sig_mocks = [
        normalize.si.return_value,
        deduplicate.si.return_value,
        extract_entities.si.return_value,
        analyze_sentiment.si.return_value,
        embed_article.si.return_value,
        cluster_article.si.return_value,
    ]
    apply_async_calls = sum(1 for sig in all_sig_mocks if sig.apply_async.called)
    assert apply_async_calls >= 1, "apply_async() was never called on any chain signature"


def test_dispatch_pipeline_passes_correct_article_id() -> None:
    """dispatch_pipeline forwards the article_id argument to every task."""
    article_id = "unique-article-42"
    received_ids: list[str] = []

    def capturing_si(**kwargs: object) -> MagicMock:
        received_ids.append(str(kwargs.get("article_id", "")))
        sig = MagicMock()
        sig.__or__ = MagicMock(return_value=sig)
        sig.apply_async = MagicMock()
        return sig

    task_mocks = {}
    for name in ["normalize", "deduplicate", "extract_entities",
                 "analyze_sentiment", "embed_article", "cluster_article"]:
        m = MagicMock(name=name)
        m.si = MagicMock(side_effect=capturing_si)
        task_mocks[name] = m

    with (
        patch("workers.tasks.nlp.normalize.run", task_mocks["normalize"]),
        patch("workers.tasks.nlp.deduplicate.run", task_mocks["deduplicate"]),
        patch("workers.tasks.nlp.extract_entities.run", task_mocks["extract_entities"]),
        patch("workers.tasks.nlp.analyze_sentiment.run", task_mocks["analyze_sentiment"]),
        patch("workers.tasks.nlp.embed_article.run", task_mocks["embed_article"]),
        patch("workers.tasks.nlp.cluster_article.run", task_mocks["cluster_article"]),
    ):
        from workers.tasks.nlp.pipeline_orchestrator import dispatch_pipeline

        dispatch_pipeline(article_id)

    assert len(received_ids) == 6
    assert all(aid == article_id for aid in received_ids), (
        f"Not all tasks received the correct article_id: {received_ids}"
    )
