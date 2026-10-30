"""Load and validate per-style templates from YAML.

Templates live at ``<repo_root>/templates/*.yaml`` — one file per style.
Loading is cached (``functools.lru_cache``): templates are data that does not
change at runtime, so the first load wins for the process lifetime.

Uses PyYAML (pinned in requirements.txt). No network, no ML.
"""

from __future__ import annotations

import functools
from pathlib import Path

import yaml

from apmatch.parse.templates import (
    CurrencySpec,
    FieldSpec,
    LineItemsSpec,
    Template,
    TotalsSpec,
    VendorSpec,
)

# templates/ sits at the repo root: apmatch/parse/template_loader.py -> up 3.
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"

_VALID_STYLES = {"kh", "us", "in", "generic"}  # open set; these are the known ones


def _field_spec(d: dict | None) -> FieldSpec:
    d = d or {}
    return FieldSpec(
        labels=tuple(d.get("labels") or ()),
        candidate_order=tuple(d.get("candidate_order") or ()),
        formats=tuple(d.get("formats") or ()),
        position_fallback=d.get("position_fallback"),
    )


def _vendor_spec(d: dict | None) -> VendorSpec:
    d = d or {}
    return VendorSpec(
        labels=tuple(d.get("labels") or ()),
        candidate_order=tuple(d.get("candidate_order") or ()),
        formats=(),
        position_fallback=d.get("position_fallback"),
        strategy=d.get("strategy", "labeled"),
        heuristic_fallback=d.get("heuristic_fallback"),
    )


def _currency_spec(d: dict | None) -> CurrencySpec:
    d = d or {}
    symbol_map = tuple((str(tok), str(code)) for tok, code in (d.get("symbol_map") or ()))
    return CurrencySpec(
        labels=(),
        candidate_order=(),
        formats=(),
        position_fallback=None,
        symbol_map=symbol_map,
    )


def _line_items_spec(d: dict | None) -> LineItemsSpec:
    d = d or {}
    columns = {
        str(col): tuple(str(a) for a in (aliases or ()))
        for col, aliases in (d.get("columns") or {}).items()
    }
    return LineItemsSpec(
        enabled=bool(d.get("enabled", False)),
        columns=columns,
        fallback=d.get("fallback", "positional"),
    )


def _totals_spec(d: dict | None) -> TotalsSpec:
    d = d or {}
    total = _field_spec(d.get("total"))
    return TotalsSpec(
        subtotal=_field_spec(d.get("subtotal")),
        tax=_field_spec(d.get("tax")),
        total=total,
        total_exclude_labels=tuple((d.get("total") or {}).get("exclude") or ()),
    )


def _template_from_dict(d: dict) -> Template:
    return Template(
        template_id=str(d.get("template_id", "")),
        style=str(d.get("style", "")),
        invoice_number=_field_spec(d.get("invoice_number")),
        invoice_date=_field_spec(d.get("invoice_date")),
        vendor=_vendor_spec(d.get("vendor")),
        currency=_currency_spec(d.get("currency")),
        totals=_totals_spec(d.get("totals")),
        line_items=_line_items_spec(d.get("line_items")),
    )


def validate_template(t: Template) -> list[str]:
    """Return a list of validation errors (empty = valid)."""
    errors: list[str] = []
    if not t.template_id:
        errors.append("template_id must be non-empty")
    if not t.style:
        errors.append("style must be non-empty")
    elif t.style not in _VALID_STYLES:
        # Open set: unknown styles are allowed but flagged so a typo is visible.
        errors.append(f"style {t.style!r} is not a known style (open set; check for a typo)")
    if t.vendor.strategy == "labeled" and not t.vendor.labels:
        errors.append("vendor.strategy is 'labeled' but vendor.labels is empty")
    if t.vendor.strategy == "heuristic" and not t.vendor.heuristic_fallback:
        errors.append("vendor.strategy is 'heuristic' but vendor.heuristic_fallback is unset")
    if t.vendor.strategy not in ("labeled", "heuristic", "labeled_then_heuristic"):
        errors.append(f"vendor.strategy {t.vendor.strategy!r} is not recognized")
    return errors


def load_template(path: Path) -> Template:
    """Load and validate one template YAML file."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: template file must be a mapping")
    t = _template_from_dict(data)
    errors = validate_template(t)
    if errors:
        raise ValueError(f"{path}: invalid template: " + "; ".join(errors))
    return t


@functools.lru_cache(maxsize=1)
def load_all_templates() -> tuple[tuple[str, Template], ...]:
    """Load every templates/*.yaml, keyed by template_id.

    Returns a tuple of (template_id, Template) pairs (stable, sorted by id) so
    the result is hashable and cacheable. Raises on duplicate template_ids.
    """
    if not _TEMPLATES_DIR.is_dir():
        return ()
    out: dict[str, Template] = {}
    for path in sorted(_TEMPLATES_DIR.glob("*.yaml")):
        t = load_template(path)
        if t.template_id in out:
            raise ValueError(f"duplicate template_id {t.template_id!r} in {path}")
        out[t.template_id] = t
    return tuple(sorted(out.items()))


def templates_by_id() -> dict[str, Template]:
    """Convenience: load_all_templates() as a dict keyed by template_id."""
    return dict(load_all_templates())
