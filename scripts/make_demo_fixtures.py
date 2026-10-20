"""
Render the demo fixture set (PO, GRN, Invoice, PARD) as PNGs.

Deterministic: running twice produces byte-identical PNGs
(Pillow output is deterministic given fixed inputs).
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Fixture data. Kept inline so the images can be regenerated
# by anyone with the same script version.
#
# The semantic demo: PO says "Office Chair"; Invoice says
# "Chair, office, metal frame, black"; GRN says
# "Office Chair (black)". After normalization these strings
# remain distinct (different words), so the exact-match path
# fails. Embeddings find them equivalent.

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "documents" / "demo"

# ---- Font resolution ----


def _find_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# ---- Page rendering ----


def _render_page(
    title: str,
    header: dict[str, str],
    line_items: list[dict],
    totals: dict[str, str] | None,
    out_path: Path,
) -> None:
    """
    Renders an A4-ish page:
      - Title at top
      - Header block (label: value lines)
      - Line-item table with # / Description / Qty / Unit Price / Amount
      - Optional totals block
    Uses simple 12pt text, monochrome, plain borders — mimics
    a printed supplier invoice.
    """
    W, H = 1654, 2339  # A4 @ 200 DPI
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    f_title = _find_font(36)
    f_body = _find_font(22)
    f_small = _find_font(18)

    x0, y = 100, 100

    # Title
    d.text((x0, y), title, font=f_title, fill="black")
    y += 70

    # Header rows
    for k, v in header.items():
        d.text((x0, y), f"{k}:", font=f_body, fill="black")
        d.text((x0 + 240, y), v, font=f_body, fill="black")
        y += 36

    y += 40

    # Table (full grid: PP-StructureV3 needs borders to extract cells
    # reliably — a borderless layout misaligns cells).
    cols = [("#", 80), ("Description", 500), ("Qty", 120),
            ("Unit Price", 180), ("Amount", 180)]
    col_widths = [w for _, w in cols]
    table_w = sum(col_widths)
    header_h, row_h = 30, 32
    n_rows = len(line_items)
    top = y
    bottom = top + header_h + n_rows * row_h

    d.rectangle([x0, top, x0 + table_w, bottom], outline="black", width=2)
    vx = x0
    for w in col_widths[:-1]:
        vx += w
        d.line([(vx, top), (vx, bottom)], fill="black", width=1)
    d.line([(x0, top + header_h), (x0 + table_w, top + header_h)], fill="black", width=1)
    for i in range(1, n_rows):
        hy = top + header_h + i * row_h
        d.line([(x0, hy), (x0 + table_w, hy)], fill="black", width=1)

    # Header row
    tx = x0
    for name, w in cols:
        d.text((tx + 8, top + 4), name, font=f_small, fill="black")
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
        for (_name, w), v in zip(cols, vals, strict=True):
            d.text((tx + 8, ry + 4), v, font=f_small, fill="black")
            tx += w
    y = bottom + 10

    # Totals
    if totals:
        y += 30
        for k, v in totals.items():
            d.text((x0 + 900, y), f"{k}:", font=f_body, fill="black")
            d.text((x0 + 1200, y), v, font=f_body, fill="black")
            y += 36

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG", optimize=False)


# ---- Fixture data ----

PO = {
    "header": {
        "PO Number": "PO-2026-0451",
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
        "GRN Number": "GRN-2026-0322",
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

# PARD: single total, no line items.
PARD = {
    "header": {
        "Reference": "PARD-2026-0210",
        "Against Invoice": "INV-2026-1123",
        "Amount Paid": "USD 1,100.00",
        "Date Paid": "01-Oct-2026",
        "Method": "Bank transfer",
    },
    "line_items": [],
    "totals": None,
    "title": "PAYMENT ADVICE",
}

# ---- Main ----


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    _render_page(PO["title"], PO["header"], PO["line_items"], PO["totals"],
                 FIXTURE_DIR / "po.png")
    _render_page(INVOICE["title"], INVOICE["header"], INVOICE["line_items"],
                 INVOICE["totals"], FIXTURE_DIR / "invoice.png")
    _render_page(GRN["title"], GRN["header"], GRN["line_items"], GRN["totals"],
                 FIXTURE_DIR / "grn.png")
    _render_page(PARD["title"], PARD["header"], PARD["line_items"], PARD["totals"],
                 FIXTURE_DIR / "pard.png")
    print(f"wrote 4 fixture images to {FIXTURE_DIR}")


if __name__ == "__main__":
    main()
