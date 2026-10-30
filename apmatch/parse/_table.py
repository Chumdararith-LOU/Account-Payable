"""Shared table-HTML parsing for the extraction layer.

Two ways to get line items out of an OCRResult:

1. ``parse_table_rows`` / ``find_column`` — parse the ``<table>`` HTML that
   PP-StructureV3 emits into a header row plus data rows.
2. ``line_items_from_text_blocks`` — a borderless / garbage-table fallback that
   rebuilds the table from the raw OCR text blocks (grouped into rows by
   y-overlap, columns located by the header row's x-centers). PP-StructureV3
   frequently returns zero tables (borderless us/in invoices) or a transposed /
   shifted table (some kh invoices and GRNs); the text blocks are clean in both
   cases, so this is the robust source.

Column location is by header text (casefolded substring) via
``classify_header_cell``; unmapped columns are skipped, and a positional
fallback is used only when no header maps at all.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

# Built-in column aliases (casefolded substring). Used when a template does not
# supply its own ``line_items.columns``. Order in classify_header_cell matters:
# price is checked before description so "Item Rate" -> price, not description.
DEFAULT_COLUMNS: dict[str, tuple[str, ...]] = {
    "description": ("description", "item description", "item", "product"),
    "quantity": ("qty", "quantity", "units", "count"),
    "price": ("unit price", "item rate", "rate", "price"),
    "amount": ("amount", "line total", "total", "value"),
}

# Canonical columns checked first (most conflict-prone first).
_COLUMN_ORDER = ("price", "quantity", "amount", "description")


def parse_table_rows(html: str) -> tuple[list[str], list[list[str]]]:
    """Return ``(header, data_rows)`` from a table HTML string.

    ``header`` is the first non-footer row's cell texts (empty list if the
    table has no rows). ``data_rows`` are the remaining non-footer rows.
    """
    if not html:
        return [], []
    soup = BeautifulSoup(html, "html.parser")
    rows: list[list[str]] = []
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        if any(c.get("colspan") for c in cells):
            continue  # footer / summary row
        rows.append([c.get_text().strip() for c in cells])
    if not rows:
        return [], []
    return rows[0], rows[1:]


def find_column(header: list[str], *keywords: str) -> int | None:
    """Index of the first header cell containing any keyword (case-insensitive)."""
    for i, cell in enumerate(header):
        low = cell.lower()
        for kw in keywords:
            if kw in low:
                return i
    return None


def classify_header_cell(text: str, columns: dict[str, tuple[str, ...]] | None = None) -> str | None:
    """Map a header cell to a canonical column via casefolded word-boundary match.

    Returns one of "description" / "quantity" / "price" / "amount", or None if
    the cell matches no alias (e.g. "HSN", "Discount", "Condition"). Word
    boundaries (not raw substring) are used so "count" does not match inside
    "Discount" and "rate" does not match inside "generate".
    """
    cols = columns or DEFAULT_COLUMNS
    low = (text or "").casefold().strip()
    if not low:
        return None
    for col in _COLUMN_ORDER:
        for alias in cols.get(col, ()):
            if re.search(r"\b" + re.escape(alias.casefold()) + r"\b", low):
                return col
    return None


def _center(b) -> float:
    return (b.bbox[0] + b.bbox[2]) / 2


def _ycenter(b) -> float:
    return (b.bbox[1] + b.bbox[3]) / 2


def _group_into_rows(blocks) -> list[list]:
    """Group text blocks into rows by y-proximity; each row sorted by x.

    A block joins the current row while its y-center is within one median block
    height of the row's anchor (the first block's y-center). This merges a
    value with a stray sub-line (e.g. a tax-% block) while keeping distinct
    table rows separate.
    """
    if not blocks:
        return []
    ordered = sorted(blocks, key=_ycenter)
    heights = [b.bbox[3] - b.bbox[1] for b in ordered]
    median_h = sorted(heights)[len(heights) // 2] or 1.0
    gap = median_h
    rows: list[list] = []
    current = [ordered[0]]
    anchor = _ycenter(ordered[0])
    for b in ordered[1:]:
        if _ycenter(b) - anchor <= gap:
            current.append(b)
        else:
            rows.append(sorted(current, key=lambda b: b.bbox[0]))
            current = [b]
            anchor = _ycenter(b)
    rows.append(sorted(current, key=lambda b: b.bbox[0]))
    return rows


def _cluster_by_x(blocks) -> list[list]:
    """Cluster blocks by x-center into columns; clusters sorted by x.

    A block joins the current cluster while its x-center is within the
    threshold of the previous block's; otherwise a new cluster starts. The
    threshold scales with the data's x-span so it adapts to the document.
    """
    if not blocks:
        return []
    ordered = sorted(blocks, key=_center)
    xs = [_center(b) for b in ordered]
    threshold = max(0.05 * (xs[-1] - xs[0]), 30.0)
    clusters: list[list] = [[ordered[0]]]
    for b in ordered[1:]:
        if _center(b) - _center(clusters[-1][-1]) <= threshold:
            clusters[-1].append(b)
        else:
            clusters.append([b])
    return clusters


def _cluster_center(cluster) -> float:
    return sum(_center(b) for b in cluster) / len(cluster)


def _map_clusters_to_header(clusters, header_cells, header_types) -> list:
    """Map each data cluster to a header cell's canonical type.

    By order when the counts match (the header and the data columns are in the
    same left-to-right order); otherwise by nearest x-center. This is robust to
    a header label that is not centered over its data column (e.g. a us-style
    "DESCRIPTION" label sitting to the right of the description values).
    """
    if len(clusters) == len(header_cells):
        return list(header_types)
    header_xs = [_center(b) for b in header_cells]
    types = []
    for cluster in clusters:
        cx = _cluster_center(cluster)
        best = min(range(len(header_cells)), key=lambda i: abs(cx - header_xs[i]))
        types.append(header_types[best])
    return types


def _assign_to_clusters(row: list, clusters, types) -> dict[str, str]:
    """Assign each block in a row to the nearest cluster; return {type: text}.

    For the description cluster the longest text wins (beats stray line
    numbers); for qty/price/amount a block that parses as a number wins (beats
    a stray OCR word at the same x).
    """
    from apmatch.parse.coerce import parse_money, parse_qty

    centers = [_cluster_center(c) for c in clusters]
    by_cluster: dict[int, list] = {}
    for b in row:
        bx = _center(b)
        i = min(range(len(clusters)), key=lambda j: abs(bx - centers[j]))
        by_cluster.setdefault(i, []).append(b)

    cells: dict[str, str] = {}
    for i, cands in by_cluster.items():
        col = types[i]
        if col is None:
            continue
        if col == "description":
            cells[col] = max(cands, key=lambda b: len(b.text)).text.strip()
            continue
        parser = parse_qty if col == "quantity" else parse_money
        numeric = [b for b in cands if parser(b.text) is not None]
        pool = numeric or cands
        cells[col] = min(pool, key=lambda b: abs(_center(b) - centers[i])).text.strip()
    return cells


def line_items_from_text_blocks(blocks, columns: dict[str, tuple[str, ...]] | None = None) -> tuple:
    """Rebuild line items from raw OCR text blocks (borderless / garbage fallback).

    Groups blocks into rows, finds the header row (the row with the most
    column-name matches), clusters the data blocks by x-position into columns,
    maps those clusters to the header's column types (by order), and reads the
    data rows below the header until a total/subtotal row or a row with no
    description / no numeric value. Returns () when no tabular header is found.
    """
    from apmatch.parse.coerce import parse_money, parse_qty
    from apmatch.schema.coercion import to_money, to_qty, to_unit_price
    from apmatch.schema.documents import LineItem

    if len(blocks) < 3:
        return ()
    rows = _group_into_rows(blocks)
    if len(rows) < 2:
        return ()

    # Header row = the row with the most column-name matches (need >= 2).
    header_idx, header_matches = -1, 0
    for i, row in enumerate(rows):
        matches = sum(1 for b in row if classify_header_cell(b.text, columns))
        if matches > header_matches:
            header_matches, header_idx = matches, i
    if header_idx < 0 or header_matches < 2:
        return ()

    header_cells = sorted(rows[header_idx], key=lambda b: b.bbox[0])
    header_types = [classify_header_cell(b.text, columns) for b in header_cells]
    if "description" not in header_types:
        return ()

    # Data rows: rows below the header, stopping at a total/subtotal row.
    data_rows = []
    for row in rows[header_idx + 1:]:
        if any(k in b.text.casefold() for b in row for k in ("total", "subtotal")):
            break
        data_rows.append(row)
    if not data_rows:
        return ()

    # Cluster all data blocks by x into columns; map clusters to header types.
    all_data = [b for row in data_rows for b in row]
    clusters = _cluster_by_x(all_data)
    types = _map_clusters_to_header(clusters, header_cells, header_types)

    items = []
    for row in data_rows:
        cells = _assign_to_clusters(row, clusters, types)
        desc = cells.get("description", "")
        qty = parse_qty(cells.get("quantity"))
        price = parse_money(cells.get("price"))
        amount = parse_money(cells.get("amount"))
        if not desc or (qty is None and price is None and amount is None):
            continue  # not a data row (footer / stray text)
        items.append(
            LineItem(
                line_no=len(items) + 1,
                description=desc,
                quantity=to_qty(qty) if qty is not None else None,
                unit_price=to_unit_price(price) if price is not None else None,
                amount=to_money(amount) if amount is not None else None,
            )
        )
    return tuple(items)
