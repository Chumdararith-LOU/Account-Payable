"""Pipeline orchestrator: images -> OCR -> parse -> validate -> match -> score -> audit entry.

Shared by the /match endpoint and the full-stack smoke test. Deterministic
except ``run_id`` (UUID4) and ``run_timestamp`` (wall clock) — both are audit
metadata, never decision inputs. This function does NOT write to the DB; the
caller (the endpoint) owns the session and the commit.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from apmatch.audit.entry import AuditEntry
from apmatch.audit.hashing import compute_input_hash
from apmatch.layout.structure import LayoutEngine
from apmatch.matching.engine import MatchingEngine
from apmatch.matching.result import MatchResult, Outcome
from apmatch.ocr.router import OCRRouter
from apmatch.parse import dispatch
from apmatch.remarks.matching import summarize_match
from apmatch.remarks.templates import summarize
from apmatch.scoring.result import RoutingDecision
from apmatch.scoring.router import decide
from apmatch.validation.arithmetic import validate_invoice
from apmatch.validation.result import ValidationResult

logger = logging.getLogger("apmatch.api.pipeline")


def _recognize_and_parse(router: OCRRouter, layout: LayoutEngine, kind, path: Path, ocr_debug: bool):
    ocr_result = router.recognize(path)
    tables = layout.extract(path)
    ocr_result = replace(ocr_result, tables=tables)  # OCRResult is frozen
    if ocr_debug:
        logger.info("ocr blocks=%d tables=%d", len(ocr_result.text_blocks), len(tables))
    return dispatch.extract(kind, ocr_result)


def run_pipeline(
    invoice_path: Path,
    po_path: Path | None = None,
    grni_path: Path | None = None,
    pard_path: Path | None = None,
    *,
    router: OCRRouter | None = None,
    layout: LayoutEngine | None = None,
    embedding_model=None,
    ocr_debug: bool = False,
) -> tuple[MatchResult, ValidationResult, RoutingDecision, AuditEntry]:
    """Run the full deterministic chain over up to four document images.

    ``router``/``layout`` are heavy to construct; pass pre-built instances
    (the endpoint builds them once at startup). If omitted, they are built
    here. ``embedding_model`` (duck-typed; needs .similarity() and
    .model_version) enables the similarity fallback in the matching engine;
    None keeps the exact-match-only behavior.
    """
    router = router or OCRRouter()
    layout = layout or LayoutEngine()

    invoice = _recognize_and_parse(router, layout, dispatch.DocumentKind.INVOICE, invoice_path, ocr_debug)
    po = _recognize_and_parse(router, layout, dispatch.DocumentKind.PURCHASE_ORDER, po_path, ocr_debug) if po_path else None
    grni = _recognize_and_parse(router, layout, dispatch.DocumentKind.GRNI, grni_path, ocr_debug) if grni_path else None
    pard = _recognize_and_parse(router, layout, dispatch.DocumentKind.PAYMENT_ADVICE, pard_path, ocr_debug) if pard_path else None

    validation = validate_invoice(invoice)
    match = MatchingEngine(embedding_model=embedding_model).match(invoice, po, grni, pard)
    decision = decide(validation, match, ocr_confidence=None)

    # Reviewer-facing remark rule (D-052): for a MATCH outcome the
    # validation summary is what the reviewer needs (the match is clean);
    # for non-MATCH the match summary explains the discrepancy. The two
    # remark modules (templates.py, matching.py) remain independent.
    remark = summarize(validation) if match.outcome is Outcome.MATCH else summarize_match(match)

    audit_entry = AuditEntry(
        run_id=uuid4().hex,
        run_timestamp=datetime.now(timezone.utc),
        invoice_number=invoice.invoice_number,
        po_number=po.po_number if po else None,
        grn_number=grni.grn_number if grni else None,
        pard_ref=pard.pard_number if pard else None,
        route=decision.route,
        route_reason=decision.reason,
        score_value=Decimal(str(decision.score.value)).quantize(Decimal("0.0001")),
        remark=remark,
        validation_failures=validation.checks_failed,
        match_failures=match.failures,
        input_hash=compute_input_hash(invoice, po, grni, pard),
        similarity_matches=match.similarity_matches,
    )
    return match, validation, decision, audit_entry
