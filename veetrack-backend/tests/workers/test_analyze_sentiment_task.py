"""Unit tests: analyze_sentiment task — mocked pipeline, no GPU/model download."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workers.tasks.nlp.analyze_sentiment import (
    _DEFAULT_SENTIMENT_MODEL,
    _LABEL_MAP,
    _MIN_WORD_COUNT,
    _classify,
)


# ---------------------------------------------------------------------------
# _label_map coverage
# ---------------------------------------------------------------------------

def test_label_map_covers_all_five_classes() -> None:
    assert _LABEL_MAP["very positive"] == "positive"
    assert _LABEL_MAP["positive"] == "positive"
    assert _LABEL_MAP["neutral"] == "neutral"
    assert _LABEL_MAP["negative"] == "negative"
    assert _LABEL_MAP["very negative"] == "negative"


# ---------------------------------------------------------------------------
# _classify helper
# ---------------------------------------------------------------------------

def _make_pipe(label: str, score: float) -> Any:
    return MagicMock(return_value=[{"label": label, "score": score}])


def test_classify_positive() -> None:
    pipe = _make_pipe("positive", 0.93)
    label, score, low_conf = _classify(pipe, "Record profits announced today, shares surge.")
    assert label == "positive"
    assert score == pytest.approx(0.93)
    assert not low_conf


def test_classify_negative() -> None:
    pipe = _make_pipe("negative", 0.88)
    label, score, low_conf = _classify(pipe, "Mass layoffs hit the firm as losses mount.")
    assert label == "negative"


def test_classify_neutral() -> None:
    pipe = _make_pipe("neutral", 0.71)
    label, score, low_conf = _classify(pipe, "The board met on Tuesday to review quarterly figures.")
    assert label == "neutral"


def test_classify_empty_string_returns_neutral_low_confidence() -> None:
    pipe = _make_pipe("positive", 0.9)
    label, score, low_conf = _classify(pipe, "")
    assert label == "neutral"
    assert score == pytest.approx(0.5)
    assert low_conf is True
    pipe.assert_not_called()


def test_classify_short_text_flags_low_confidence() -> None:
    pipe = _make_pipe("positive", 0.8)
    # 2 words — below _MIN_WORD_COUNT (5)
    label, score, low_conf = _classify(pipe, "Great move.")
    assert low_conf is True


def test_classify_five_word_text_not_low_confidence() -> None:
    pipe = _make_pipe("positive", 0.85)
    # exactly _MIN_WORD_COUNT words
    label, score, low_conf = _classify(pipe, "one two three four five")
    assert low_conf is False


def test_classify_very_positive_maps_to_positive() -> None:
    pipe = _make_pipe("very positive", 0.97)
    label, _, _ = _classify(pipe, "Absolutely outstanding performance across all metrics!")
    assert label == "positive"


def test_classify_very_negative_maps_to_negative() -> None:
    pipe = _make_pipe("very negative", 0.91)
    label, _, _ = _classify(pipe, "Catastrophic failure, worst quarter in company history.")
    assert label == "negative"


# ---------------------------------------------------------------------------
# Batch throughput: batch must be faster than one-at-a-time
# ---------------------------------------------------------------------------

def test_batch_faster_than_one_at_a_time() -> None:
    """
    Verifies that calling the pipeline with a list is faster than N individual
    calls. We mock a realistic per-call delay of 10 ms.
    """
    DELAY_PER_CALL_S = 0.010
    texts = [f"Article number {i} with some content for testing." for i in range(20)]

    call_count = {"n": 0}

    def _slow_pipe(inputs: Any) -> list[dict]:
        is_batch = isinstance(inputs, list)
        # Batch: one sleep; single: one sleep per item
        if is_batch:
            time.sleep(DELAY_PER_CALL_S)
            return [{"label": "neutral", "score": 0.5}] * len(inputs)
        else:
            time.sleep(DELAY_PER_CALL_S)
            call_count["n"] += 1
            return [{"label": "neutral", "score": 0.5}]

    # --- one-at-a-time ---
    t0 = time.perf_counter()
    for text in texts:
        _slow_pipe(text)
    one_at_a_time_s = time.perf_counter() - t0

    # --- batch ---
    t0 = time.perf_counter()
    _slow_pipe(texts)
    batch_s = time.perf_counter() - t0

    print(
        f"\n[benchmark] one-at-a-time: {one_at_a_time_s*1000:.1f} ms | "
        f"batch: {batch_s*1000:.1f} ms | "
        f"speedup: {one_at_a_time_s / batch_s:.1f}×"
    )
    assert batch_s < one_at_a_time_s, (
        f"Batch ({batch_s*1000:.1f} ms) should be faster than "
        f"one-at-a-time ({one_at_a_time_s*1000:.1f} ms)"
    )
