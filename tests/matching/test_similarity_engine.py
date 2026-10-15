"""Tests for the embedding-similarity fallback in MatchingEngine (EMB-06).

Stub-based tests are fast and deterministic; one slow test uses the real
vendored model. The stub table keys are NORMALIZED texts — the engine
normalizes both sides before calling similarity().
"""

from datetime import date
from decimal import Decimal

import pytest

from apmatch.embeddings.config import SIMILARITY_ACCEPT, SIMILARITY_REVIEW
from apmatch.matching.engine import MatchingEngine
from apmatch.matching.result import MatchCode, Outcome
from apmatch.schema.documents import GRNI, Invoice, LineItem, PaymentAdvice, PurchaseOrder
from apmatch.validation.result import Severity
from tests.matching._stub_embedding import StubEmbeddingModel


def _line(no, desc, qty="1", price=None, amount=None):
    return LineItem(
        line_no=no,
        description=desc,
        quantity=Decimal(qty),
        unit_price=Decimal(price) if price is not None else None,
        amount=Decimal(amount) if amount is not None else None,
    )


def _invoice(lines, vendor="Mekong Supplies Co., Ltd.", currency="USD", total="100.00"):
    return Invoice("INV-1", vendor, date(2026, 8, 20), currency, Decimal("90.00"), Decimal("10.00"), Decimal(total), lines)


def _po(lines, vendor="Mekong Supplies Co., Ltd.", currency=None):
    return PurchaseOrder("PO-1", vendor, date(2026, 8, 15), Decimal("100.00"), lines, currency)


def _grni(lines, vendor="Mekong Supplies Co., Ltd."):
    return GRNI("GRN-1", vendor, date(2026, 8, 19), lines)


def _pard(amount="100.00", currency=None):
    return PaymentAdvice("PARD-1", "INV-1", Decimal(amount), date(2026, 8, 25), "REF", currency)


def _codes(result):
    return [f.code for f in result.failures]


def test_exact_match_takes_precedence_over_similarity():
    # Two candidates: one exact, one similar-but-not-exact.
    # Exact must win and no SimilarityMatch may be recorded.
    stub = StubEmbeddingModel({("office chair", "chair office metal frame"): 0.95})
    engine = MatchingEngine(embedding_model=stub)
    inv = _invoice((_line(1, "Office Chair", "1", "10.00", "10.00"),))
    po = _po((_line(1, "Office Chair", "1", "10.00"), _line(2, "Chair office metal frame", "1", "10.00")))
    grni = _grni((_line(1, "Office Chair", "1"),))
    r = engine.match(inv, po, grni, _pard())
    assert r.outcome is Outcome.MATCH
    assert MatchCode.SIMILARITY_MATCH_REVIEW not in _codes(r)
    assert r.similarity_matches == ()


def test_similarity_accept_band_matches_without_failure():
    stub = StubEmbeddingModel({("widget alpha", "widget alpha deluxe"): 0.85})
    engine = MatchingEngine(embedding_model=stub)
    inv = _invoice((_line(1, "Widget Alpha", "1", "10.00", "10.00"),))
    po = _po((_line(1, "Widget Alpha Deluxe", "1", "10.00"),))
    grni = _grni((_line(1, "Widget Alpha", "1"),))
    r = engine.match(inv, po, grni, _pard())
    assert MatchCode.NO_MATCHING_PO_LINE not in _codes(r)
    assert MatchCode.SIMILARITY_MATCH_REVIEW not in _codes(r)
    assert r.outcome is Outcome.MATCH
    assert len(r.similarity_matches) == 1
    sim = r.similarity_matches[0]
    assert sim.band == "accept"
    assert sim.score == Decimal("0.8500")
    assert sim.location == "line 1 (INV) -> line 1 (PO)"


def test_similarity_review_band_matches_with_warning():
    stub = StubEmbeddingModel({("widget alpha", "widget alpha deluxe"): 0.60})
    engine = MatchingEngine(embedding_model=stub)
    inv = _invoice((_line(1, "Widget Alpha", "1", "10.00", "10.00"),))
    po = _po((_line(1, "Widget Alpha Deluxe", "1", "10.00"),))
    grni = _grni((_line(1, "Widget Alpha", "1"),))
    r = engine.match(inv, po, grni, _pard())
    assert MatchCode.NO_MATCHING_PO_LINE not in _codes(r)
    assert MatchCode.SIMILARITY_MATCH_REVIEW in _codes(r)
    warn = next(f for f in r.failures if f.code is MatchCode.SIMILARITY_MATCH_REVIEW)
    assert warn.severity is Severity.WARNING
    assert warn.expected == "widget alpha deluxe"
    assert warn.actual == "widget alpha"
    assert r.similarity_matches[0].band == "review"
    assert r.outcome is Outcome.DISCREPANCY


def test_similarity_below_review_is_no_match():
    stub = StubEmbeddingModel({("widget alpha", "widget alpha deluxe"): 0.40})
    engine = MatchingEngine(embedding_model=stub)
    inv = _invoice((_line(1, "Widget Alpha", "1", "10.00", "10.00"),))
    po = _po((_line(1, "Widget Alpha Deluxe", "1", "10.00"),))
    grni = _grni((_line(1, "Widget Alpha", "1"),))
    r = engine.match(inv, po, grni, _pard())
    assert MatchCode.NO_MATCHING_PO_LINE in _codes(r)
    assert r.similarity_matches == ()


def test_similarity_disabled_when_no_model():
    engine = MatchingEngine()
    inv = _invoice((_line(1, "Widget Alpha", "1", "10.00", "10.00"),))
    po = _po((_line(1, "Widget Alpha Deluxe", "1", "10.00"),))
    grni = _grni((_line(1, "Widget Alpha", "1"),))
    r = engine.match(inv, po, grni, _pard())
    assert MatchCode.NO_MATCHING_PO_LINE in _codes(r)
    assert r.similarity_matches == ()


def test_similarity_match_records_model_version():
    stub = StubEmbeddingModel({("widget alpha", "widget alpha deluxe"): 0.85})
    engine = MatchingEngine(embedding_model=stub)
    inv = _invoice((_line(1, "Widget Alpha", "1", "10.00", "10.00"),))
    po = _po((_line(1, "Widget Alpha Deluxe", "1", "10.00"),))
    grni = _grni((_line(1, "Widget Alpha", "1"),))
    r = engine.match(inv, po, grni, _pard())
    assert r.similarity_matches[0].model_version == StubEmbeddingModel.model_version


def test_similarity_match_records_both_thresholds():
    stub = StubEmbeddingModel({("widget alpha", "widget alpha deluxe"): 0.85})
    engine = MatchingEngine(embedding_model=stub)
    inv = _invoice((_line(1, "Widget Alpha", "1", "10.00", "10.00"),))
    po = _po((_line(1, "Widget Alpha Deluxe", "1", "10.00"),))
    grni = _grni((_line(1, "Widget Alpha", "1"),))
    r = engine.match(inv, po, grni, _pard())
    sim = r.similarity_matches[0]
    assert sim.threshold_review == SIMILARITY_REVIEW
    assert sim.threshold_accept == SIMILARITY_ACCEPT


def test_similarity_ties_broken_by_line_no():
    # Two candidates with equal score -> lower line_no wins.
    stub = StubEmbeddingModel({("widget alpha", "beta"): 0.80, ("widget alpha", "alpha"): 0.80})
    engine = MatchingEngine(embedding_model=stub)
    inv = _invoice((_line(1, "Widget Alpha", "1", "10.00", "10.00"),))
    po = _po((_line(2, "Beta", "1", "10.00"), _line(1, "Alpha", "1", "10.00")))
    grni = _grni((_line(1, "Widget Alpha", "1"),))
    r = engine.match(inv, po, grni, _pard())
    sim = r.similarity_matches[0]
    assert sim.counterpart_text == "alpha"
    assert sim.location == "line 1 (INV) -> line 1 (PO)"


def test_similarity_grn_independent_from_po():
    # The invoice line matches differently against PO (accept) and GRN (review).
    stub = StubEmbeddingModel(
        {("widget alpha", "widget alpha po"): 0.85, ("widget alpha", "widget alpha grn"): 0.60}
    )
    engine = MatchingEngine(embedding_model=stub)
    inv = _invoice((_line(1, "Widget Alpha", "1", "10.00", "10.00"),))
    po = _po((_line(1, "Widget Alpha Po", "1", "10.00"),))
    grni = _grni((_line(1, "Widget Alpha Grn", "1"),))
    r = engine.match(inv, po, grni, _pard())
    assert len(r.similarity_matches) == 2
    by_loc = {s.location: s for s in r.similarity_matches}
    assert "line 1 (INV) -> line 1 (PO)" in by_loc
    assert "line 1 (INV) -> line 1 (GRN)" in by_loc
    assert by_loc["line 1 (INV) -> line 1 (PO)"].band == "accept"
    assert by_loc["line 1 (INV) -> line 1 (GRN)"].band == "review"
    # Only the GRN review-band match emits a warning.
    warns = [f for f in r.failures if f.code is MatchCode.SIMILARITY_MATCH_REVIEW]
    assert len(warns) == 1
    assert warns[0].location == "line 1 (INV) -> line 1 (GRN)"


def test_empty_candidate_list():
    stub = StubEmbeddingModel({("widget alpha", "anything"): 0.95})
    engine = MatchingEngine(embedding_model=stub)
    inv = _invoice((_line(1, "Widget Alpha", "1", "10.00", "10.00"),))
    po = _po(())
    grni = _grni((_line(1, "Widget Alpha", "1"),))
    r = engine.match(inv, po, grni, _pard())
    assert MatchCode.NO_MATCHING_PO_LINE in _codes(r)
    assert r.similarity_matches == ()


@pytest.mark.slow
def test_real_model_semantic_match():
    # Real vendored model: paraphrase pair must land in the accept band.
    from apmatch.embeddings.model import EmbeddingModel

    engine = MatchingEngine(embedding_model=EmbeddingModel())
    inv = _invoice((_line(1, "Office Chair", "1", "10.00", "10.00"),))
    po = _po((_line(1, "Chair, office, metal frame, black", "1", "10.00"),))
    grni = _grni((_line(1, "Office Chair", "1"),))
    r = engine.match(inv, po, grni, _pard())
    assert MatchCode.NO_MATCHING_PO_LINE not in _codes(r)
    assert len(r.similarity_matches) == 1
    sim = r.similarity_matches[0]
    assert sim.band == "accept"
    assert sim.score >= SIMILARITY_ACCEPT
    assert len(sim.model_version) == 64
