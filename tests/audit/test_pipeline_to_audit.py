"""First test that carries a full pipeline run all the way into storage.

Loads the happy_path fixture, runs validation -> matching -> scoring, builds an
AuditEntry, appends it, and reads it back. This is the contract that P1-11b's
dashboard and P1-12's API will rely on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from apmatch.audit.entry import AuditEntry
from apmatch.audit.hashing import compute_input_hash
from apmatch.audit.repository import AuditRepository
from apmatch.matching.engine import MatchingEngine
from apmatch.remarks.matching import summarize_match
from apmatch.scoring.router import decide
from apmatch.validation.arithmetic import validate_invoice
from tests.integration.test_pipeline import _load

SCORE_QUANTUM = Decimal("0.0001")


def _run_pipeline():
    invoice, po, grni, pard = _load("happy_path")
    validation = validate_invoice(invoice)
    match = MatchingEngine().match(invoice, po, grni, pard)
    decision = decide(validation, match)
    remark = summarize_match(match)
    return invoice, po, grni, pard, validation, match, decision, remark


def _build_entry(run_id: str, invoice, po, grni, pard, validation, match, decision, remark) -> AuditEntry:
    return AuditEntry(
        run_id=run_id,
        run_timestamp=datetime.now(UTC),
        invoice_number=invoice.invoice_number,
        po_number=po.po_number,
        grn_number=grni.grn_number,
        pard_ref=pard.pard_number,
        route=decision.route,
        route_reason=decision.reason,
        score_value=Decimal(str(decision.score.value)).quantize(SCORE_QUANTUM),
        remark=remark,
        validation_failures=validation.checks_failed,
        match_failures=match.failures,
        input_hash=compute_input_hash(invoice, po, grni, pard),
    )


def test_full_pipeline_writes_audit_row(pg_session):
    invoice, po, grni, pard, validation, match, decision, remark = _run_pipeline()
    entry = _build_entry(uuid4().hex, invoice, po, grni, pard, validation, match, decision, remark)
    AuditRepository.append(pg_session, entry)
    loaded = AuditRepository.get(pg_session, entry.run_id)
    assert loaded == entry
    assert loaded.route is decision.route
    assert loaded.route_reason is decision.reason
    assert loaded.remark == remark
    assert loaded.input_hash == entry.input_hash
    assert loaded.validation_failures == validation.checks_failed
    assert loaded.match_failures == match.failures
    assert loaded.invoice_number == invoice.invoice_number


def test_same_documents_produce_same_input_hash(pg_session):
    invoice, po, grni, pard, validation, match, decision, remark = _run_pipeline()
    entry1 = _build_entry(uuid4().hex, invoice, po, grni, pard, validation, match, decision, remark)
    entry2 = _build_entry(uuid4().hex, invoice, po, grni, pard, validation, match, decision, remark)
    assert entry1.input_hash == entry2.input_hash
    assert entry1.run_id != entry2.run_id
