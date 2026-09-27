"""Deterministic matching-engine result type.

No I/O. Failures carry a stable ``MatchCode`` and a ``Severity`` — never free
text. Downstream modules (remarks, routing, audit) switch on ``MatchCode``; they
must never string-match a message. Ordering is part of the contract:
``failures`` is sorted by (severity desc, then code asc, then location asc),
mirroring ``apmatch.validation.result``.
"""

from __future__ import annotations

from dataclasses import dataclass
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

    # ordering sanity
    DATE_OUT_OF_ORDER = "DATE_OUT_OF_ORDER"


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
class MatchResult:
    """The outcome of matching an invoice against PO / GRNI / PARD."""

    outcome: Outcome
    score: float  # in [0.0, 1.0]
    failures: tuple[MatchFailure, ...]

    invoice_number: str
    po_number: str | None = None
    grn_number: str | None = None
    pard_ref: str | None = None

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
