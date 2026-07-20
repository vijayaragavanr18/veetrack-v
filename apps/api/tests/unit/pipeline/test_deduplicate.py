"""Unit tests for deduplicate.py — pure MinHash/LSH functions."""

from __future__ import annotations

import pytest

from app.application.use_cases.pipeline.deduplicate import (
    add_to_index,
    build_lsh_index,
    compute_minhash,
    find_duplicate,
    is_near_duplicate,
)

# ---------------------------------------------------------------------------
# compute_minhash
# ---------------------------------------------------------------------------

def test_compute_minhash_returns_object() -> None:
    m = compute_minhash("hello world")
    assert m is not None


def test_compute_minhash_identical_texts_same_signature() -> None:
    text = "Tesla reported record revenue in Q4 2024."
    m1 = compute_minhash(text)
    m2 = compute_minhash(text)
    assert m1.jaccard(m2) == pytest.approx(1.0)


def test_compute_minhash_different_texts_low_similarity() -> None:
    m1 = compute_minhash("Apple launches new iPhone model today.")
    m2 = compute_minhash("EU regulators impose fines on social media platforms.")
    assert m1.jaccard(m2) < 0.3


def test_compute_minhash_empty_string_no_crash() -> None:
    m = compute_minhash("")
    assert m is not None


# ---------------------------------------------------------------------------
# build_lsh_index / add_to_index / find_duplicate
# ---------------------------------------------------------------------------

def test_build_lsh_index_returns_empty_index() -> None:
    lsh = build_lsh_index()
    m = compute_minhash("any text")
    assert find_duplicate(lsh, m) is None


def test_add_and_find_near_duplicate() -> None:
    lsh = build_lsh_index()
    # Near-duplicates: same long article body with a single word changed
    original = (
        "Apple CEO Tim Cook announced the new MacBook Pro laptop today at the company's "
        "annual developer conference in Cupertino. The device features the new M4 chip, "
        "which Apple claims delivers a 40 percent performance improvement over the previous "
        "generation. Cook highlighted the improved battery life, noting that users can expect "
        "up to 22 hours of continuous video playback on a single charge."
    )
    near_dup = (
        "Apple CEO Tim Cook announced the new MacBook Pro laptop today at the company's "
        "annual developer conference in Cupertino. The device features the new M4 chip, "
        "which Apple claims delivers a 40 percent performance improvement over the previous "
        "generation. Cook highlighted the improved battery life, noting that users can expect "
        "up to 22 hours of continuous video playback on a single charge. Updated."
    )

    m_orig = compute_minhash(original)
    add_to_index(lsh, "article-001", m_orig)

    m_dup = compute_minhash(near_dup)
    result = find_duplicate(lsh, m_dup)
    assert result == "article-001"


def test_find_no_duplicate_returns_none() -> None:
    lsh = build_lsh_index()
    m = compute_minhash("Tesla reports record earnings.")
    add_to_index(lsh, "art-1", m)

    unrelated = compute_minhash("EU fines Meta for GDPR violations.")
    assert find_duplicate(lsh, unrelated) is None


def test_add_duplicate_key_silently_ignored() -> None:
    lsh = build_lsh_index()
    m = compute_minhash("some content")
    add_to_index(lsh, "art-1", m)
    # Second insert with same key must not raise
    add_to_index(lsh, "art-1", m)


_LONG_BODIES = [
    (
        "Microsoft Azure cloud revenue grew thirty percent year over year in the most recent "
        "quarter, beating Wall Street expectations. The company's chief financial officer "
        "credited enterprise AI workload adoption and expanding data centre capacity. Azure "
        "now accounts for roughly half of Microsoft's total commercial cloud revenue, which "
        "crossed one hundred billion dollars annually for the first time."
    ),
    (
        "Amazon Web Services reported strong quarterly results driven by demand for generative "
        "AI infrastructure. AWS revenue increased twenty-one percent year over year, reaching "
        "twenty-five billion dollars. CEO Andy Jassy said the cloud division continues to "
        "benefit from customers migrating on-premises workloads to the public cloud as part "
        "of multi-year digital transformation programmes."
    ),
    (
        "Google Cloud posted its fastest growth rate in six quarters, with revenue up twenty-nine "
        "percent year over year. The division, led by Thomas Kurian, is benefiting from demand "
        "for Vertex AI services and BigQuery analytics. Alphabet executives noted that Google "
        "Cloud is now consistently profitable and expanding its enterprise customer base globally."
    ),
]


def test_multiple_articles_in_index() -> None:
    lsh = build_lsh_index()
    for i, text in enumerate(_LONG_BODIES):
        add_to_index(lsh, f"art-{i}", compute_minhash(text))

    # Near-duplicate of _LONG_BODIES[0] — same body with one extra sentence appended
    similar = _LONG_BODIES[0] + " Analysts expect continued momentum in subsequent quarters."
    result = find_duplicate(lsh, compute_minhash(similar))
    assert result == "art-0"


# ---------------------------------------------------------------------------
# is_near_duplicate
# ---------------------------------------------------------------------------

def test_is_near_duplicate_identical() -> None:
    text = "Identical article text that should match itself."
    assert is_near_duplicate(text, text) is True


def test_is_near_duplicate_near_identical() -> None:
    # Same long text with only a trailing word changed — well above threshold
    base = (
        "Tesla delivered a record number of electric vehicles in the fourth quarter, "
        "surpassing analyst forecasts by fifteen percent. Elon Musk attributed the results "
        "to improved manufacturing efficiency at the Gigafactory in Texas and strong demand "
        "in the Chinese market. The company plans to introduce the refreshed Model Y in all "
        "major markets during the first half of next year."
    )
    variant = base.replace("first half", "second half")
    assert is_near_duplicate(base, variant) is True


def test_is_near_duplicate_unrelated() -> None:
    a = "Tesla unveils new Cybertruck variant with extended range battery."
    b = "European Central Bank holds interest rates steady amid inflation concerns."
    assert is_near_duplicate(a, b) is False
