"""Deduplication stage: MinHash + LSH near-duplicate detection.

Pure functions — no I/O, no framework imports.  Celery tasks are thin wrappers.

Algorithm:
  - Each article's clean_content is shingled into char 5-grams.
  - MinHash(num_perm=128) approximates Jaccard similarity.
  - MinHashLSH(threshold=0.5) index enables O(1)-ish lookup.

Gray-zone routing (Phase 11 Revised):
  - Similarity ≥ DUPLICATE_THRESHOLD → immediate duplicate (fast path).
  - Similarity < DISTINCT_THRESHOLD  → immediate distinct (fast path).
  - DISTINCT_THRESHOLD ≤ similarity < DUPLICATE_THRESHOLD → gray zone:
      the Celery task routes to the agentic dedup agent for a reasoning decision.

Usage pattern:
  1. Build an LSH index from already-processed articles (or a seed corpus).
  2. For each new article call `find_duplicate(lsh, content)`.
  3. If a duplicate is found, compute jaccard with `compute_jaccard_similarity`.
  4. Route based on `classify_similarity(score)`.
  5. If a duplicate is found, mark the new article's is_duplicate_of FK.
  6. If not a duplicate, add the new article to the index with `add_to_index`.
"""

from __future__ import annotations

from datasketch import MinHash, MinHashLSH  # type: ignore[import-untyped]

_NUM_PERM = 128
_THRESHOLD = 0.5  # LSH index threshold (must be within gray zone or above)
_SHINGLE_SIZE = 5

# ── Gray-zone band ────────────────────────────────────────────────────────────
# Similarity ≥ this → clear duplicate, no LLM.
DUPLICATE_THRESHOLD: float = 0.75
# Similarity < this → clearly distinct, no LLM.
DISTINCT_THRESHOLD: float = 0.55
# Between DISTINCT_THRESHOLD and DUPLICATE_THRESHOLD → gray zone → agentic path.

# Verdict constants
VERDICT_DUPLICATE = "duplicate"
VERDICT_UPDATE = "update"
VERDICT_DISTINCT = "distinct"
VERDICT_GRAY_ZONE = "gray_zone"  # internal: not stored, routes to agentic


def _shingle(text: str, k: int = _SHINGLE_SIZE) -> set[bytes]:
    """Return set of k-char byte shingles from text."""
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) < k:
        return {encoded}
    return {encoded[i : i + k] for i in range(len(encoded) - k + 1)}


def compute_minhash(text: str) -> MinHash:
    """Return a MinHash signature for *text*."""
    m = MinHash(num_perm=_NUM_PERM)
    for shingle in _shingle(text):
        m.update(shingle)
    return m


def compute_jaccard_similarity(text_a: str, text_b: str) -> float:
    """Return the MinHash Jaccard similarity between two texts (0.0–1.0)."""
    ma = compute_minhash(text_a)
    mb = compute_minhash(text_b)
    return float(ma.jaccard(mb))


def classify_similarity(score: float) -> str:
    """Return routing verdict for a MinHash similarity *score*.

    Returns one of:
      VERDICT_DUPLICATE  — score ≥ DUPLICATE_THRESHOLD: fast-path, mark duplicate.
      VERDICT_DISTINCT   — score < DISTINCT_THRESHOLD:  fast-path, treat as new.
      VERDICT_GRAY_ZONE  — in between: route to the agentic dedup agent.
    """
    if score >= DUPLICATE_THRESHOLD:
        return VERDICT_DUPLICATE
    if score < DISTINCT_THRESHOLD:
        return VERDICT_DISTINCT
    return VERDICT_GRAY_ZONE


def build_lsh_index() -> MinHashLSH:
    """Return an empty LSH index with the project-wide threshold."""
    return MinHashLSH(threshold=_THRESHOLD, num_perm=_NUM_PERM)


def add_to_index(lsh: MinHashLSH, article_id: str, minhash: MinHash) -> None:
    """Insert *article_id* into *lsh*; silently skip if already present."""
    import contextlib

    with contextlib.suppress(ValueError):
        lsh.insert(article_id, minhash)


def find_duplicate(lsh: MinHashLSH, minhash: MinHash) -> str | None:
    """Return the ID of the first near-duplicate in *lsh*, or None."""
    results: list[str] = lsh.query(minhash)
    return results[0] if results else None


def is_near_duplicate(text_a: str, text_b: str) -> bool:
    """Convenience: return True if two texts exceed the similarity threshold."""
    ma = compute_minhash(text_a)
    mb = compute_minhash(text_b)
    return bool(ma.jaccard(mb) >= _THRESHOLD)
