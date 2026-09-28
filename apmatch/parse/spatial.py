"""Spatial primitives over OCR text blocks.

Pure functions over ``tuple[TextBlock, ...]``. No ML, no I/O, no mutation.

Spatial conventions:
- bbox format is ``(x0, y0, x1, y1)`` with ``x0 < x1`` and ``y0 < y1``.
- "right of" = ``block.x0 >= label.x1`` (block starts at or past the label's
  right edge), within ``max_gap_px`` horizontally.
- "vertically overlapping" = the y-intervals ``[y0, y1]`` intersect.
- "below" = ``block.y0 >= label.y1`` (block starts at or past the label's
  bottom edge), within ``max_gap_px`` vertically.
- All distances are Euclidean in pixel units of the source image.
"""

from __future__ import annotations

import re

from apmatch.ocr.engine import TextBlock


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()


def _y_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return max(a[1], b[1]) < min(a[3], b[3])


def _x_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return max(a[0], b[0]) < min(a[2], b[2])


def bbox_right_of(
    blocks: tuple[TextBlock, ...],
    label_bbox: tuple[float, float, float, float],
    max_gap_px: float = 200.0,
) -> tuple[TextBlock, ...]:
    """Blocks entirely to the right of ``label_bbox`` and vertically overlapping it.

    Sorted by horizontal x-distance ascending (nearest first).
    """
    lx1, ly0, ly1 = label_bbox[2], label_bbox[1], label_bbox[3]
    out = []
    for b in blocks:
        bx0, by0, by1 = b.bbox[0], b.bbox[1], b.bbox[3]
        if bx0 < lx1:
            continue
        if bx0 - lx1 > max_gap_px:
            continue
        if not _y_overlap(label_bbox, b.bbox):
            continue
        out.append((bx0 - lx1, b))
    out.sort(key=lambda t: t[0])
    return tuple(b for _, b in out)


def bbox_below(
    blocks: tuple[TextBlock, ...],
    label_bbox: tuple[float, float, float, float],
    max_gap_px: float = 80.0,
) -> tuple[TextBlock, ...]:
    """Blocks vertically below ``label_bbox`` and horizontally overlapping it.

    Within ``max_gap_px`` vertically. Sorted by y-distance ascending (nearest first).
    """
    lx0, lx1, ly1 = label_bbox[0], label_bbox[2], label_bbox[3]
    out = []
    for b in blocks:
        bx0, bx1, by0 = b.bbox[0], b.bbox[2], b.bbox[1]
        if by0 < ly1:
            continue
        if by0 - ly1 > max_gap_px:
            continue
        if not _x_overlap(label_bbox, b.bbox):
            continue
        out.append((by0 - ly1, b))
    out.sort(key=lambda t: t[0])
    return tuple(b for _, b in out)


def find_label(
    blocks: tuple[TextBlock, ...],
    variants: tuple[str, ...],
    casefold: bool = True,
) -> TextBlock | None:
    """First block whose normalized text contains any variant (source order).

    Uses a substring (contains) match rather than an exact match because real
    PP-OCRv6 labels carry trailing noise (slashes, Khmer glyphs, colons). The
    first match in source order wins, so callers order variants by specificity.
    """
    for block in blocks:
        text = _normalize(block.text) if casefold else block.text
        for variant in variants:
            v = _normalize(variant) if casefold else variant
            if v and v in text:
                return block
    return None


def value_right_or_below(
    blocks: tuple[TextBlock, ...],
    label_bbox: tuple[float, float, float, float],
    max_gap_px: float = 200.0,
) -> str | None:
    """First non-empty block text to the right of ``label_bbox``, then below it.

    Strips colons and leading/trailing whitespace. Returns None if no value found.
    """
    for candidate in (
        *bbox_right_of(blocks, label_bbox, max_gap_px),
        *bbox_below(blocks, label_bbox, max_gap_px),
    ):
        text = candidate.text.strip().lstrip(":").strip()
        if text:
            return text
    return None


def value_after_label(
    blocks: tuple[TextBlock, ...],
    variants: tuple[str, ...],
    max_gap_px: float = 200.0,
) -> str | None:
    """Find the label, then look right, then below; return the first non-empty value.

    Strips colons and leading/trailing whitespace. Returns None if no value found.
    """
    label = find_label(blocks, variants)
    if label is None:
        return None
    return value_right_or_below(blocks, label.bbox, max_gap_px)


def same_block_value(label: TextBlock, variants: tuple[str, ...]) -> str | None:
    """Value carried in the label block's own text, after the label.

    Real PP-OCRv6 output frequently merges label and value into one block
    (e.g. ``No.:INV-2026-1123``, ``Date:20-Aug-2026``). Returns the cleaned
    remainder of the first matching variant. The remainder must contain at
    least one digit: OCR noise tails (``/H``, ``/NJU``, ``Hnüms``) are
    rejected so callers fall through to the spatial lookup.
    """
    text = _normalize(label.text)
    for variant in variants:
        v = _normalize(variant)
        idx = text.find(v)
        if idx == -1:
            continue
        rest = label.text[idx + len(variant):].strip().lstrip(":").strip()
        if rest and any(c.isdigit() for c in rest):
            return rest
    return None
