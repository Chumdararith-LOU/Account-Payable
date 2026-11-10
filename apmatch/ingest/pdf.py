"""PDF uploads: render the pages to one PNG the pipeline can read (UI-2).

Suppliers mostly send PDFs. The pipeline (VLM and OCR) reads images, so a PDF
is rendered with PDFium (pypdfium2) at a
fixed resolution. Rendering is deterministic for a given PDFium version: the
same file always gives the same pixels.

Multi-page documents (an invoice whose lines run onto page 2) are stacked top
to bottom into one tall image, up to MAX_PAGES pages.

pypdfium2 is not listed in requirements.txt on purpose: the pinned
paddlex[ocr]==3.7.2 requires it (pypdfium2>=4), and editing requirements.txt
would force the server to rebuild every Python layer of the image (paddle,
torch). Add an explicit pin the next time requirements.txt changes anyway.
"""

from __future__ import annotations

import io

import pypdfium2 as pdfium
from PIL import Image

DPI = 200
MAX_PAGES = 4
# A page larger than this (pixels per side) is rendered at a lower resolution,
# so a malicious PDF with a huge page size cannot exhaust memory.
MAX_SIDE_PX = 6000


class PdfError(ValueError):
    """The upload is not a PDF we can render. ``code`` is the API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def is_pdf(data: bytes) -> bool:
    return data[:1024].lstrip().startswith(b"%PDF-")


def _render_page(page) -> Image.Image:
    width_pt, height_pt = page.get_size()
    scale = min(DPI / 72, MAX_SIDE_PX / max(width_pt, height_pt, 1))
    return page.render(scale=scale).to_pil().convert("RGB")


def pdf_to_png(data: bytes, *, max_pages: int = MAX_PAGES) -> bytes:
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as e:
        raise PdfError(
            "INVALID_PDF", "The PDF could not be opened (damaged or password-protected)"
        ) from e
    try:
        count = len(pdf)
        if count == 0:
            raise PdfError("INVALID_PDF", "The PDF has no pages")
        if count > max_pages:
            raise PdfError(
                "PDF_TOO_MANY_PAGES",
                f"PDFs of up to {max_pages} pages are supported; split the file",
            )
        pages = [_render_page(pdf[i]) for i in range(count)]
    finally:
        pdf.close()

    if len(pages) == 1:
        sheet = pages[0]
    else:
        width = max(p.width for p in pages)
        sheet = Image.new("RGB", (width, sum(p.height for p in pages)), "white")
        y = 0
        for p in pages:
            sheet.paste(p, ((width - p.width) // 2, y))
            y += p.height
    out = io.BytesIO()
    sheet.save(out, format="PNG", optimize=False)
    return out.getvalue()
