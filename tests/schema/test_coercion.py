from decimal import Decimal

import pytest

from apmatch.schema.coercion import to_money, to_qty, to_unit_price
from apmatch.schema.documents import GRNI, Invoice, PaymentAdvice, PurchaseOrder


def test_to_money_accepts_str_and_decimal():
    assert to_money("10.00") == Decimal("10.00")
    assert to_money(Decimal("10.005")) == Decimal("10.01")
    assert to_money(42) == Decimal("42.00")


def test_to_money_rejects_float():
    with pytest.raises(TypeError):
        to_money(10.0)


def test_to_money_quantizes_half_up():
    assert to_money(Decimal("1.005")) == Decimal("1.01")
    assert to_money(Decimal("1.004")) == Decimal("1.00")


def test_to_unit_price_quantum_is_4dp():
    result = to_unit_price("1.23456")
    assert result == Decimal("1.2346")
    assert result.as_tuple().exponent == -4


def test_to_qty_quantum_is_4dp():
    result = to_qty(Decimal("3.00005"))
    assert result == Decimal("3.0001")
    assert result.as_tuple().exponent == -4


def test_invoice_no_longer_has_created_at():
    assert not hasattr(Invoice, "created_at")
    assert not hasattr(PurchaseOrder, "created_at")
    assert not hasattr(GRNI, "created_at")
    assert not hasattr(PaymentAdvice, "created_at")
