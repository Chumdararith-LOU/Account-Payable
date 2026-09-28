"""Extractor tests against the real PP-OCRv6 fixtures in output/ocr/.

Values asserted are the TRUE document values (per P1-12a decision): the
fixtures carry explicit Subtotal 1,000.00 / VAT 100.00 / TOTAL 1,100.00 on
the invoice and PO, and 1,100.00 on the PARD. The legacy DB's 0.0 totals
were a known bug (USD lived in a separate text block from the label).
"""

from datetime import date
from decimal import Decimal

from apmatch.ocr.engine import OCRResult, Table, TextBlock
from apmatch.parse.grni import extract_grni
from apmatch.parse.invoice import extract_invoice
from apmatch.parse.payment_advice import extract_payment_advice
from apmatch.parse.purchase_order import extract_purchase_order
from tests.parse.conftest import _load_ocr_result


def _inv():
    return extract_invoice(_load_ocr_result("INV_2026_1123.json"))


def test_extract_invoice_invoice_number():
    assert _inv().invoice_number == "INV-2026-1123"


def test_extract_invoice_vendor_name():
    assert _inv().vendor_name == "Mekong Supplies Co., Ltd."


def test_extract_invoice_date():
    assert _inv().invoice_date == date(2026, 8, 20)


def test_extract_invoice_line_count():
    assert len(_inv().line_items) == 3


def test_extract_invoice_total():
    assert _inv().total == Decimal("1100.00")


def test_extract_invoice_line_amounts():
    assert [li.amount for li in _inv().line_items] == [
        Decimal("450.00"),
        Decimal("250.00"),
        Decimal("300.00"),
    ]


def test_extract_invoice_subtotal():
    # Explicit in the document ("Subtotal/ USD 1,000.00"); tax is explicit too.
    assert _inv().subtotal == Decimal("1000.00")
    assert _inv().tax_amount == Decimal("100.00")


def test_extract_po_line_count():
    po = extract_purchase_order(_load_ocr_result("PO_2026_0451.json"))
    assert len(po.line_items) == 3


def test_extract_po_total():
    po = extract_purchase_order(_load_ocr_result("PO_2026_0451.json"))
    assert po.total == Decimal("1100.00")
    assert po.po_number == "PO-2026-0451"


def test_extract_grni_line_count():
    grni = extract_grni(_load_ocr_result("GRN_2026_0322.json"))
    assert len(grni.line_items) == 3
    assert grni.grn_number == "GRN-2026-0322"
    assert [li.quantity for li in grni.line_items] == [
        Decimal("10.0000"),
        Decimal("20.0000"),
        Decimal("5.0000"),
    ]


def test_extract_pard_amount():
    pard = extract_payment_advice(_load_ocr_result("PARD_2026_0210.json"))
    assert pard.amount == Decimal("1100.00")
    assert pard.pard_number == "PARD-2026-0210"
    assert pard.invoice_number == "INV-2026-1123"


def test_extractor_totality_empty_input():
    inv = extract_invoice(OCRResult(source_file="x", text_blocks=(), tables=()))
    assert inv.invoice_number is None
    assert inv.vendor_name is None
    assert inv.invoice_date is None
    assert inv.subtotal is None
    assert inv.tax_amount is None
    assert inv.total is None
    assert inv.line_items == ()
    assert inv.currency == "USD"  # documented default, not None


def test_invoice_derives_totals_when_absent():
    # No Subtotal/Tax/Total labels anywhere: subtotal and total are derived
    # from line amounts (P1-10c-fix policy).
    ocr = OCRResult(
        source_file="synthetic",
        text_blocks=(
            TextBlock(text="No.:INV-2026-0001", bbox=(100, 100, 300, 130)),
            TextBlock(text="Date:01-Jan-2026", bbox=(100, 140, 300, 170)),
        ),
        tables=(
            Table(
                html=(
                    "<table><tr><td>#</td><td>Description</td><td>Qty</td>"
                    "<td>Unit Price</td><td>Amount</td></tr>"
                    "<tr><td>1</td><td>Widget</td><td>2</td><td>100.00</td><td>200.00</td></tr>"
                    "<tr><td>2</td><td>Gadget</td><td>1</td><td>50.00</td><td>50.00</td></tr>"
                    "</table>"
                ),
                bbox=(0, 0, 0, 0),
            ),
        ),
    )
    inv = extract_invoice(ocr)
    assert inv.subtotal == Decimal("250.00")
    assert inv.total == Decimal("250.00")  # no tax found -> total = subtotal


def test_invoice_derives_tax_when_label_missing():
    # Subtotal and Total are explicit but the VAT label is garbled/absent
    # (live OCR misread it as Khmer on INV_2026_1123): tax is derived as
    # total - subtotal (P1-10c-fix policy extension).
    ocr = OCRResult(
        source_file="synthetic",
        text_blocks=(
            TextBlock(text="Subtotal", bbox=(100, 100, 200, 130)),
            TextBlock(text="USD 1,000.00", bbox=(250, 100, 400, 130)),
            TextBlock(text="TOTAL", bbox=(100, 140, 200, 170)),
            TextBlock(text="USD 1,100.00", bbox=(250, 140, 400, 170)),
        ),
        tables=(),
    )
    inv = extract_invoice(ocr)
    assert inv.subtotal == Decimal("1000.00")
    assert inv.total == Decimal("1100.00")
    assert inv.tax_amount == Decimal("100.00")  # derived: 1100 - 1000
