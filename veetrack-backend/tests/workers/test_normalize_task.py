"""Unit tests: normalize task — pure normalization logic (no DB/Celery)."""

from __future__ import annotations

from workers.tasks.nlp.normalize import _normalize_article_pure


def test_normalize_plain_english() -> None:
    clean, lang = _normalize_article_pure("The quick brown fox jumps over the lazy dog.")
    assert "The quick brown fox" in clean
    assert lang == "en"


def test_normalize_strips_html_tags() -> None:
    html = "<p>Apple <b>reported</b> record earnings.</p>"
    clean, lang = _normalize_article_pure(html)
    assert "Apple" in clean
    assert "reported" in clean
    assert "<" not in clean
    assert lang == "en"


def test_normalize_html_heavy_article() -> None:
    html = (
        "<html><body>"
        "<h1>Breaking News</h1>"
        "<p>Microsoft acquires startup for $1.2 billion.</p>"
        "<ul><li>Deal closes Q2 2025</li></ul>"
        "</body></html>"
    )
    clean, lang = _normalize_article_pure(html)
    assert "Breaking News" in clean
    assert "Microsoft" in clean
    assert "1.2 billion" in clean
    assert "<" not in clean
    assert lang == "en"


def test_normalize_whitespace_collapsed() -> None:
    text = "Hello   world\n\n\n\nParagraph two."
    clean, _ = _normalize_article_pure(text)
    assert "  " not in clean
    # No more than two consecutive newlines
    assert "\n\n\n" not in clean


def test_normalize_empty_string_defaults() -> None:
    clean, lang = _normalize_article_pure("")
    assert clean == ""
    assert lang == "en"


def test_normalize_script_tag_removed() -> None:
    html = "<p>Content here.</p><script>alert('xss')</script>"
    clean, _ = _normalize_article_pure(html)
    assert "Content here" in clean
    assert "alert" not in clean
