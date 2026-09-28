"""Shared table-HTML parsing for the extraction layer.

Parses the simple ``<table>`` HTML that PP-StructureV3 emits into a header row
plus data rows. Footer rows (``colspan``) are skipped. Column location is by
header text (case-insensitive substring), with a positional fallback when no
header row is present.
"""

from __future__ import annotations

from bs4 import BeautifulSoup


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
