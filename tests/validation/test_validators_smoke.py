"""Smoke tests: each validator returns ok=True on a well-formed, DB-realistic doc.

Guarantees the validators do not spuriously fail on valid input. Field values
mirror the real rows seen in P1-06 Checkpoint A (Mekong Supplies invoice set).
"""

from datetime import date
from decimal import Decimal

from apmatch.schema.documents import GRNI, LineItem, PaymentAdvice, PurchaseOrder
from apmatch.validation.arithmetic import validate_grni, validate_pard, validate_po


def _po():
    lines = (
        LineItem(line_no=1, description="Office Chair", quantity=Decimal("10"), unit_price=Decimal("45.00")),
        LineItem(line_no=2, description="Desk Lamp", quantity=Decimal("20"), unit_price=Decimal("12.50")),
        LineItem(line_no=3, description="Whiteboard", quantity=Decimal("5"), unit_price=Decimal("60.00")),
    )
    return PurchaseOrder(
        po_number="PO-2026-0451",
        vendor_name="Mekong Supplies Co., Ltd.",
        po_date=date(2026, 8, 15),
        total=Decimal("1000.00"),  # 10*45 + 20*12.5 + 5*60
        line_items=lines,
    )


def _grni():
    lines = (
        LineItem(line_no=1, description="Office Chair", quantity=Decimal("10")),
        LineItem(line_no=2, description="Desk Lamp", quantity=Decimal("20")),
        LineItem(line_no=3, description="Whiteboard", quantity=Decimal("5")),
    )
    return GRNI(
        grn_number="GRN-2026-0322",
        vendor_name="Mekong Supplies Co., Ltd.",
        grni_date=date(2026, 8, 19),
        line_items=lines,
    )


def _pard():
    return PaymentAdvice(
        pard_number="PARD-2026-0210",
        invoice_number="INV-2026-1123",
        amount=Decimal("1100.00"),
        payment_date=date(2026, 8, 25),
        reference="REF-1",
    )


def test_po_smoke_ok():
    assert validate_po(_po()).ok is True


def test_grni_smoke_ok():
    assert validate_grni(_grni()).ok is True


def test_pard_smoke_ok():
    assert validate_pard(_pard()).ok is True


def test_all_smoke_ok():
    assert validate_po(_po()).ok
    assert validate_grni(_grni()).ok
    assert validate_pard(_pard()).ok
