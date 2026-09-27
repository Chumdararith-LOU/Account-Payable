"""Structured result type for document validation.

Failures carry a stable ``CheckCode`` and a ``Severity`` — never free text.
Downstream modules (remarks, matching, audit) switch on ``CheckCode``; they
must never string-match a message. New failure modes are added by extending
``CheckCode``, not by inventing new message strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    BLOCKER = "blocker"
    WARNING = "warning"
    INFO = "info"


class CheckCode(str, Enum):
    LINE_AMOUNT_MISMATCH = "LINE_AMOUNT_MISMATCH"
    SUBTOTAL_MISMATCH = "SUBTOTAL_MISMATCH"
    TAX_MISMATCH = "TAX_MISMATCH"
    DISCOUNT_MISMATCH = "DISCOUNT_MISMATCH"
    TOTAL_MISMATCH = "TOTAL_MISMATCH"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    NEGATIVE_AMOUNT = "NEGATIVE_AMOUNT"
    NO_LINE_ITEMS = "NO_LINE_ITEMS"
    DATE_IN_FUTURE = "DATE_IN_FUTURE"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"


@dataclass(frozen=True)
class CheckFailure:
    """One failed check. Decimals are rendered as str; empty when n/a."""

    code: CheckCode
    severity: Severity
    location: str  # "header" or "line 3"
    expected: str
    actual: str
    delta: str


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of validating one document."""

    document_kind: str  # "invoice" | "po" | "grni" | "pard"
    checks_passed: tuple[CheckCode, ...]
    checks_failed: tuple[CheckFailure, ...]

    @property
    def ok(self) -> bool:
        return not self.checks_failed

    @property
    def has_blocker(self) -> bool:
        return any(f.severity is Severity.BLOCKER for f in self.checks_failed)
