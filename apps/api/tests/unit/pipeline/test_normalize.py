"""Unit tests for normalize.py — pure functions, no I/O."""

from __future__ import annotations

from app.application.use_cases.pipeline.normalize import (
    clean_whitespace,
    normalize_article,
    strip_html,
)

# ---------------------------------------------------------------------------
# strip_html
# ---------------------------------------------------------------------------

def test_strip_html_basic_tags() -> None:
    html = "<p>Hello <b>world</b>!</p>"
    result = strip_html(html)
    assert "Hello" in result
    assert "world" in result
    assert "<" not in result


def test_strip_html_nested_structure() -> None:
    html = "<div><h1>Title</h1><p>Para one.</p><p>Para two.</p></div>"
    result = strip_html(html)
    assert "Title" in result
    assert "Para one" in result
    assert "Para two" in result
    assert "<" not in result


def test_strip_html_entities_decoded() -> None:
    html = "<p>AT&amp;T raised &lt;$100M&gt;</p>"
    result = strip_html(html)
    assert "AT&T" in result
    assert "<$100M>" in result


def test_strip_html_script_removed() -> None:
    html = "<p>Content</p><script>alert('xss')</script>"
    result = strip_html(html)
    assert "Content" in result
    assert "alert" not in result


def test_strip_html_plain_text_passthrough() -> None:
    plain = "No tags here."
    assert "No tags here." in strip_html(plain)


# ---------------------------------------------------------------------------
# clean_whitespace
# ---------------------------------------------------------------------------

def test_clean_whitespace_collapses_spaces() -> None:
    assert clean_whitespace("hello   world") == "hello world"


def test_clean_whitespace_strips_edges() -> None:
    assert clean_whitespace("  hi  ") == "hi"


def test_clean_whitespace_tabs_to_space() -> None:
    result = clean_whitespace("a\t\tb")
    assert result == "a b"


def test_clean_whitespace_triple_newlines_collapsed() -> None:
    result = clean_whitespace("para1\n\n\n\npara2")
    assert result == "para1\n\npara2"


def test_clean_whitespace_unicode_normalised() -> None:
    # Full-width space U+3000 → normalized to regular space
    result = clean_whitespace("hello　world")
    assert "hello" in result and "world" in result


# ---------------------------------------------------------------------------
# normalize_article
# ---------------------------------------------------------------------------

def test_normalize_article_strips_html_and_returns_language() -> None:
    html = "<p>Apple announced record quarterly earnings today.</p>"
    clean, lang = normalize_article(html)
    assert "Apple" in clean
    assert "<" not in clean
    assert lang  # non-empty language code


def test_normalize_article_plain_english_detected() -> None:
    text = "The quick brown fox jumps over the lazy dog."
    clean, lang = normalize_article(text)
    assert lang == "en"


def test_normalize_article_empty_returns_defaults() -> None:
    clean, lang = normalize_article("")
    assert clean == ""
    assert lang == "en"


def test_normalize_article_html_heavy_content() -> None:
    html = (
        "<!DOCTYPE html><html><head><title>Test</title></head>"
        "<body><h1>Headline</h1><p>First paragraph.</p>"
        "<ul><li>Item 1</li><li>Item 2</li></ul></body></html>"
    )
    clean, lang = normalize_article(html)
    assert "Headline" in clean
    assert "First paragraph" in clean
    assert "Item 1" in clean
    assert "<" not in clean
    assert lang == "en"


def test_normalize_article_whitespace_normalized_in_output() -> None:
    html = "<p>Hello   world</p>"
    clean, _ = normalize_article(html)
    # Multiple spaces should be collapsed
    assert "  " not in clean
