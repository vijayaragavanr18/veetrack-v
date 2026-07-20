"""Unit tests: GlinerNerService — mocked model output parsed correctly."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.interfaces.services import NerService
from app.infrastructure.nlp.gliner_service import GlinerNerService, _to_mention

# ---------------------------------------------------------------------------
# _to_mention helper
# ---------------------------------------------------------------------------


def test_to_mention_full_dict() -> None:
    raw = {"text": "Tesla", "label": "organization", "score": 0.92, "start": 5, "end": 10}
    m = _to_mention(raw)
    assert m.text == "Tesla"
    assert m.label == "organization"
    assert m.score == pytest.approx(0.92)
    assert m.start == 5
    assert m.end == 10


def test_to_mention_minimal_dict() -> None:
    m = _to_mention({"text": "Apple", "label": "org", "score": 0.7})
    assert m.text == "Apple"
    assert m.start == 0


def test_to_mention_empty_dict_no_crash() -> None:
    m = _to_mention({})
    assert m.text == ""
    assert m.score == 0.0


# ---------------------------------------------------------------------------
# GlinerNerService satisfies NerService protocol
# ---------------------------------------------------------------------------


def test_gliner_service_satisfies_protocol() -> None:
    assert isinstance(GlinerNerService.__new__(GlinerNerService), NerService)


# ---------------------------------------------------------------------------
# GlinerNerService.extract — mocked model
# ---------------------------------------------------------------------------


def _make_service_with_mock_model(
    predict_return: list[dict],
    batch_return: list[list[dict]] | None = None,
) -> GlinerNerService:
    mock_model = MagicMock()
    mock_model.predict_entities.return_value = predict_return
    if batch_return is not None:
        mock_model.batch_predict_entities.return_value = batch_return

    svc = GlinerNerService.__new__(GlinerNerService)
    svc._model_id = "test-model"
    svc._default_threshold = 0.5
    svc._model = MagicMock(return_value=mock_model)
    return svc


def test_extract_returns_mentions() -> None:
    svc = _make_service_with_mock_model(
        [
            {"text": "Tesla", "label": "organization", "score": 0.91, "start": 0, "end": 5},
            {"text": "Elon Musk", "label": "person", "score": 0.85, "start": 10, "end": 19},
        ]
    )
    mentions = svc.extract("Tesla CEO Elon Musk", ["organization", "person"])
    assert len(mentions) == 2
    assert mentions[0].text == "Tesla"
    assert mentions[1].text == "Elon Musk"


def test_extract_empty_text_returns_empty() -> None:
    svc = _make_service_with_mock_model([])
    mentions = svc.extract("", ["organization"])
    assert mentions == []


def test_extract_empty_labels_returns_empty() -> None:
    svc = _make_service_with_mock_model([])
    mentions = svc.extract("Some text here", [])
    assert mentions == []


def test_extract_maps_score() -> None:
    svc = _make_service_with_mock_model(
        [
            {"text": "Apple", "label": "organization", "score": 0.77},
        ]
    )
    mentions = svc.extract("Apple earnings", ["organization"])
    assert mentions[0].score == pytest.approx(0.77)


# ---------------------------------------------------------------------------
# GlinerNerService.extract_batch — mocked model
# ---------------------------------------------------------------------------


def test_extract_batch_returns_per_text_lists() -> None:
    batch_out = [
        [{"text": "Tesla", "label": "organization", "score": 0.9}],
        [{"text": "Tim Cook", "label": "person", "score": 0.8}],
    ]
    svc = _make_service_with_mock_model([], batch_return=batch_out)
    results = svc.extract_batch(
        ["Tesla news today", "Tim Cook at Apple"],
        ["organization", "person"],
    )
    assert len(results) == 2
    assert results[0][0].text == "Tesla"
    assert results[1][0].text == "Tim Cook"


def test_extract_batch_empty_list_returns_empty() -> None:
    svc = _make_service_with_mock_model([])
    results = svc.extract_batch([], ["organization"])
    assert results == []


def test_extract_batch_whitespace_only_texts() -> None:
    svc = _make_service_with_mock_model([])
    results = svc.extract_batch(["   ", "  "], ["organization"])
    assert results == [[], []]
