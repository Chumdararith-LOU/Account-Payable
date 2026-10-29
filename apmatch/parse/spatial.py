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
    lx1 = label_bbox[2]
    out = []
    for b in blocks:
        bx0 = b.bbox[0]
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
    ly1 = label_bbox[3]
    out = []
    for b in blocks:
        by0 = b.bbox[1]
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


def value_after_label_with_validation(
    blocks: tuple[TextBlock, ...],
    labels: tuple[str, ...],
    parse_fn,
    candidate_order: tuple[str, ...] | None = None,
    position_fallback: str | None = None,
    max_gap_px: float = 200.0,
):
    """Try labels in order; for each, try same-block, right, below candidates.

    Returns the first candidate that ``parse_fn`` accepts as
    ``(parsed_value, raw_text)``; ``(None, None)`` if nothing parses.

    This is the fix for the ``value_parse_failed`` failure mode (PROD-B0.6):
    the legacy ``value_after_label`` grabs the first non-empty candidate
    without checking it parses, so a "Date" label next to a P.O. block yields
    ``parse_date("P.O.#") -> None``. Here every candidate is validated, and a
    bad one falls through to the next. ``candidate_order`` lets a specific
    label ("Invoice Date") win over a bare one ("Date"). ``position_fallback``
    ("top-right" / "top-left") is used only when no label matches.
    """
    order = candidate_order if candidate_order else labels
    for label in order:
        label_block = find_label(blocks, (label,))
        if label_block is None:
            continue
        candidates: list[str] = []
        sv = same_block_value(label_block, (label,))
        if sv is not None:
            candidates.append(sv)
        for b in (
            *bbox_right_of(blocks, label_block.bbox, max_gap_px),
            *bbox_below(blocks, label_block.bbox, max_gap_px),
        ):
            text = b.text.strip().lstrip(":").strip()
            if text:
                candidates.append(text)
        for cand in candidates:
            try:
                parsed = parse_fn(cand)
            except (ValueError, TypeError):
                continue
            if parsed is not None:
                return parsed, cand
    if position_fallback:
        fb = position_block(blocks, position_fallback)
        if fb is not None:
            try:
                parsed = parse_fn(fb.text.strip())
            except (ValueError, TypeError):
                parsed = None
            if parsed is not None:
                return parsed, fb.text.strip()
    return None, None


_COMPANY_SUFFIX_RE = re.compile(
    r"\b(LLC|Inc\.?|Co\.?|Ltd\.?|Limited|Corp\.?|Corporation|"
    r"GmbH|AG|SA|SAS|SRL|Pvt\.?\s*Ltd\.?|Private Limited)\b",
    re.IGNORECASE,
)


def find_vendor_heuristic(
    blocks: tuple[TextBlock, ...],
    page_height: float | None = None,
) -> TextBlock | None:
    """Most likely vendor name from an unlabeled document.

    Heuristic: top 20% of the page, block containing a legal suffix (LLC,
    Inc., Ltd., ...), largest by area. Rationale (PROD-B0.6): "Bill to" /
    "BILL TO" are near-misses for "vendor" but label the BUYER; a label-based
    approach grabs the wrong company. The suffix heuristic finds the company
    that is actually selling.
    """
    if page_height is None:
        page_height = max((b.bbox[3] for b in blocks), default=0)
        if page_height == 0:
            return None
    top_zone = [b for b in blocks if b.bbox[1] < page_height * 0.2]
    candidates = [b for b in top_zone if _COMPANY_SUFFIX_RE.search(b.text)]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda b: (b.bbox[2] - b.bbox[0]) * (b.bbox[3] - b.bbox[1]),
    )


def position_block(
    blocks: tuple[TextBlock, ...],
    position: str,
) -> TextBlock | None:
    """Largest block in a page corner zone ("top-right" / "top-left")."""
    if not blocks:
        return None
    width = max(b.bbox[2] for b in blocks)
    height = max(b.bbox[3] for b in blocks)
    if width == 0 or height == 0:
        return None
    if position == "top-right":
        zone = [b for b in blocks if b.bbox[0] > width * 0.6 and b.bbox[1] < height * 0.2]
    elif position == "top-left":
        zone = [b for b in blocks if b.bbox[0] < width * 0.4 and b.bbox[1] < height * 0.2]
    else:
        return None
    if not zone:
        return None
    return max(zone, key=lambda b: (b.bbox[2] - b.bbox[0]) * (b.bbox[3] - b.bbox[1]))
