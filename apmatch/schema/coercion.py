"""Coercion helpers that build Decimal money/price/qty values.

FLOAT REJECTION IS THE POINT OF THIS MODULE. ``float`` is a smell for
monetary code: it cannot represent most decimal fractions exactly, so a
float that slips into the money path causes silent drift (e.g. 0.1 + 0.2
!= 0.3). Every function here raises ``TypeError`` if handed a ``float``,
forcing the caller to pass a ``Decimal`` or a ``str`` (an ``int`` is also
accepted). This is the single boundary where external numeric input is
turned into a quantized Decimal; downstream code only ever sees Decimal.
"""

from __future__ import annotations

from decimal import Decimal

from apmatch.schema.documents import (
    MONEY_QUANTUM,
    QTY_QUANTUM,
    ROUNDING,
    UNIT_PRICE_QUANTUM,
)


def _coerce(value: Decimal | str | int, quantum: Decimal, name: str) -> Decimal:
    if isinstance(value, float):
        raise TypeError(
            f"{name}: float is not allowed for monetary/quantity values; "
            "pass a Decimal or a str (e.g. Decimal('10.00') or '10.00')"
        )
    return Decimal(value).quantize(quantum, rounding=ROUNDING)


def to_money(value: Decimal | str | int) -> Decimal:
    """Coerce to a Money Decimal quantized to 0.01 (ROUND_HALF_UP)."""
    return _coerce(value, MONEY_QUANTUM, "to_money")


def to_unit_price(value: Decimal | str | int) -> Decimal:
    """Coerce to a UnitPrice Decimal quantized to 0.0001 (ROUND_HALF_UP)."""
    return _coerce(value, UNIT_PRICE_QUANTUM, "to_unit_price")


def to_qty(value: Decimal | str | int) -> Decimal:
    """Coerce to a Quantity Decimal quantized to 0.0001 (ROUND_HALF_UP)."""
    return _coerce(value, QTY_QUANTUM, "to_qty")
