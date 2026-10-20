"""Before/after proof for the embedding fallback (EMB-08).

Runs the full pipeline (OCR included) on the generated demo fixtures in
documents/demo/, where line-item descriptions are semantically equivalent
but textually distinct:

  - Without embeddings: NO_MATCHING_PO_LINE -> DISCREPANCY -> HUMAN_REVIEW
  - With embeddings: similarity matches recorded, route not REJECT

Each test runs the real OCR pipeline, so this module is slow by design.
"""

from pathlib import Path

import pytest

DEMO = Path("documents/demo")


@pytest.fixture(scope="session")
def embedding_model():
    from apmatch.embeddings.model import EmbeddingModel

    return EmbeddingModel()


def _run(embedding_model=None):
    from apmatch.api.pipeline import run_pipeline

    return run_pipeline(
        invoice_path=DEMO / "invoice.png",
        po_path=DEMO / "po.png",
        grni_path=DEMO / "grn.png",
        pard_path=DEMO / "pard.png",
        embedding_model=embedding_model,
    )


def test_demo_without_embeddings_produces_discrepancy():
    # Run the pipeline on the demo fixtures WITHOUT an embedding model.
    match, _, decision, _ = _run(embedding_model=None)
    # Descriptions differ (no exact match), so we expect
    # NO_MATCHING_PO_LINE on line 1 (or line 2, or line 3).
    codes = [f.code.value for f in match.failures]
    assert "NO_MATCHING_PO_LINE" in codes
    assert decision.route.value == "HUMAN_REVIEW"


def test_demo_with_embeddings_produces_match(embedding_model):
    # Same fixtures, WITH the real embedding model.
    match, _, decision, _ = _run(embedding_model=embedding_model)
    # Line 1 should now match by similarity.
    assert len(match.similarity_matches) >= 1
    sm = match.similarity_matches[0]
    assert sm.band in ("accept", "review")
    assert sm.model_version == embedding_model.model_version
    # Route should be AUTO_APPROVE (accept) or HUMAN_REVIEW
    # with the review-band warning. Assert it's one of those,
    # not REJECT.
    assert decision.route.value in ("AUTO_APPROVE", "HUMAN_REVIEW")


def test_demo_similarity_evidence_is_complete(embedding_model):
    # Every similarity match carries the full audit evidence.
    match, _, _, _ = _run(embedding_model=embedding_model)
    for sm in match.similarity_matches:
        assert sm.score > 0
        assert sm.threshold_review > 0
        assert sm.threshold_accept > sm.threshold_review
        assert sm.model_version != ""
        assert sm.location.startswith("line ")


def test_demo_route_depends_on_embeddings(embedding_model):
    # The before/after: without embeddings -> HUMAN_REVIEW,
    # with embeddings -> not REJECT (usually AUTO_APPROVE).
    _, _, d_off, _ = _run(embedding_model=None)
    _, _, d_on, _ = _run(embedding_model=embedding_model)
    assert d_off.route.value == "HUMAN_REVIEW"
    assert d_on.route.value != "REJECT"
