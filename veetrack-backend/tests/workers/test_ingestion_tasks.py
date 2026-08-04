"""Unit tests: ingestion task pure helper _make_dedup_hash.

Tests cover watch_newsdata, watch_rss, and watch_twitter — all three define
an identical _make_dedup_hash(external_id, source_id) helper.
No DB, no Redis, no network.
"""

from __future__ import annotations

import hashlib

# ---------------------------------------------------------------------------
# watch_newsdata._make_dedup_hash
# ---------------------------------------------------------------------------


def test_newsdata_dedup_hash_is_stable() -> None:
    """Same inputs always produce the same hex digest."""
    from workers.tasks.ingestion.watch_newsdata import _make_dedup_hash

    h1 = _make_dedup_hash("abc", "src")
    h2 = _make_dedup_hash("abc", "src")
    assert h1 == h2


def test_newsdata_dedup_hash_different_sources() -> None:
    """Same external_id but different source_id produces different hashes."""
    from workers.tasks.ingestion.watch_newsdata import _make_dedup_hash

    assert _make_dedup_hash("abc", "src1") != _make_dedup_hash("abc", "src2")


def test_newsdata_dedup_hash_different_external_ids() -> None:
    """Different external_id with same source_id produces different hashes."""
    from workers.tasks.ingestion.watch_newsdata import _make_dedup_hash

    assert _make_dedup_hash("id-1", "src") != _make_dedup_hash("id-2", "src")


def test_newsdata_dedup_hash_is_hex_string_of_64_chars() -> None:
    """The hash is a 64-character lowercase hex string (SHA-256)."""
    from workers.tasks.ingestion.watch_newsdata import _make_dedup_hash

    h = _make_dedup_hash("some-id", "some-source")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_newsdata_dedup_hash_matches_manual_sha256() -> None:
    """Hash matches manual sha256(source_id:external_id)."""
    from workers.tasks.ingestion.watch_newsdata import _make_dedup_hash

    expected = hashlib.sha256(b"mysource:myid").hexdigest()
    assert _make_dedup_hash("myid", "mysource") == expected


# ---------------------------------------------------------------------------
# watch_rss._make_dedup_hash
# ---------------------------------------------------------------------------


def test_rss_dedup_hash_is_stable() -> None:
    """RSS dedup hash is deterministic for the same inputs."""
    from workers.tasks.ingestion.watch_rss import _make_dedup_hash

    h1 = _make_dedup_hash("link-1", "rss-src")
    h2 = _make_dedup_hash("link-1", "rss-src")
    assert h1 == h2


def test_rss_dedup_hash_different_sources() -> None:
    """RSS: same external_id, different source_id → different hashes."""
    from workers.tasks.ingestion.watch_rss import _make_dedup_hash

    assert _make_dedup_hash("link-1", "src-a") != _make_dedup_hash("link-1", "src-b")


def test_rss_dedup_hash_matches_manual_sha256() -> None:
    """RSS hash matches manual sha256(source_id:external_id)."""
    from workers.tasks.ingestion.watch_rss import _make_dedup_hash

    expected = hashlib.sha256(b"rss-feed:entry-42").hexdigest()
    assert _make_dedup_hash("entry-42", "rss-feed") == expected


# ---------------------------------------------------------------------------
# watch_twitter._make_dedup_hash
# ---------------------------------------------------------------------------


def test_twitter_dedup_hash_is_stable() -> None:
    """Twitter dedup hash is deterministic for the same inputs."""
    from workers.tasks.ingestion.watch_twitter import _make_dedup_hash

    h1 = _make_dedup_hash("tweet-99", "twit-src")
    h2 = _make_dedup_hash("tweet-99", "twit-src")
    assert h1 == h2


def test_twitter_dedup_hash_different_sources() -> None:
    """Twitter: same external_id, different source_id → different hashes."""
    from workers.tasks.ingestion.watch_twitter import _make_dedup_hash

    assert _make_dedup_hash("tweet-99", "src-1") != _make_dedup_hash("tweet-99", "src-2")


def test_twitter_dedup_hash_matches_manual_sha256() -> None:
    """Twitter hash matches manual sha256(source_id:external_id)."""
    from workers.tasks.ingestion.watch_twitter import _make_dedup_hash

    expected = hashlib.sha256(b"twitter-src:tweet-007").hexdigest()
    assert _make_dedup_hash("tweet-007", "twitter-src") == expected


# ---------------------------------------------------------------------------
# Cross-connector consistency
# ---------------------------------------------------------------------------


def test_all_three_connectors_use_same_algorithm() -> None:
    """All three connectors produce identical hashes for identical inputs."""
    from workers.tasks.ingestion.watch_newsdata import _make_dedup_hash as nd_hash
    from workers.tasks.ingestion.watch_rss import _make_dedup_hash as rss_hash
    from workers.tasks.ingestion.watch_twitter import _make_dedup_hash as tw_hash

    ext_id = "shared-id-xyz"
    source = "shared-source"
    assert nd_hash(ext_id, source) == rss_hash(ext_id, source) == tw_hash(ext_id, source)
