"""Tolerance and matching configuration constants.

Constants, not config files — deliberately. Changing any value here changes
behavior across the whole matching engine; every change should come with a
task, a rationale, and updated tests. Money quantities are Decimal, not float.
"""

from decimal import Decimal

__all__ = [
    "QTY_TOLERANCE_ABS",
    "UNIT_PRICE_TOLERANCE",
    "AMOUNT_TOLERANCE",
    "TOTAL_TOLERANCE",
    "UNIT_PRICE_TOLERANCE_REL",
    "AMOUNT_TOLERANCE_REL",
    "VENDOR_NAME_FUZZY_MIN",
    "MATCHABLE_FIELDS",
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
