"""Template-driven extraction: end-to-end behavior per style.

Regression guard: the kh fixture must extract exactly as before the template
system. The us/in tests verify the new label variants, formats, currency
symbols, and the vendor heuristic.
"""

from datetime import date
from decimal import Decimal

from apmatch.ocr.engine import OCRResult, TextBlock
from apmatch.parse.invoice import extract_invoice
from tests.parse.conftest import _load_ocr_result


def _b(text: str, x0: float, y0: float, x1: float, y1: float) -> TextBlock:
    return TextBlock(text=text, bbox=(x0, y0, x1, y1))


def test_kh_invoice_extracts_as_before():
    # The regression guard: every header field matches the pre-refactor value.
    inv = extract_invoice(_load_ocr_result("INV_2026_1123.json"))
    assert inv.invoice_number == "INV-2026-1123"
    assert inv.vendor_name == "Mekong Supplies Co., Ltd."
    assert inv.invoice_date == date(2026, 8, 20)
    assert inv.currency == "USD"
    assert inv.subtotal == Decimal("1000.00")
    assert inv.tax_amount == Decimal("100.00")
    assert inv.total == Decimal("1100.00")


def _us_blocks() -> tuple[TextBlock, ...]:
    return (
        _b("INVOICE #", 100, 100, 250, 140),
        _b("US-275", 300, 110, 400, 150),
        _b("INVOICE DATE", 100, 200, 250, 240),
        _b("Mar 15, 2026", 300, 210, 420, 250),
        _b("From", 100, 300, 180, 340),
        _b("Sunshine Motors Service", 230, 310, 450, 350),
    )


def test_us_invoice_extracts_invoice_number():
    inv = extract_invoice(OCRResult(source_file="us", text_blocks=_us_blocks(), tables=()))
    assert inv.invoice_number == "US-275"


def test_us_invoice_date_format():
    # "Mar 15, 2026" is the %b %d, %Y format the legacy parse_date lacked.
    inv = extract_invoice(OCRResult(source_file="us", text_blocks=_us_blocks(), tables=()))
    assert inv.invoice_date == date(2026, 3, 15)


def test_us_invoice_extracts_dollar_amount():
    blocks = (*_us_blocks(), _b("Total", 100, 400, 200, 440), _b("$228.97", 250, 410, 400, 450))
    inv = extract_invoice(OCRResult(source_file="us", text_blocks=blocks, tables=()))
    assert inv.currency == "USD"
    assert inv.total == Decimal("228.97")


def test_in_invoice_extracts_rupee_amount():
    blocks = (
        _b("INVOICE #", 100, 100, 250, 140),
        _b("IN-123", 300, 110, 400, 150),
        _b("Invoice Date", 100, 200, 250, 240),
        _b("15/08/2025", 300, 210, 420, 250),
        _b("Seller", 100, 300, 180, 340),
        _b("Shree Ganesh Appliances", 230, 310, 450, 350),
        _b("Total", 100, 400, 200, 440),
        _b("₹1,234.56", 250, 410, 400, 450),
    )
    inv = extract_invoice(OCRResult(source_file="in", text_blocks=blocks, tables=()))
    assert inv.currency == "INR"
    assert inv.vendor_name == "Shree Ganesh Appliances"
    assert inv.total == Decimal("1234.56")


def test_vendor_heuristic_finds_company_when_no_label():
    # No vendor label; the top-20% legal-suffix block is the vendor.
    blocks = (
        _b("INVOICE #", 100, 100, 250, 140),
        _b("US-275", 300, 110, 400, 150),
        _b("INVOICE DATE", 100, 200, 250, 240),
        _b("Mar 15, 2026", 300, 210, 420, 250),
        _b("Acme Corp LLC", 100, 40, 400, 80),  # top 20%, no vendor label
    )
    inv = extract_invoice(OCRResult(source_file="us", text_blocks=blocks, tables=()))
    assert inv.vendor_name == "Acme Corp LLC"


def test_value_validation_skips_bad_candidate():
    # "INVOICE DATE" has a P.O. block to its right, then the real date. The
    # validated extraction skips the P.O. block and returns the date.
    blocks = (
        _b("INVOICE #", 100, 100, 250, 140),
        _b("US-275", 300, 110, 400, 150),
        _b("INVOICE DATE", 100, 200, 250, 240),
        _b("P.O.#", 300, 210, 380, 250),
        _b("08/15/2025", 420, 210, 540, 250),  # MM/DD (us template format)
        _b("From", 100, 300, 180, 340),
        _b("Sunshine Motors Service", 230, 310, 450, 350),
    )
    inv = extract_invoice(OCRResult(source_file="us", text_blocks=blocks, tables=()))
    assert inv.invoice_date == date(2025, 8, 15)
