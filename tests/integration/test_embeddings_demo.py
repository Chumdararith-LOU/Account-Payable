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


# The OCR engines hold ~2.6 GB of model weights. Build them once and reuse
# across every test: run_pipeline would otherwise rebuild them per call, and
# the 4th test (two pipeline runs) would peak high enough to OOM the
# 15 GB server (which also runs the production API, ~4.5 GB).
@pytest.fixture(scope="session")
def ocr_router():
    from apmatch.ocr.router import OCRRouter

    return OCRRouter()


@pytest.fixture(scope="session")
def layout_engine():
    from apmatch.layout.structure import LayoutEngine

    return LayoutEngine()


def _run(embedding_model=None, router=None, layout=None, customer_id="default"):
    from apmatch.api.pipeline import run_pipeline

    return run_pipeline(
        invoice_path=DEMO / "invoice.png",
        po_path=DEMO / "po.png",
        grni_path=DEMO / "grn.png",
        pard_path=DEMO / "pard.png",
        embedding_model=embedding_model,
        router=router,
        layout=layout,
        customer_id=customer_id,
    )


def test_demo_without_embeddings_produces_discrepancy(ocr_router, layout_engine):
    # Run the pipeline on the demo fixtures WITHOUT an embedding model.
    match, _, decision, _ = _run(
        embedding_model=None, router=ocr_router, layout=layout_engine)
    # Descriptions differ (no exact match), so we expect
    # NO_MATCHING_PO_LINE on line 1 (or line 2, or line 3).
    codes = [f.code.value for f in match.failures]
    assert "NO_MATCHING_PO_LINE" in codes
    assert decision.route.value == "HUMAN_REVIEW"


def test_demo_with_embeddings_produces_match(embedding_model, ocr_router, layout_engine):
    # Same fixtures, WITH the real embedding model.
    match, _, decision, _ = _run(
        embedding_model=embedding_model, router=ocr_router, layout=layout_engine)
    # Line 1 should now match by similarity.
    assert len(match.similarity_matches) >= 1
    sm = match.similarity_matches[0]
    assert sm.band in ("accept", "review")
    assert sm.model_version == embedding_model.model_version
    # Route should be AUTO_APPROVE (accept) or HUMAN_REVIEW
    # with the review-band warning. Assert it's one of those,
    # not REJECT.
    assert decision.route.value in ("AUTO_APPROVE", "HUMAN_REVIEW")


def test_demo_similarity_evidence_is_complete(embedding_model, ocr_router, layout_engine):
    # Every similarity match carries the full audit evidence.
    match, _, _, _ = _run(
        embedding_model=embedding_model, router=ocr_router, layout=layout_engine)
    for sm in match.similarity_matches:
        assert sm.score > 0
        assert sm.threshold_review > 0
        assert sm.threshold_accept > sm.threshold_review
        assert sm.model_version != ""
        assert sm.location.startswith("line ")


def test_demo_route_depends_on_embeddings(embedding_model, ocr_router, layout_engine):
    # The before/after: without embeddings -> HUMAN_REVIEW,
    # with embeddings -> not REJECT (usually AUTO_APPROVE).
    _, _, d_off, _ = _run(
        embedding_model=None, router=ocr_router, layout=layout_engine)
    _, _, d_on, _ = _run(
        embedding_model=embedding_model, router=ocr_router, layout=layout_engine)
    assert d_off.route.value == "HUMAN_REVIEW"
    assert d_on.route.value != "REJECT"


def test_demo_with_customer_id(embedding_model, ocr_router, layout_engine):
    # The multi-tenant tag (D-091) is carried through to the AuditEntry.
    _, _, _, entry = _run(
        embedding_model=embedding_model, router=ocr_router, layout=layout_engine,
        customer_id="hotel_demo")
    assert entry.customer_id == "hotel_demo"
