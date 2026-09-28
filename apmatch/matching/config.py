"""Tolerance and matching configuration constants.

Constants, not config files — deliberately. Changing any value here changes
behavior across the whole matching engine; every change should come with a
task, a rationale, and updated tests. Money quantities are Decimal, not float.
"""

from decimal import Decimal

from apmatch.matching.result import MatchCode

__all__ = [
    "AMOUNT_TOLERANCE",
    "AMOUNT_TOLERANCE_REL",
    "MATCHABLE_FIELDS",
    "MATCH_CODE_WEIGHTS",
    "QTY_TOLERANCE_ABS",
    "TOTAL_TOLERANCE",
    "UNIT_PRICE_TOLERANCE",
    "UNIT_PRICE_TOLERANCE_REL",
    "VENDOR_NAME_FUZZY_MIN",
]

# Absolute tolerances — differences strictly greater than these are treated as
# mismatches. Values in document currency units.
QTY_TOLERANCE_ABS = Decimal("0")  # quantities must match exactly
UNIT_PRICE_TOLERANCE = Decimal("0.01")  # one cent
AMOUNT_TOLERANCE = Decimal("0.01")  # one cent
TOTAL_TOLERANCE = Decimal("0.01")  # one cent

# Relative tolerances — used ONLY for line-item unit price and amount when the
# absolute tolerance would be too tight for large values. A line passes if
# (abs diff <= ABS) OR (abs diff / max(|a|, |b|) <= REL).
# NOT yet used by any engine; reserved for P1-08b, at which point a test
# asserts the intended behavior.
UNIT_PRICE_TOLERANCE_REL = Decimal("0.001")  # 0.1%
AMOUNT_TOLERANCE_REL = Decimal("0.001")  # 0.1%

# Vendor name: pure normalizations are expected to make these match; the fuzzy
# threshold is reserved for P1-08b if needed. If it stays unused after P1-08b,
# delete it.
VENDOR_NAME_FUZZY_MIN = Decimal("0.90")

# Currency codes must match exactly (ISO 4217) — no constant needed; the engine
# does an exact string compare on the normalized code.

# Documents with these fields populated are candidates for the numeric checks.
# Naming the tuple here keeps the engine from hardcoding field lists.
MATCHABLE_FIELDS = ("vendor_name", "currency", "total")

# Score weights: each MatchFailure contributes -weight to the score, which
# starts at 1.0 and is clamped to [0.0, 1.0]. Decimal, not float. A future
# change is one edit here, one task, one test.
MATCH_CODE_WEIGHTS: dict[MatchCode, Decimal] = {
    MatchCode.PO_MISSING: Decimal("0.5"),
    MatchCode.GRNI_MISSING: Decimal("0.5"),
    MatchCode.PARD_MISSING: Decimal("0.5"),
    MatchCode.VENDOR_MISMATCH: Decimal("0.3"),
    MatchCode.CURRENCY_MISMATCH: Decimal("0.3"),
    MatchCode.NO_MATCHING_PO_LINE: Decimal("0.2"),
    MatchCode.NO_MATCHING_GRNI_LINE: Decimal("0.2"),
    MatchCode.QTY_MISMATCH: Decimal("0.3"),
    MatchCode.UNIT_PRICE_MISMATCH: Decimal("0.3"),
    MatchCode.LINE_AMOUNT_MISMATCH: Decimal("0.3"),
    MatchCode.PARD_AMOUNT_MISMATCH: Decimal("0.2"),
    MatchCode.DATE_OUT_OF_ORDER: Decimal("0.1"),
}
