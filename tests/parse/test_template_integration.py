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


def _kh_blocks(total_text: str) -> tuple[TextBlock, ...]:
    return (
        _b("No.: INV-2026-999", 100, 100, 300, 140),
        _b("Date: 20-Aug-2026", 100, 200, 300, 240),
        _b("From (Vendor) / ", 100, 300, 300, 340),
        _b("Mekong Supplies Co., Ltd.", 320, 310, 600, 350),
        _b("Total", 100, 400, 200, 440),
        _b(total_text, 250, 410, 450, 450),
    )


def test_kh_invoice_no_currency_marker_defaults_to_khr():
    # Khmer-style documents omit the currency code for local-currency
    # amounts (USD always prints "$"), so "no marker" must mean KHR, not the
    # global USD default.
    inv = extract_invoice(OCRResult(source_file="kh", text_blocks=_kh_blocks("14,844,500"), tables=()))
    assert inv.currency == "KHR"
    assert inv.total == Decimal("14844500")


def test_kh_invoice_dollar_marker_beats_default():
    inv = extract_invoice(OCRResult(source_file="kh", text_blocks=_kh_blocks("$ 1,100.00"), tables=()))
    assert inv.currency == "USD"


def test_kh_invoice_unlabeled_top_right_number():
    # kh_sme layout: the number is a bare top-right block, with the "Invoice"
    # title and the date in the same corner. The position fallback must pick
    # the number — not the date, not the digitless title.
    blocks = (
        _b("Invoice Pvelec", 1438, 0, 1608, 29),
        _b("Invoice", 1456, 69, 1612, 113),
        _b("2026412", 1493, 121, 1613, 156),
        _b("Date:", 1333, 170, 1409, 203),
        _b("19/02/2026", 1456, 162, 1613, 199),
        _b("From (Vendor) / ", 100, 300, 300, 340),
        _b("Mekong Supplies Co., Ltd.", 320, 310, 600, 350),
        _b("Total", 100, 1500, 200, 1540),
        _b("14,844,500", 250, 1510, 450, 1550),
    )
    inv = extract_invoice(OCRResult(source_file="kh", text_blocks=blocks, tables=()))
    assert inv.invoice_number == "2026412"


def test_kh_invoice_degree_sign_number_label():
    # kh_sme invoices label the number "N°:" (degree sign, not the letter o).
    # The kh template carries "N°" so the selector scores kh (not generic) and
    # the number is read from the block right of the label.
    blocks = (
        _b("Invoice Sabay", 1438, 0, 1608, 29),
        _b("N°:", 1400, 120, 1460, 155),
        _b("2025462", 1470, 120, 1600, 155),
        _b("Date:", 1333, 170, 1409, 203),
        _b("17-Dec-25", 1456, 162, 1613, 199),
        _b("From (Vendor) / ", 100, 300, 300, 340),
        _b("Mekong Supplies Co., Ltd.", 320, 310, 600, 350),
        _b("Total", 100, 1500, 200, 1540),
        _b("16,110,600", 250, 1510, 450, 1550),
    )
    inv = extract_invoice(OCRResult(source_file="kh", text_blocks=blocks, tables=()))
    assert inv.invoice_number == "2025462"
    assert inv.invoice_date == date(2025, 12, 17)


def _us_blocks() -> tuple[TextBlock, ...]:
    return (
        _b("INVOICE #", 100, 100, 250, 140),
        _b("US-275", 300, 110, 400, 150),
        _b("INVOICE DATE", 100, 200, 250, 240),
        _b("Mar 15, 2026", 300, 210, 420, 250),
        _b("Billed From", 100, 300, 180, 340),
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
        _b("Seller Name", 100, 300, 180, 340),
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
        _b("Billed From", 100, 300, 180, 340),
        _b("Sunshine Motors Service", 230, 310, 450, 350),
    )
    inv = extract_invoice(OCRResult(source_file="us", text_blocks=blocks, tables=()))
    assert inv.invoice_date == date(2025, 8, 15)
