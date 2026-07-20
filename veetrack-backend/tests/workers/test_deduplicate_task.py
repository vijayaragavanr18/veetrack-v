"""Unit tests: deduplicate task — MinHash/LSH helpers (no DB/Celery)."""

from __future__ import annotations

import pytest
from datasketch import MinHash, MinHashLSH  # type: ignore[import-untyped]

from workers.tasks.nlp.deduplicate import _build_minhash

# ---------------------------------------------------------------------------
# _build_minhash helper
# ---------------------------------------------------------------------------


def test_build_minhash_returns_minhash() -> None:
    m = _build_minhash("hello world")
    assert isinstance(m, MinHash)


def test_build_minhash_identical_texts() -> None:
    text = "Tesla surpasses delivery targets in Q3 2024."
    m1 = _build_minhash(text)
    m2 = _build_minhash(text)
    assert m1.jaccard(m2) == pytest.approx(1.0)


def test_build_minhash_near_identical_texts_high_similarity() -> None:
    base = (
        "Apple CEO announces the brand new MacBook lineup at WWDC 2024 in Cupertino. "
        "The event featured demonstrations of the new M4 chip and the updated operating system."
    )
    variant = base.replace("brand new", "new")
    m1 = _build_minhash(base)
    m2 = _build_minhash(variant)
    assert m1.jaccard(m2) > 0.4


def test_build_minhash_unrelated_texts_low_similarity() -> None:
    m1 = _build_minhash("Amazon Prime Day breaks records with highest ever sales.")
    m2 = _build_minhash("European Central Bank cuts rates for the second time this year.")
    assert m1.jaccard(m2) < 0.3


def test_build_minhash_empty_string_no_crash() -> None:
    m = _build_minhash("")
    assert isinstance(m, MinHash)


def test_build_minhash_short_text_no_crash() -> None:
    m = _build_minhash("Hi")
    assert isinstance(m, MinHash)


# ---------------------------------------------------------------------------
# Integration: build index + query (simulates the task's dedup logic)
# ---------------------------------------------------------------------------


def test_dedup_flags_near_duplicate() -> None:
    lsh: MinHashLSH = MinHashLSH(threshold=0.5, num_perm=128)

    base = (
        "Microsoft Azure revenue grew thirty percent year-over-year in the latest quarter, "
        "driven by strong enterprise AI demand and expanded data centre capacity across Europe "
        "and Asia Pacific. CFO Amy Hood said cloud margins continue to improve as fixed costs "
        "are spread across a larger customer base."
    )
    near_dup = base + " Analysts expect the trend to continue into next year."

    lsh.insert("art-001", _build_minhash(base))
    candidates: list[str] = lsh.query(_build_minhash(near_dup))
    assert candidates == ["art-001"]


def test_dedup_does_not_flag_unrelated() -> None:
    lsh: MinHashLSH = MinHashLSH(threshold=0.5, num_perm=128)
    lsh.insert("art-001", _build_minhash("Tesla Cybertruck deliveries begin in December."))

    unrelated = "EU fines TikTok over data privacy violations."
    candidates: list[str] = lsh.query(_build_minhash(unrelated))
    assert candidates == []
