"""
Render the demo fixture set (PO, GRN, Invoice, PARD) as PNGs.

Deterministic: running twice produces byte-identical PNGs
(Pillow output is deterministic given fixed inputs).

Layout notes (learned the hard way against PP-StructureV3 + the parse
layer's spatial matcher):
- The table needs a dark navy header row with white text (like the
  production fixtures). A plain white header gets its reading direction
  and cell order scrambled by the table pipeline.
- Header field values go on the line BELOW the label, not to its right:
  the OCR text detector sometimes merges same-line label:value pairs
  into one block, and the money extractor (labeled_money) has no
  same-block fallback. Separate lines are never merged, and the parse
  layer's below-lookup (80px) always finds them.
- Labels must match the extractor variants: "PO No", "GRN No",
  "PARD No" (see apmatch/parse/*.py).
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Fixture data. Kept inline so the images can be regenerated
# by anyone with the same script version.
#
# The semantic demo: PO says "Office Chair"; Invoice says
# "Chair, office, metal frame, black"; GRN says
# "Office Chair (black frame)". After normalization these strings
# remain distinct (different words), so the exact-match path
# fails. Embeddings find them equivalent.

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "documents" / "demo"

# ---- Font resolution ----

_FONT_CANDIDATES = {
    False: [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ],
    True: [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ],
}


def _find_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for p in _FONT_CANDIDATES[bold]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# ---- Page rendering ----


def _labeled_field(d: ImageDraw.ImageDraw, x: int, y: int, label: str, value: str,
                   font) -> int:
    """Draw 'label:' on one line and the value on the next (same x).

    Returns the y just below the value. Separate lines are never merged
    into one block by the OCR text detector, so the parse layer's
    below-lookup (80px) always finds the value. Same-line label:value
    pairs are unreliable: the detector sometimes merges them, and the
    money extractor (labeled_money) has no same-block fallback.
    """
    d.text((x, y), f"{label}:", font=font, fill="black")
    y += 44
    d.text((x, y), value, font=font, fill="black")
    return y + 44


def _render_page(
    title: str,
    header: dict[str, str],
    line_items: list[dict],
    totals: dict[str, str] | None,
    out_path: Path,
    cols: list[tuple[str, int]],
) -> None:
    """
    Renders an A4-ish page:
      - Title at top
      - Header block (label line, value line below — see _labeled_field)
      - Line-item table (dark navy header row, 1px grid)
      - Optional totals block (label line, value line below)
    Mimics the existing production fixtures, which PP-StructureV3 reads
    reliably: the dark header row is the cue the table pipeline needs to
    get reading direction and cell order right.
    """
    W, H = 1654, 2339  # A4 @ 200 DPI
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    f_title = _find_font(36)
    f_body = _find_font(22)
    f_small = _find_font(18)
    f_small_bold = _find_font(18, bold=True)

    x0, y = 100, 100

    # Title
    d.text((x0, y), title, font=f_title, fill="black")
    y += 70

    # Header fields (label line, value line below)
    for k, v in header.items():
        y = _labeled_field(d, x0, y, k, v, f_body)

    y += 40

    # Table (dark navy header row + 1px grid, like the production fixtures)
    if line_items:
        col_widths = [w for _, w in cols]
        table_w = sum(col_widths)
        header_h, row_h = 40, 44
        n_rows = len(line_items)
        top = y
        bottom = top + header_h + n_rows * row_h

        d.rectangle([x0, top, x0 + table_w, top + header_h], fill=(44, 62, 80))
        d.rectangle([x0, top, x0 + table_w, bottom], outline="black", width=1)
        vx = x0
        for w in col_widths[:-1]:
            vx += w
            d.line([(vx, top), (vx, bottom)], fill="black", width=1)
        d.line([(x0, top + header_h), (x0 + table_w, top + header_h)],
               fill="black", width=1)
        for i in range(1, n_rows):
            hy = top + header_h + i * row_h
            d.line([(x0, hy), (x0 + table_w, hy)], fill="black", width=1)

        # Header row (white bold on navy)
        tx = x0
        for name, w in cols:
            d.text((tx + 8, top + 10), name, font=f_small_bold, fill="white")
            tx += w

        # Data rows
        for i, row in enumerate(line_items):
            ry = top + header_h + i * row_h
            tx = x0
            vals = [
                str(row["line_no"]),
                row["description"],
                str(row["quantity"]),
                str(row["unit_price"]),
                str(row["amount"]),
            ]
            for (_name, w), v in zip(cols, vals):  # noqa: B905 — stops at the shorter (cols)
                if v:
                    d.text((tx + 8, ry + 12), v, font=f_small, fill="black")
                tx += w
        y = bottom + 30

    # Totals (right-side block, label line, value line below)
    if totals:
        for k, v in totals.items():
            y = _labeled_field(d, x0 + 700, y, k, v, f_body)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG", optimize=False)


# ---- Fixture data ----

PO = {
    "header": {
        "PO No": "PO-2026-0451",
        "Vendor": "Mekong Supplies Co., Ltd.",
        "Date": "15-Aug-2026",
        "Currency": "USD",
    },
    "line_items": [
        {"line_no": 1, "description": "Office Chair",
         "quantity": "10", "unit_price": "45.00", "amount": "450.00"},
        {"line_no": 2, "description": "Desk Lamp",
         "quantity": "20", "unit_price": "12.50", "amount": "250.00"},
        {"line_no": 3, "description": "Whiteboard",
         "quantity": "5", "unit_price": "60.00", "amount": "300.00"},
    ],
    "totals": {"Subtotal": "USD 1,000.00", "VAT 10%": "USD 100.00",
               "TOTAL": "USD 1,100.00"},
    "title": "PURCHASE ORDER",
}

# Invoice: same items, paraphrased descriptions.
INVOICE = {
    "header": {
        "Invoice Number": "INV-2026-1123",
        "Vendor": "Mekong Supplies Co., Ltd.",
        "Date": "20-Aug-2026",
        "Against PO": "PO-2026-0451",
        "Currency": "USD",
    },
    "line_items": [
        {"line_no": 1,
         "description": "Chair, office, metal frame, black",
         "quantity": "10", "unit_price": "45.00", "amount": "450.00"},
        {"line_no": 2,
         "description": "Lamp for desk, adjustable",
         "quantity": "20", "unit_price": "12.50", "amount": "250.00"},
        {"line_no": 3,
         "description": "White board, wall-mounted",
         "quantity": "5", "unit_price": "60.00", "amount": "300.00"},
    ],
    "totals": {"Subtotal": "USD 1,000.00", "VAT 10%": "USD 100.00",
               "TOTAL": "USD 1,100.00"},
    "title": "VENDOR INVOICE",
}

# GRN: quantities only, descriptions differ again.
GRN = {
    "header": {
        "GRN No": "GRN-2026-0322",
        "Vendor": "Mekong Supplies Co., Ltd.",
        "Date": "12-Sep-2026",
        "Against PO": "PO-2026-0451",
    },
    "line_items": [
        {"line_no": 1, "description": "Office Chair (black frame)",
         "quantity": "10", "unit_price": "", "amount": ""},
        {"line_no": 2, "description": "Desk Lamp",
         "quantity": "20", "unit_price": "", "amount": ""},
        {"line_no": 3, "description": "Whiteboard",
         "quantity": "5", "unit_price": "", "amount": ""},
    ],
    "totals": None,
    "title": "GOODS RECEIVED NOTE",
}

# PARD: single total, no line items. The amount is a right-aligned block
# (not a header field): a sparse left-only layout puts the content at the
# left edge of the OCR detection region, which drops first characters
# (INV->NV, USD->JSD). A right-aligned amount spans the page width, like
# the PO/invoice totals, so the left content keeps its margin.
PARD = {
    "header": {
        "PARD No": "PARD-2026-0210",
        "Against Invoice": "INV-2026-1123",
        "Date Paid": "01-Oct-2026",
        "Method": "Bank transfer",
    },
    "line_items": [],
    "totals": {"Amount Paid": "USD 1,100.00"},
    "title": "PAYMENT ADVICE",
}

# ---- Main ----


# All four documents use the same 5-column table shape: PP-StructureV3
# detects this shape reliably (a narrower 3-column GRN table gets its rows
# scrambled). The GRN leaves Unit Price / Amount empty (quantity-only doc).
FULL_COLS = [("#", 80), ("Description", 460), ("Qty", 120),
             ("Unit Price (USD)", 200), ("Amount (USD)", 200)]


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    _render_page(PO["title"], PO["header"], PO["line_items"], PO["totals"],
                 FIXTURE_DIR / "po.png", FULL_COLS)
    _render_page(INVOICE["title"], INVOICE["header"], INVOICE["line_items"],
                 INVOICE["totals"], FIXTURE_DIR / "invoice.png", FULL_COLS)
    _render_page(GRN["title"], GRN["header"], GRN["line_items"], GRN["totals"],
                 FIXTURE_DIR / "grn.png", FULL_COLS)
    _render_page(PARD["title"], PARD["header"], PARD["line_items"], PARD["totals"],
                 FIXTURE_DIR / "pard.png", [])
    print(f"wrote 4 fixture images to {FIXTURE_DIR}")


if __name__ == "__main__":
    main()
