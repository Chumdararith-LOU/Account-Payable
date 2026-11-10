"""Pipeline orchestrator: images -> extract -> derive -> validate -> match -> score -> audit entry.

Extraction is the only non-deterministic step (a VLM reads the document, with
the OCR heuristics as fallback). Its output is recorded (``_extraction`` in the
returned sidecar), and everything after it is pure code (D-109): given the same
extracted documents, the decision is always the same. ``run_id`` (UUID4) and
``run_timestamp`` (wall clock) are audit metadata, never decision inputs. This function does NOT write to the DB; the
caller (the endpoint) owns the session and the commit.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from apmatch.audit.entry import AuditEntry
from apmatch.audit.hashing import _canonical, canonical_documents, compute_input_hash
from apmatch.matching.engine import MatchingEngine
from apmatch.matching.result import MatchResult, Outcome
from apmatch.parse import dispatch
from apmatch.parse import vlm as vlm_module
from apmatch.parse.derive import derive
from apmatch.parse.reconcile import reconcile
from apmatch.remarks.matching import summarize_match
from apmatch.remarks.templates import summarize
from apmatch.schema.serialize import document_from_dict
from apmatch.scoring.result import RoutingDecision
from apmatch.scoring.router import decide
from apmatch.validation.arithmetic import validate_invoice
from apmatch.validation.result import ValidationResult

logger = logging.getLogger("apmatch.api.pipeline")

# DocumentKind -> key used by canonical_documents() / the audit sidecar.
_DOC_KEY = {
    dispatch.DocumentKind.INVOICE: "invoice",
    dispatch.DocumentKind.PURCHASE_ORDER: "po",
    dispatch.DocumentKind.GRNI: "grni",
    dispatch.DocumentKind.PAYMENT_ADVICE: "pard",
}

# Bump when the OCR-heuristic extractors change in a way that should
# invalidate cached heuristic extractions.
HEURISTIC_VERSION = "2026-11-08.1"


def extraction_backend() -> str:
    """'vlm' (default: VLM first, OCR heuristics as fallback) or 'ocr' (heuristics only)."""
    value = os.getenv("EXTRACTION_BACKEND", "vlm").strip().lower()
    return "ocr" if value in ("ocr", "heuristic") else "vlm"


class _Engines:
    """OCR router + layout engine, built only if the heuristic path is needed."""

    def __init__(self, router=None, layout=None):
        self._router = router
        self._layout = layout

    @property
    def router(self):
        if self._router is None:
            from apmatch.ocr.router import OCRRouter

            self._router = OCRRouter()
        return self._router

    @property
    def layout(self):
        if self._layout is None:
            from apmatch.layout.structure import LayoutEngine

            self._layout = LayoutEngine()
        return self._layout


def _heuristic(engines: _Engines, kind, path: Path, ocr_debug: bool):
    ocr_result = engines.router.recognize(path)
    tables = engines.layout.extract(path)
    ocr_result = replace(ocr_result, tables=tables)  # OCRResult is frozen
    if ocr_debug:
        logger.info("ocr blocks=%d tables=%d", len(ocr_result.text_blocks), len(tables))
    return dispatch.extract(kind, ocr_result)


def _cache_path(cache_dir: Path, kind, path: Path, backend: str) -> Path:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if backend == "vlm":
        version = f"vlm|{vlm_module.VLM_MODEL}|{vlm_module.prompt_version(kind)}"
    else:
        version = f"ocr|{HEURISTIC_VERSION}"
    key = hashlib.sha256(f"{digest}|{kind.value}|{version}".encode()).hexdigest()[:32]
    return cache_dir / f"{key}.json"


def _vlm_from_raw(kind, raw: str):
    """Re-parse a stored raw model reply with the CURRENT parsing code."""
    field_errors: list[str] = []
    data = vlm_module.parse_model_json(raw)
    doc = vlm_module.document_from_payload(kind, data, field_errors)
    return doc, field_errors, vlm_module.date_candidates(kind, data)


def _recognize_and_parse(engines: _Engines, kind, path: Path, ocr_debug: bool, cache_dir: Path | None = None):
    """Returns (document, info). info["source"] is "vlm" or "heuristic".

    The returned document is the RAW extraction (before derivation); the
    caller applies ``derive`` and ``reconcile``. With ``cache_dir`` set,
    extractions are cached per (file content, kind, backend, model, prompt
    version). For VLM extractions the cache holds the model's raw reply and
    re-parses it on every hit, so a parsing fix takes effect without calling
    the model again.
    """
    backend = extraction_backend()
    cache_file = _cache_path(cache_dir, kind, path, backend) if cache_dir else None
    if cache_file is not None and cache_file.is_file():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        info = dict(cached["info"], cache="hit")
        # PROD-B3 cache files kept the raw reply only inside info["vlm"].
        raw = cached.get("raw_output") or ((info.get("vlm") or {}).get("raw_output"))
        if info.get("source") == "vlm" and raw:
            doc, field_errors, cands = _vlm_from_raw(kind, raw)
            info["vlm"] = dict(info["vlm"] or {}, field_errors=field_errors,
                               date_candidates=[d.isoformat() for d in cands])
            return doc, info
        return document_from_dict(_DOC_KEY[kind], cached["document"]), info

    info: dict = {"source": None, "vlm": None, "cache": "miss" if cache_file else None}
    doc = None
    raw_output = None
    if backend == "vlm":
        result = vlm_module.extract_vlm_detailed(kind, path)
        info["vlm"] = result.summary()
        if result.document is not None:
            doc = result.document
            raw_output = result.raw_output
            info["source"] = "vlm"
        else:
            # Loud on purpose: a silent fallback hides VLM outages (PROD-B2).
            logger.error("VLM FAILED for %s (%s). Falling back to OCR.", path.name, result.error)
    if doc is None:
        doc = _heuristic(engines, kind, path, ocr_debug)
        info["source"] = "heuristic"

    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps({"document": _canonical(doc), "info": info, "raw_output": raw_output},
                       ensure_ascii=False),
            encoding="utf-8",
        )
    return doc, info


def date_candidates_from_infos(infos: dict) -> dict[str, list]:
    """Per-document date readings recorded by the VLM extraction."""
    out: dict[str, list] = {}
    for key, info in infos.items():
        cands = ((info or {}).get("vlm") or {}).get("date_candidates") or []
        if (info or {}).get("source") == "vlm" and cands:
            out[key] = [date.fromisoformat(c) for c in cands]
    return out


class _Lazy:
    """Proxy that builds the wrapped engine on first attribute access."""

    def __init__(self, factory):
        self._factory = factory
        self._obj = None

    def __getattr__(self, name):
        if self._obj is None:
            self._obj = self._factory()
        return getattr(self._obj, name)


def lazy_ocr_engines():
    """(router, layout) proxies for batch runs: Paddle loads only if a document
    actually falls back to the OCR path, and then only once."""

    def _router():
        from apmatch.ocr.router import OCRRouter

        return OCRRouter()

    def _layout():
        from apmatch.layout.structure import LayoutEngine

        return LayoutEngine()

    return _Lazy(_router), _Lazy(_layout)


def invoice_key(invoice) -> tuple[str, str] | None:
    """(company, invoice number) identity used by the duplicate check."""
    from apmatch.matching.normalize import normalize_company

    if invoice is None or not invoice.invoice_number:
        return None
    number = "".join(ch for ch in invoice.invoice_number.upper() if ch.isalnum())
    return normalize_company(invoice.vendor_name), number


def check_duplicate(invoice, seen: dict, run_id: str):
    """In-memory duplicate check for batch runs (the API uses the audit log, D-108).

    The same supplier + invoice number seen earlier in the run marks this
    invoice as a duplicate of that run — also when it was re-dated or re-totalled.
    The first occurrence is registered; later ones are flagged.
    """
    key = invoice_key(invoice)
    if key is None:
        return invoice
    if key in seen:
        return replace(invoice, duplicate_of_run_id=seen[key])
    seen[key] = run_id
    return invoice


def build_audit_entry(
    invoice, po, grni, pard, validation, match, decision, *,
    run_id: str, customer_id: str, extraction_source: str,
    case_id: str | None = None, decided_by: str = "system", reviewer: str | None = None,
) -> AuditEntry:
    # Reviewer-facing remark rule (D-052): for a MATCH outcome the validation
    # summary is what the reviewer needs; for non-MATCH the match summary
    # explains the discrepancy.
    remark = summarize(validation) if match.outcome is Outcome.MATCH else summarize_match(match)
    return AuditEntry(
        run_id=run_id,
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
        customer_id=customer_id,
        extraction_source=extraction_source,
        case_id=case_id,
        decided_by=decided_by,
        reviewer=reviewer,
    )


def recheck_documents(
    documents: dict,
    *,
    customer_id: str,
    case_id: str,
    session=None,
    embedding_model=None,
    reviewer: str | None = None,
):
    """Re-decide a case from documents a reviewer corrected (review workflow).

    The reviewer's values are authoritative: only missing values are derived
    and a missing invoice currency is filled from the PO / payment advice; no
    date or price "repairs" are applied over what a person typed. The rules
    then decide exactly as for a fresh submission. The duplicate check
    ignores earlier runs of the same case. Returns the same 5-tuple as
    run_pipeline; the caller appends the audit entry.
    """
    from apmatch.parse.reconcile import fill_currency
    from apmatch.schema.serialize import DOC_KEYS, document_from_dict

    docs = {k: derive(document_from_dict(k, documents.get(k))) for k in DOC_KEYS}
    if docs["invoice"] is None:
        raise ValueError("invoice is required")
    docs = fill_currency(docs)
    invoice, po, grni, pard = (docs[k] for k in DOC_KEYS)
    if session is not None and invoice.invoice_number:
        from apmatch.audit.kpis import find_prior_invoice_run

        prior = find_prior_invoice_run(
            session,
            vendor_tax_id=invoice.vendor_tax_id,
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            total=invoice.total,
            customer_id=customer_id,
            exclude_case_id=case_id,
        )
        invoice = replace(invoice, duplicate_of_run_id=prior)
    validation, match, decision = decide_documents(invoice, po, grni, pard, embedding_model)
    entry = build_audit_entry(
        invoice, po, grni, pard, validation, match, decision,
        run_id=uuid4().hex, customer_id=customer_id, extraction_source="reviewer", case_id=case_id,
        reviewer=reviewer,
    )
    extracted = canonical_documents(invoice, po, grni, pard)
    extracted["_extraction"] = {k: ({"source": "reviewer"} if docs[k] is not None else None) for k in DOC_KEYS}
    return match, validation, decision, entry, extracted


def decide_documents(invoice, po, grni, pard, embedding_model=None):
    """The deterministic half of the pipeline: validate -> match -> route.

    Pure given its inputs. Shared by ``run_pipeline`` and
    ``scripts/rematch_report.py`` (which re-scores stored extractions).
    """
    validation = validate_invoice(invoice)
    match = MatchingEngine(embedding_model=embedding_model).match(invoice, po, grni, pard)
    decision = decide(validation, match, ocr_confidence=None)
    return validation, match, decision


def _summarize_sources(infos: dict) -> str:
    sources = {i["source"] for i in infos.values() if i}
    if len(sources) == 1:
        return sources.pop()
    return "mixed"


def run_pipeline(
    invoice_path: Path,
    po_path: Path | None = None,
    grni_path: Path | None = None,
    pard_path: Path | None = None,
    *,
    router=None,
    layout=None,
    embedding_model=None,
    ocr_debug: bool = False,
    customer_id: str = "default",
    session=None,
    extraction_cache_dir: Path | None = None,
    seen_invoices: dict | None = None,
) -> tuple[MatchResult, ValidationResult, RoutingDecision, AuditEntry, dict]:
    """Run the full chain over up to four document images.

    Extraction: the VLM reads each document (EXTRACTION_BACKEND=vlm, the
    default) with the OCR heuristics as per-document fallback; with
    EXTRACTION_BACKEND=ocr only the heuristics run. Everything after
    extraction (derivation, validation, matching, scoring) is deterministic.

    ``router``/``layout`` are heavy to construct; pass pre-built instances
    (the endpoint builds them once at startup). If omitted they are built
    lazily, only when a document actually needs the OCR path.
    ``embedding_model`` (duck-typed; needs .similarity() and .model_version)
    enables the similarity fallback in the matching engine.

    Returns the canonical extracted documents (5th element) so the caller can
    persist them for the review UI. That dict also carries ``_extraction``:
    per-document source and VLM diagnostics (model digest, prompt version,
    raw output, field errors).

    ``seen_invoices`` (batch runs, no DB): a dict shared across calls; an
    invoice whose supplier + number was seen before is a duplicate.
    """
    engines = _Engines(router, layout)
    cache_dir = Path(extraction_cache_dir) if extraction_cache_dir else None

    infos: dict[str, dict | None] = {"invoice": None, "po": None, "grni": None, "pard": None}
    docs: dict[str, object | None] = {"invoice": None, "po": None, "grni": None, "pard": None}
    for kind, path in (
        (dispatch.DocumentKind.INVOICE, invoice_path),
        (dispatch.DocumentKind.PURCHASE_ORDER, po_path),
        (dispatch.DocumentKind.GRNI, grni_path),
        (dispatch.DocumentKind.PAYMENT_ADVICE, pard_path),
    ):
        if path is None:
            continue
        doc, info = _recognize_and_parse(engines, kind, Path(path), ocr_debug, cache_dir)
        key = _DOC_KEY[kind]
        docs[key] = derive(doc)
        infos[key] = info

    # Case-level rules that need all four documents (currency, ambiguous dates).
    docs = reconcile(docs, date_candidates_from_infos(infos))
    invoice, po, grni, pard = docs["invoice"], docs["po"], docs["grni"], docs["pard"]

    # Duplicate-invoice check (D-108): only when a session is provided (the
    # API endpoint); batch runs and unit tests stay pure with session=None.
    if session is not None and invoice.invoice_number:
        from apmatch.audit.kpis import find_prior_invoice_run
        prior = find_prior_invoice_run(
            session,
            vendor_tax_id=getattr(invoice, "vendor_tax_id", None),
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            total=invoice.total,
            customer_id=customer_id,
        )
        if prior is not None:
            invoice = replace(invoice, duplicate_of_run_id=prior)

    run_id = uuid4().hex
    if seen_invoices is not None and session is None:
        invoice = check_duplicate(invoice, seen_invoices, run_id)

    validation, match, decision = decide_documents(invoice, po, grni, pard, embedding_model)
    audit_entry = build_audit_entry(
        invoice, po, grni, pard, validation, match, decision,
        run_id=run_id, customer_id=customer_id, extraction_source=_summarize_sources(infos),
    )
    extracted = canonical_documents(invoice, po, grni, pard)
    extracted["_extraction"] = infos
    return match, validation, decision, audit_entry, extracted
