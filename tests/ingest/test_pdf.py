"""PDF uploads are rendered to one PNG (UI-2)."""

import io

import pytest
from PIL import Image

from apmatch.ingest.pdf import DPI, PdfError, is_pdf, pdf_to_png


def _pdf(pages: int, size=(595, 842)) -> bytes:  # A4 in points
    imgs = [Image.new("RGB", size, (255, 255, 255 - i * 40)) for i in range(pages)]
    out = io.BytesIO()
    imgs[0].save(out, format="PDF", save_all=True, append_images=imgs[1:], resolution=72)
    return out.getvalue()


def test_detects_pdf():
    assert is_pdf(_pdf(1))
    assert not is_pdf(b"\x89PNG\r\n")


def test_single_page_renders_at_fixed_resolution():
    png = pdf_to_png(_pdf(1))
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"
    assert abs(img.width - round(595 * DPI / 72)) <= 2


def test_rendering_is_deterministic():
    data = _pdf(2)
    assert pdf_to_png(data) == pdf_to_png(data)


def test_pages_are_stacked_top_to_bottom():
    one = Image.open(io.BytesIO(pdf_to_png(_pdf(1))))
    three = Image.open(io.BytesIO(pdf_to_png(_pdf(3))))
    assert three.width == one.width and abs(three.height - 3 * one.height) <= 3


def test_too_many_pages_and_damaged_files_are_refused():
    with pytest.raises(PdfError) as e:
        pdf_to_png(_pdf(5))
    assert e.value.code == "PDF_TOO_MANY_PAGES"
    with pytest.raises(PdfError) as e:
        pdf_to_png(b"%PDF-1.4 this is not really a pdf")
    assert e.value.code == "INVALID_PDF"


def test_huge_pages_are_capped():
    img = Image.open(io.BytesIO(pdf_to_png(_pdf(1, size=(14400, 1000)))))  # a 200-inch-wide page
    assert max(img.size) <= 6001
