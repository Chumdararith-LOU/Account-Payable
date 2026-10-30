"""Per-style extraction templates (schema).

A ``Template`` describes how to extract the HEADER fields from one style of
document (kh / us / in / generic). It is data, not code: adding a new style is
a YAML file, not a Python change. The loader (template_loader.py) reads YAML;
the selector (template_selector.py) picks the best match for an OCRResult; the
extractors (invoice.py, ...) consume the specs.

Line items are intentionally out of scope here (PROD-B1b) — ``LineItemsSpec``
is a reserved placeholder.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldSpec:
    """One field's extraction rules.

    labels: known label variants (substring, casefolded). Empty = "use the
        extractor's hardcoded fallback" (the generic-template safety net).
    candidate_order: label variants in preference order. If empty, ``labels``
        order is used. Lets a specific label ("Invoice Date") win over a bare
        one ("Date") that risks grabbing a P.O. block.
    formats: date strptime formats to try (for date fields). Empty = the
        coerce layer's default format list.
    position_fallback: "top-right" / "top-left" / None. Used when no label
        matches — take the block at that page position. None = skip the field.
    """

    labels: tuple[str, ...] = ()
    candidate_order: tuple[str, ...] = ()
    formats: tuple[str, ...] = ()
    position_fallback: str | None = None

    def effective_order(self) -> tuple[str, ...]:
        """Labels in the order the extractor should try them."""
        return self.candidate_order if self.candidate_order else self.labels


@dataclass(frozen=True)
class VendorSpec(FieldSpec):
    """Vendor extraction: labels, a heuristic, or both.

    strategy: "labeled" (labels only), "heuristic" (top-company-suffix only),
        or "labeled_then_heuristic" (labels first, fall back to the heuristic).
    heuristic_fallback: "top_company_suffix" = top-20% block with a legal
        suffix (LLC, Inc., Ltd., ...), largest by area.
    """

    strategy: str = "labeled"
    heuristic_fallback: str | None = None


@dataclass(frozen=True)
class CurrencySpec(FieldSpec):
    """Currency extraction: a symbol/code map plus the ISO-token fallback.

    symbol_map: (token, code) pairs, e.g. (("$", "USD"), ("₹", "INR")).
        Matched in source order; the first token found in any block wins.
        Empty = fall straight through to the ISO 4217 token detector.
    """

    symbol_map: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class TotalsSpec:
    """Subtotal / tax / total label specs.

    total_exclude_labels: blocks containing these are never treated as the
        total row (e.g. "Subtotal" contains "total" as a substring).
    """

    subtotal: FieldSpec = field(default_factory=FieldSpec)
    tax: FieldSpec = field(default_factory=FieldSpec)
    total: FieldSpec = field(default_factory=FieldSpec)
    total_exclude_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class LineItemsSpec:
    """Line-item column mapping (PROD-B1c).

    columns: canonical column -> header aliases (casefolded substring match).
        Canonical keys: "description", "quantity", "price", "amount".
        Empty = use the extractor's built-in defaults (the generic safety net).
    fallback: "positional" = when no header maps, assign columns by index
        (0=#, 1=desc, 2=qty, 3=price, 4=amount). None = no positional fallback.
    """

    enabled: bool = False
    columns: dict[str, tuple[str, ...]] = field(default_factory=dict)
    fallback: str | None = "positional"


@dataclass(frozen=True)
class Template:
    """One style's header-extraction rules."""

    template_id: str
    style: str
    invoice_number: FieldSpec = field(default_factory=FieldSpec)
    invoice_date: FieldSpec = field(default_factory=FieldSpec)
    vendor: VendorSpec = field(default_factory=VendorSpec)
    currency: CurrencySpec = field(default_factory=CurrencySpec)
    totals: TotalsSpec = field(default_factory=TotalsSpec)
    line_items: LineItemsSpec = field(default_factory=LineItemsSpec)
