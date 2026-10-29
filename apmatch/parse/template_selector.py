"""Pick the best-matching template for an OCRResult.

Strategy: score each non-generic template by the fraction of its labeled
fields that have at least one label present in the blocks. Highest score wins;
if the best score is below the threshold, fall back to the generic template
(the hardcoded-default safety net).

Determinism: templates are iterated in sorted template_id order, and a strict
``>`` comparison keeps the first (alphabetically earliest) template on ties.
No dict iteration, no randomness.
"""

from __future__ import annotations

from apmatch.ocr.engine import TextBlock
from apmatch.parse.spatial import find_label
from apmatch.parse.templates import Template

# Below this label-overlap score, no style is confident enough — use generic.
_MIN_SCORE = 0.5


def _score(t: Template, blocks: tuple[TextBlock, ...]) -> float:
    """Fraction of t's labeled header fields that have a label in blocks."""
    fields = (t.invoice_number, t.invoice_date, t.vendor)
    with_labels = [f for f in fields if f.labels]
    if not with_labels:
        return 0.0
    found = sum(1 for f in with_labels if find_label(blocks, f.labels) is not None)
    return found / len(with_labels)


def select_template(
    blocks: tuple[TextBlock, ...],
    templates: dict[str, Template],
) -> tuple[Template | None, float]:
    """Return (template, score). Falls back to generic when no style is confident."""
    best: Template | None = None
    best_score = 0.0
    for tid in sorted(templates):
        t = templates[tid]
        if t.style == "generic":
            continue
        score = _score(t, blocks)
        if score > best_score:
            best, best_score = t, score
    if best is not None and best_score >= _MIN_SCORE:
        return best, best_score
    generic = templates.get("generic")
    if generic is not None:
        return generic, best_score
    return best, best_score
