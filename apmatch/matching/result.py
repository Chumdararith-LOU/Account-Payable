"""Deterministic matching-engine result type.

No I/O. Failures carry a stable ``MatchCode`` and a ``Severity`` — never free
text. Downstream modules (remarks, routing, audit) switch on ``MatchCode``; they
must never string-match a message. Ordering is part of the contract:
``failures`` is sorted by (severity desc, then code asc, then location asc),
mirroring ``apmatch.validation.result``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from apmatch.validation.result import Severity


class Outcome(str, Enum):
    MATCH = "MATCH"
    DISCREPANCY = "DISCREPANCY"
    PENDING_INFO = "PENDING_INFO"


class MatchCode(str, Enum):
    # missing document
    PO_MISSING = "PO_MISSING"
    GRNI_MISSING = "GRNI_MISSING"
    PARD_MISSING = "PARD_MISSING"

    # header-level
    VENDOR_MISMATCH = "VENDOR_MISMATCH"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"

    # line-level — no corresponding line on PO or GRNI
    NO_MATCHING_PO_LINE = "NO_MATCHING_PO_LINE"
    NO_MATCHING_GRNI_LINE = "NO_MATCHING_GRNI_LINE"

    # line-level — matched line but value differs
    QTY_MISMATCH = "QTY_MISMATCH"
    UNIT_PRICE_MISMATCH = "UNIT_PRICE_MISMATCH"
    LINE_AMOUNT_MISMATCH = "LINE_AMOUNT_MISMATCH"

    # payment advice vs invoice total
    PARD_AMOUNT_MISMATCH = "PARD_AMOUNT_MISMATCH"

    # sequence and reference sanity
    INVOICE_BEFORE_PO = "INVOICE_BEFORE_PO"
    PARD_INVOICE_MISMATCH = "PARD_INVOICE_MISMATCH"
    DUPLICATE_INVOICE = "DUPLICATE_INVOICE"

    # ordering sanity
    DATE_OUT_OF_ORDER = "DATE_OUT_OF_ORDER"

    # similarity fallback — match accepted but in the review band
    SIMILARITY_MATCH_REVIEW = "SIMILARITY_MATCH_REVIEW"


@dataclass(frozen=True)
class MatchFailure:
    """One failed match check. Decimals are rendered as str; empty when n/a."""

    code: MatchCode
    severity: Severity
    location: str  # "header" or "line 3 (INV) -> line 2 (PO)"
    expected: str
    actual: str
    delta: str


@dataclass(frozen=True)
class SimilarityMatch:
    """
    Record of an embedding-based line match.

    Present whenever the engine accepted a similarity match
    (either accept band or review band). Absent when the
    exact-match path was used.

    The score and both thresholds are recorded at decision
    time, so future threshold changes do not invalidate
    the audit trail (per D-080).
    """

    location: str  # "line 2 (INV) -> line 2 (PO)" or "line 2 (INV) -> line 2 (GRN)"
    invoice_text: str  # invoice line description, post-normalization
    counterpart_text: str  # counterpart line description, post-normalization
    score: Decimal  # cosine similarity, quantized to 4dp
    threshold_review: Decimal  # config.SIMILARITY_REVIEW at match time
    threshold_accept: Decimal  # config.SIMILARITY_ACCEPT at match time
    band: str  # "accept" or "review"
    model_version: str  # SHA-256 of the embedding weights, from EmbeddingModel


@dataclass(frozen=True)
class MatchResult:
    """The outcome of matching an invoice against PO / GRNI / PARD."""

    outcome: Outcome
    score: float  # in [0.0, 1.0]
    failures: tuple[MatchFailure, ...]

    invoice_number: str
    po_number: str | None = None
    grn_number: str | None = None
    pard_ref: str | None = None
    similarity_matches: tuple[SimilarityMatch, ...] = ()

    @property
    def ok(self) -> bool:
        return self.outcome is Outcome.MATCH

    @property
    def has_blocker(self) -> bool:
        return any(f.severity is Severity.BLOCKER for f in self.failures)

    @property
    def is_pending(self) -> bool:
        return self.outcome is Outcome.PENDING_INFO


_SEV_RANK = {Severity.BLOCKER: 2, Severity.WARNING: 1, Severity.INFO: 0}


def _order_failures(failures: list[MatchFailure]) -> tuple[MatchFailure, ...]:
    return tuple(
        sorted(failures, key=lambda f: (-_SEV_RANK[f.severity], f.code.value, f.location))
    )
