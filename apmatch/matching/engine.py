"""Deterministic 4-way matching engine.

Pure, no I/O, no LLM, no network. Consumes the schema dataclasses
(``Invoice``, ``PurchaseOrder``, ``GRNI``, ``PaymentAdvice``) and produces a
``MatchResult``.

Matching strategy: vendor name via ``normalize_text``; currency via
``normalize_currency``; line items joined on ``normalize_text(description)``
with quantity/price/amount tolerance checks.

Score model: starts at 1.0; every ``MatchFailure`` subtracts its weight from
``config.MATCH_CODE_WEIGHTS``; the result is clamped to [0.0, 1.0]. A missing
PO/GRNI/PARD short-circuits to PENDING_INFO with score 0.0 before any further
checks run.

Money quantities come from the schema dataclasses, which guarantee Decimal. If
a caller somehow passes a float, Decimal/float arithmetic raises TypeError at
runtime; we deliberately do NOT cast.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path

from apmatch.matching.config import (
    AMOUNT_TOLERANCE,
    AMOUNT_TOLERANCE_REL,
    MATCH_CODE_WEIGHTS,
    QTY_TOLERANCE_ABS,
    TOTAL_TOLERANCE,
    UNIT_PRICE_TOLERANCE,
    UNIT_PRICE_TOLERANCE_REL,
)
from apmatch.matching.normalize import normalize_currency, normalize_text
from apmatch.matching.result import (
    MatchCode,
    MatchFailure,
    MatchResult,
    Outcome,
    _order_failures,
)
from apmatch.schema.coercion import to_money, to_qty, to_unit_price
from apmatch.schema.documents import GRNI, Invoice, LineItem, PaymentAdvice, PurchaseOrder
from apmatch.validation.result import Severity


class MatchingEngine:
    """Matches an invoice against its PO, GRNI, and payment advice."""

    def __init__(self) -> None:
        # No state today; reserved for future config objects.
        pass

    def match(
        self,
        invoice: Invoice,
        po: PurchaseOrder | None,
        grni: GRNI | None,
        pard: PaymentAdvice | None,
    ) -> MatchResult:
        failures: list[MatchFailure] = []

        # 1. Missing-document short-circuit.
        missing = []
        if po is None:
            missing.append(MatchCode.PO_MISSING)
        if grni is None:
            missing.append(MatchCode.GRNI_MISSING)
        if pard is None:
            missing.append(MatchCode.PARD_MISSING)
        if missing:
            for code in missing:
                failures.append(
                    MatchFailure(code, Severity.BLOCKER, "header", "present", "missing", "")
                )
            return MatchResult(
                outcome=Outcome.PENDING_INFO,
                score=0.0,
                failures=_order_failures(failures),
                invoice_number=invoice.invoice_number,
                po_number=po.po_number if po else None,
                grn_number=grni.grn_number if grni else None,
                pard_ref=pard.pard_number if pard else None,
            )

        # After the short-circuit, all three documents are guaranteed present.
        assert po is not None and grni is not None and pard is not None

        # 2. Header checks.
        if normalize_text(invoice.vendor_name) != normalize_text(po.vendor_name):
            failures.append(
                MatchFailure(
                    MatchCode.VENDOR_MISMATCH,
                    Severity.WARNING,
                    "header",
                    normalize_text(po.vendor_name),
                    normalize_text(invoice.vendor_name),
                    "",
                )
            )
        # The PurchaseOrder schema (P1-06) has no currency field; compare only
        # when one is present so the check is forward-compatible and never a
        # false positive. See P1-08b report.
        po_currency = getattr(po, "currency", None)
        if po_currency is not None and normalize_currency(invoice.currency) != normalize_currency(po_currency):
            failures.append(
                MatchFailure(
                    MatchCode.CURRENCY_MISMATCH,
                    Severity.WARNING,
                    "header",
                    normalize_currency(po_currency),
                    normalize_currency(invoice.currency),
                    "",
                )
            )

        # 3. Line-item matching.
        for n, inv_line in enumerate(invoice.line_items, start=1):
            po_line = _find_line(po.line_items, inv_line.description)
            if po_line is None:
                failures.append(
                    MatchFailure(
                        MatchCode.NO_MATCHING_PO_LINE,
                        Severity.WARNING,
                        f"line {n} (INV)",
                        "a PO line",
                        "none",
                        "",
                    )
                )
            else:
                loc = f"line {n} (INV) -> line {po_line.line_no} (PO)"
                if abs(inv_line.quantity - po_line.quantity) > QTY_TOLERANCE_ABS:
                    failures.append(
                        MatchFailure(
                            MatchCode.QTY_MISMATCH,
                            Severity.WARNING,
                            loc,
                            str(po_line.quantity),
                            str(inv_line.quantity),
                            str(abs(inv_line.quantity - po_line.quantity)),
                        )
                    )
                if inv_line.unit_price is not None and po_line.unit_price is not None:
                    diff = abs(inv_line.unit_price - po_line.unit_price)
                    max_val = max(abs(inv_line.unit_price), abs(po_line.unit_price))
                    if diff > UNIT_PRICE_TOLERANCE and (
                        max_val == 0 or diff / max_val > UNIT_PRICE_TOLERANCE_REL
                    ):
                        failures.append(
                            MatchFailure(
                                MatchCode.UNIT_PRICE_MISMATCH,
                                Severity.WARNING,
                                loc,
                                str(po_line.unit_price),
                                str(inv_line.unit_price),
                                str(diff),
                            )
                        )
                if inv_line.amount is not None and po_line.unit_price is not None:
                    po_amount = po_line.quantity * po_line.unit_price
                    diff = abs(inv_line.amount - po_amount)
                    max_val = max(abs(inv_line.amount), abs(po_amount))
                    if diff > AMOUNT_TOLERANCE and (
                        max_val == 0 or diff / max_val > AMOUNT_TOLERANCE_REL
                    ):
                        failures.append(
                            MatchFailure(
                                MatchCode.LINE_AMOUNT_MISMATCH,
                                Severity.WARNING,
                                loc,
                                str(po_amount),
                                str(inv_line.amount),
                                str(diff),
                            )
                        )

            grni_line = _find_line(grni.line_items, inv_line.description)
            if grni_line is None:
                failures.append(
                    MatchFailure(
                        MatchCode.NO_MATCHING_GRNI_LINE,
                        Severity.WARNING,
                        f"line {n} (INV)",
                        "a GRNI line",
                        "none",
                        "",
                    )
                )
            elif abs(inv_line.quantity - grni_line.quantity) > QTY_TOLERANCE_ABS:
                failures.append(
                    MatchFailure(
                        MatchCode.QTY_MISMATCH,
                        Severity.WARNING,
                        f"line {n} (INV) -> line {grni_line.line_no} (GRNI)",
                        str(grni_line.quantity),
                        str(inv_line.quantity),
                        str(abs(inv_line.quantity - grni_line.quantity)),
                    )
                )

        # 4. PARD amount vs invoice total.
        if abs(pard.amount - invoice.total) > TOTAL_TOLERANCE:
            failures.append(
                MatchFailure(
                    MatchCode.PARD_AMOUNT_MISMATCH,
                    Severity.BLOCKER,
                    "header",
                    str(invoice.total),
                    str(pard.amount),
                    str(abs(pard.amount - invoice.total)),
                )
            )

        # 5. Date ordering (soft).
        if pard.payment_date < invoice.invoice_date:
            failures.append(
                MatchFailure(
                    MatchCode.DATE_OUT_OF_ORDER,
                    Severity.INFO,
                    "header",
                    str(invoice.invoice_date),
                    str(pard.payment_date),
                    "",
                )
            )

        # 6. Outcome + score. Any failure (blocker or not) is a DISCREPANCY;
        # the blocker distinction is carried by MatchResult.has_blocker.
        outcome = Outcome.DISCREPANCY if failures else Outcome.MATCH
        total_weight = sum((MATCH_CODE_WEIGHTS[f.code] for f in failures), Decimal("0"))
        score = float(max(Decimal("0"), Decimal("1") - total_weight))

        return MatchResult(
            outcome=outcome,
            score=score,
            failures=_order_failures(failures),
            invoice_number=invoice.invoice_number,
            po_number=po.po_number,
            grn_number=grni.grn_number,
            pard_ref=pard.pard_number,
        )


def _find_line(lines: tuple[LineItem, ...], description: str) -> LineItem | None:
    """Return the FIRST line (source order) whose normalized description matches."""
    target = normalize_text(description)
    for line in lines:
        if normalize_text(line.description) == target:
            return line
    return None


# --- CLI -------------------------------------------------------------------


def _build_line(li: dict, default_no: int) -> LineItem:
    return LineItem(
        line_no=li.get("line_no", default_no),
        description=li["description"],
        quantity=to_qty(li["quantity"]),
        unit_price=to_unit_price(li["unit_price"]) if li.get("unit_price") is not None else None,
        amount=to_money(li["amount"]) if li.get("amount") is not None else None,
        unit_of_measure=li.get("unit_of_measure"),
    )


def _build_invoice(d: dict) -> Invoice:
    return Invoice(
        invoice_number=d["invoice_number"],
        vendor_name=d["vendor_name"],
        invoice_date=date.fromisoformat(d["invoice_date"]),
        currency=d["currency"],
        subtotal=to_money(d["subtotal"]),
        tax_amount=to_money(d["tax_amount"]),
        total=to_money(d["total"]),
        line_items=tuple(_build_line(li, i + 1) for i, li in enumerate(d.get("line_items", []))),
        po_number=d.get("po_number"),
        grn_number=d.get("grn_number"),
        discount_amount=to_money(d["discount_amount"]) if d.get("discount_amount") is not None else None,
    )


def _build_po(d: dict) -> PurchaseOrder:
    return PurchaseOrder(
        po_number=d["po_number"],
        vendor_name=d["vendor_name"],
        po_date=date.fromisoformat(d["po_date"]),
        total=to_money(d["total"]),
        line_items=tuple(_build_line(li, i + 1) for i, li in enumerate(d.get("line_items", []))),
    )


def _build_grni(d: dict) -> GRNI:
    return GRNI(
        grn_number=d["grn_number"],
        vendor_name=d["vendor_name"],
        grni_date=date.fromisoformat(d["grni_date"]),
        line_items=tuple(_build_line(li, i + 1) for i, li in enumerate(d.get("line_items", []))),
    )


def _build_pard(d: dict) -> PaymentAdvice:
    return PaymentAdvice(
        pard_number=d["pard_number"],
        invoice_number=d["invoice_number"],
        amount=to_money(d["amount"]),
        payment_date=date.fromisoformat(d["payment_date"]),
        reference=d.get("reference"),
    )


def _enum_to_value(obj):
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _enum_to_value(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_enum_to_value(v) for v in obj]
    return obj


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m apmatch.matching.engine <json_dir>", file=sys.stderr)
        return 2
    root = Path(argv[0])
    invoice = _build_invoice(json.loads((root / "invoice.json").read_text(encoding="utf-8")))
    po = _build_po(json.loads((root / "po.json").read_text(encoding="utf-8")))
    grni = _build_grni(json.loads((root / "grni.json").read_text(encoding="utf-8")))
    pard = _build_pard(json.loads((root / "pard.json").read_text(encoding="utf-8")))
    result = MatchingEngine().match(invoice, po, grni, pard)
    print(json.dumps(_enum_to_value(dataclasses.asdict(result)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
