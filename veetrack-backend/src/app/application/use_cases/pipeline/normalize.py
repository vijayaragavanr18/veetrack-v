"""Normalization stage: HTML stripping, whitespace cleanup, language detection.

Pure functions — no I/O, no framework imports.  Celery tasks are thin wrappers.
"""

from __future__ import annotations

import re
import unicodedata

import structlog

logger = structlog.get_logger(__name__)

# lazy imports so tests can run without these optional deps
_bs4: object | None = None
_langdetect: object | None = None


def _get_bs4() -> object:
    global _bs4
    if _bs4 is None:
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]

        _bs4 = BeautifulSoup
    return _bs4


def _detect_language(text: str) -> str:
    """Return BCP-47 language code; default 'en' if detection fails."""
    global _langdetect
    if _langdetect is None:
        from langdetect import DetectorFactory, detect  # type: ignore[import-untyped]

        DetectorFactory.seed = 0
        _langdetect = detect

    detect_fn = _langdetect  # narrow type for mypy
    if not callable(detect_fn):  # pragma: no cover
        return "en"

    try:
        return str(detect_fn(text[:2000]))
    except Exception:
        return "en"


def strip_html(raw: str) -> str:
    """Strip HTML tags; return plain text with whitespace normalized."""
    BeautifulSoup = _get_bs4()
    soup = BeautifulSoup(raw, "lxml")  # type: ignore[call-arg,operator]
    text: str = soup.get_text(separator=" ")
    return text


def clean_whitespace(text: str) -> str:
    """Normalize unicode, collapse whitespace, strip leading/trailing space."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_article(raw_content: str) -> tuple[str, str]:
    """Return (clean_content, language_code) for one article.

    clean_content — HTML stripped, whitespace normalized plain text
    language_code — BCP-47 code detected from the first 2 000 chars
    """
    plain = strip_html(raw_content)
    clean = clean_whitespace(plain)
    lang = _detect_language(clean) if clean else "en"
    return clean, lang
