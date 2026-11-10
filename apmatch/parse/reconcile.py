"""Case-level reconciliation: use the four documents together (D-114).

Extraction reads each document on its own. Some facts can only be settled by
looking at the whole case. This step is pure and deterministic, and it never
overrides a value the document states unambiguously.

1. Currency. An invoice that prints no currency takes it from the PO, then
   the payment advice ("USD" if none of them says). Local invoices often omit
   the currency their PO states.

2. Ambiguous dates. "04/09/2025" can be 4 Sep or 9 Apr. For every document
   whose printed date has two readings, pick the combination that gives the
   coherent business order PO <= GRN <= invoice <= payment, preferring the
   tightest overall span, then the reading the extractor already chose.
   Unambiguous dates are never changed, so a real chronology problem printed
   unambiguously is still caught by the matching engine.

3. Misread unit price. When an invoice line's qty x price does not give its
   amount, but amount / qty equals the price of the same item on the PO AND
   differs from the price read by exactly one digit ("12.80" vs "13.80"),
   the price was misread: use amount / qty. A real pricing error (price as
   on the PO, amount wrong) is never "repaired", because then amount / qty
   does not equal the PO price.
"""

from __future__ import annotations

import itertools
from dataclasses import replace
from datetime import date
from decimal import Decimal

from apmatch.schema.coercion import to_unit_price

# Business order of the four documents, and the date field of each.
_ORDER = ("po", "grni", "invoice", "pard")
_DATE_FIELD = {"po": "po_date", "grni": "grni_date", "invoice": "invoice_date", "pard": "payment_date"}


def _violations(dates: dict[str, date]) -> int:
    present = [dates[k] for k in _ORDER if dates.get(k) is not None]
    return sum(1 for a, b in itertools.combinations(present, 2) if a > b)


def _span(dates: dict[str, date]) -> int:
    present = [d for d in dates.values() if d is not None]
    return (max(present) - min(present)).days if len(present) > 1 else 0


def resolve_dates(docs: dict, candidates: dict[str, list[date]] | None) -> dict:
    """Return docs with ambiguous dates resolved. ``candidates[key]`` lists the
    readings of that document's printed date (from the extractor)."""
    if not candidates:
        return docs
    options: dict[str, list[date | None]] = {}
    for key in _ORDER:
        doc = docs.get(key)
        if doc is None:
            continue
        current = getattr(doc, _DATE_FIELD[key])
        cands = [c for c in (candidates.get(key) or []) if c is not None]
        if len(cands) > 1:
            # Current reading first, so it wins ties.
            options[key] = [current, *[c for c in cands if c != current]] if current in cands else cands
        else:
            options[key] = [current]
    if all(len(v) == 1 for v in options.values()):
        return docs

    keys = list(options)
    best = None
    for rank, combo in enumerate(itertools.product(*(options[k] for k in keys))):
        dates = dict(zip(keys, combo, strict=True))
        score = (_violations(dates), _span(dates), rank)
        if best is None or score < best[0]:
            best = (score, dates)
    chosen = best[1]
    out = dict(docs)
    for key, value in chosen.items():
        doc = out[key]
        if getattr(doc, _DATE_FIELD[key]) != value:
            out[key] = replace(doc, **{_DATE_FIELD[key]: value})
    return out


def fill_currency(docs: dict) -> dict:
    inv = docs.get("invoice")
    if inv is None or inv.currency:
        return docs
    for key in ("po", "pard"):
        other = docs.get(key)
        if other is not None and getattr(other, "currency", None):
            return dict(docs, invoice=replace(inv, currency=other.currency))
    return dict(docs, invoice=replace(inv, currency="USD"))


def _one_digit_apart(a: Decimal, b: Decimal) -> bool:
    sa, sb = f"{a:.2f}", f"{b:.2f}"
    return len(sa) == len(sb) and sum(x != y for x, y in zip(sa, sb, strict=True)) == 1


def repair_misread_prices(docs: dict) -> dict:
    inv, po = docs.get("invoice"), docs.get("po")
    if inv is None or po is None:
        return docs
    from apmatch.matching.engine import (
        names_close,  # local: keep parse -> matching one-way at import
    )

    cent = Decimal("0.01")
    changed = False
    lines = []
    for li in inv.line_items:
        q, p, a = li.quantity, li.unit_price, li.amount
        if q and p is not None and a is not None and abs(q * p - a) > cent:
            implied = to_unit_price(a / q)
            for pl in po.line_items:
                if (
                    pl.unit_price is not None
                    and abs(pl.unit_price - implied) <= cent
                    and _one_digit_apart(p, pl.unit_price)
                    and names_close(li.description, pl.description, exact_ok=True)
                ):
                    li = replace(li, unit_price=implied)
                    changed = True
                    break
        lines.append(li)
    return dict(docs, invoice=replace(inv, line_items=tuple(lines))) if changed else docs


def reconcile(docs: dict, date_candidates: dict[str, list[date]] | None = None) -> dict:
    """Apply all case-level rules. ``docs`` maps invoice/po/grni/pard to documents."""
    docs = fill_currency(docs)
    docs = repair_misread_prices(docs)
    return resolve_dates(docs, date_candidates)
