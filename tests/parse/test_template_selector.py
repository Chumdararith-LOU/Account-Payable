"""Template selector: picks the best-matching style for an OCRResult."""

from apmatch.ocr.engine import TextBlock
from apmatch.parse.template_loader import templates_by_id
from apmatch.parse.template_selector import select_template


def _b(text: str, x0: float = 100, y0: float = 100, x1: float = 300, y1: float = 140) -> TextBlock:
    return TextBlock(text=text, bbox=(x0, y0, x1, y1))


def test_selector_picks_kh_for_kh_document():
    blocks = (
        _b("No.:INV-2026-1123"),
        _b("Date:20-Aug-2026"),
        _b("From (Vendor) / "),
    )
    template, score = select_template(blocks, templates_by_id())
    assert template is not None
    assert template.style == "kh"
    assert score >= 0.5


def test_selector_picks_us_for_us_document():
    blocks = (_b("INVOICE #"), _b("INVOICE DATE"), _b("From"))
    template, _ = select_template(blocks, templates_by_id())
    assert template is not None
    assert template.style == "us"


def test_selector_picks_in_for_in_document():
    blocks = (_b("INVOICE #"), _b("Invoice Date"), _b("Seller"))
    template, _ = select_template(blocks, templates_by_id())
    assert template is not None
    assert template.style == "in"


def test_selector_falls_back_to_generic_on_garbage():
    blocks = (_b("random text"), _b("foo bar"), _b("xyz 123"))
    template, score = select_template(blocks, templates_by_id())
    assert template is not None
    assert template.style == "generic"
    assert score < 0.5


def test_selector_deterministic():
    blocks = (_b("INVOICE #"), _b("INVOICE DATE"), _b("From"))
    first = select_template(blocks, templates_by_id())
    for _ in range(5):
        assert select_template(blocks, templates_by_id()) == first
