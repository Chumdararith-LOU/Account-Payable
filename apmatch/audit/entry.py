"""The content of the append-only audit log.

A frozen dataclass. ``run_id`` is non-deterministic (a UUID4 hex string); every
other field is a pure function of the pipeline inputs. ``input_hash`` is the
SHA-256 over the canonical JSON of the four documents (sorted keys, decimals as
strings) — the tamper-evidence field. Failures are stored structurally (code +
severity + location + expected/actual/delta), never as pre-rendered strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from apmatch.matching.result import MatchFailure, SimilarityMatch
from apmatch.scoring.result import Route, RouteReason
from apmatch.validation.result import CheckFailure


@dataclass(frozen=True)
class AuditEntry:
    run_id: str  # UUID4 hex string
    run_timestamp: datetime  # UTC, aware
    invoice_number: str
    po_number: str | None
    grn_number: str | None
    pard_ref: str | None

    route: Route
    route_reason: RouteReason
    score_value: Decimal  # Numeric(5,4) in DB
    remark: str

    validation_failures: tuple[CheckFailure, ...]
    match_failures: tuple[MatchFailure, ...]

    input_hash: str  # 64 hex chars
    similarity_matches: tuple[SimilarityMatch, ...] = ()
    # Multi-tenant tag (D-091). Defaulted and last: dataclass fields with
    # defaults must trail the required ones, so it cannot sit mid-class.
    customer_id: str = "default"
    # Which backend extracted the invoice (PROD-B2): "vlm", "heuristic",
    # "mixed", or "reviewer" (values typed in by a reviewer).
    extraction_source: str = "vlm"
    # Review workflow: one submission = one case; corrections and reviewer
    # decisions are new rows with the same case_id. None = its own run_id.
    case_id: str | None = None
    decided_by: str = "system"  # "system" or "reviewer"
    reviewer: str | None = None  # username of the person (D-118)
