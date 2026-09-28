"""Pure arithmetic-consistency validators for AP documents.

Pure functions, no I/O, no exceptions for business failures — each returns a
``ValidationResult``. Deterministic: the same input always yields the same
output, including the ordering of ``checks_failed`` (severity desc, then code
asc, then location asc). That ordering is part of the contract.

Given a well-formed document object, these answer one question: is the
document's own arithmetic internally consistent? They do NOT match documents
against each other, extract from OCR, or generate remarks.

Two-mode tax/discount checks (part of the contract): when ``Invoice.tax_rate``
/ ``Invoice.discount_rate`` is present, ``TAX_MISMATCH`` / ``DISCOUNT_MISMATCH``
is a real arithmetic check (expected = (subtotal - discount) * tax_rate, or
subtotal * discount_rate) and a failure is a BLOCKER at location ``"header"``.
When the rate is absent, the check degrades to a sanity check (tax > total, or
discount > subtotal) that is a WARNING at location
``"header (sanity-only: no tax_rate)"`` / ``"header (sanity-only: no
discount_rate)"`` — the tag keeps audit logs unambiguous about which mode ran.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path

from apmatch.schema.coercion import to_money, to_qty, to_unit_price
from apmatch.schema.documents import (
    GRNI,
    MONEY_QUANTUM,
    ROUNDING,
    Invoice,
    LineItem,
    PaymentAdvice,
    PurchaseOrder,
)
from apmatch.validation.result import (
    CheckCode,
    CheckFailure,
    Severity,
    ValidationResult,
)

# Tolerances: one cent.
LINE_AMOUNT_TOLERANCE = Decimal("0.01")
TOTAL_TOLERANCE = Decimal("0.01")

_SEV_RANK = {Severity.BLOCKER: 2, Severity.WARNING: 1, Severity.INFO: 0}


def _sort_failures(failures: list[CheckFailure]) -> tuple[CheckFailure, ...]:
    return tuple(
        sorted(
            failures,
            key=lambda f: (-_SEV_RANK[f.severity], f.code.value, f.location),
        )
    )


def _finish(kind: str, passed: set[CheckCode], failures: list[CheckFailure]) -> ValidationResult:
    return ValidationResult(
        document_kind=kind,
        checks_passed=tuple(sorted(passed, key=lambda c: c.value)),
        checks_failed=_sort_failures(failures),
    )


def _q2(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUNDING)


def validate_invoice(inv: Invoice) -> ValidationResult:
    passed: set[CheckCode] = set()
    failures: list[CheckFailure] = []

    if not inv.line_items:
        failures.append(
            CheckFailure(CheckCode.NO_LINE_ITEMS, Severity.BLOCKER, "header", "", "0 lines", "")
        )
    else:
        passed.add(CheckCode.NO_LINE_ITEMS)

        line_ok = True
        for line in inv.line_items:
            if line.amount is None or line.unit_price is None:
                line_ok = False
                failures.append(
                    CheckFailure(
                        CheckCode.MISSING_REQUIRED_FIELD,
                        Severity.BLOCKER,
                        f"line {line.line_no}",
                        "amount+unit_price",
                        "missing",
                        "",
                    )
                )
                continue
            expected = _q2(line.quantity * line.unit_price)
            if abs(expected - line.amount) > LINE_AMOUNT_TOLERANCE:
                line_ok = False
                failures.append(
                    CheckFailure(
                        CheckCode.LINE_AMOUNT_MISMATCH,
                        Severity.BLOCKER,
                        f"line {line.line_no}",
                        str(expected),
                        str(line.amount),
                        str(abs(expected - line.amount)),
                    )
                )
        if line_ok:
            passed.add(CheckCode.LINE_AMOUNT_MISMATCH)

        lines_sum = _q2(sum((li.amount for li in inv.line_items if li.amount is not None), Decimal("0")))
        if abs(lines_sum - inv.subtotal) > TOTAL_TOLERANCE:
            failures.append(
                CheckFailure(
                    CheckCode.SUBTOTAL_MISMATCH,
                    Severity.BLOCKER,
                    "header",
                    str(inv.subtotal),
                    str(lines_sum),
                    str(abs(lines_sum - inv.subtotal)),
                )
            )
        else:
            passed.add(CheckCode.SUBTOTAL_MISMATCH)

        discount = inv.discount_amount if inv.discount_amount is not None else Decimal("0")
        expected_total = _q2(inv.subtotal - discount + inv.tax_amount)
        if abs(expected_total - inv.total) > TOTAL_TOLERANCE:
            failures.append(
                CheckFailure(
                    CheckCode.TOTAL_MISMATCH,
                    Severity.BLOCKER,
                    "header",
                    str(inv.total),
                    str(expected_total),
                    str(abs(expected_total - inv.total)),
                )
            )
        else:
            passed.add(CheckCode.TOTAL_MISMATCH)

        if inv.discount_rate is not None:
            expected_discount = _q2(inv.subtotal * inv.discount_rate)
            actual_discount = inv.discount_amount if inv.discount_amount is not None else Decimal("0")
            if abs(actual_discount - expected_discount) > TOTAL_TOLERANCE:
                failures.append(
                    CheckFailure(
                        CheckCode.DISCOUNT_MISMATCH,
                        Severity.BLOCKER,
                        "header",
                        str(expected_discount),
                        str(actual_discount),
                        str(actual_discount - expected_discount),
                    )
                )
            else:
                passed.add(CheckCode.DISCOUNT_MISMATCH)
        else:
            if inv.discount_amount is not None and inv.discount_amount > inv.subtotal:
                failures.append(
                    CheckFailure(
                        CheckCode.DISCOUNT_MISMATCH,
                        Severity.WARNING,
                        "header (sanity-only: no discount_rate)",
                        "<= subtotal",
                        str(inv.discount_amount),
                        str(inv.discount_amount - inv.subtotal),
                    )
                )
            else:
                passed.add(CheckCode.DISCOUNT_MISMATCH)

        if inv.tax_rate is not None:
            expected_tax = _q2((inv.subtotal - discount) * inv.tax_rate)
            if abs(inv.tax_amount - expected_tax) > TOTAL_TOLERANCE:
                failures.append(
                    CheckFailure(
                        CheckCode.TAX_MISMATCH,
                        Severity.BLOCKER,
                        "header",
                        str(expected_tax),
                        str(inv.tax_amount),
                        str(inv.tax_amount - expected_tax),
                    )
                )
            else:
                passed.add(CheckCode.TAX_MISMATCH)
        else:
            if inv.tax_amount > inv.total:
                failures.append(
                    CheckFailure(
                        CheckCode.TAX_MISMATCH,
                        Severity.WARNING,
                        "header (sanity-only: no tax_rate)",
                        "<= total",
                        str(inv.tax_amount),
                        str(inv.tax_amount - inv.total),
                    )
                )
            else:
                passed.add(CheckCode.TAX_MISMATCH)

    neg = []
    if inv.subtotal < 0:
        neg.append("subtotal")
    if inv.tax_amount < 0:
        neg.append("tax_amount")
    if inv.total < 0:
        neg.append("total")
    if inv.discount_amount is not None and inv.discount_amount < 0:
        neg.append("discount_amount")
    for line in inv.line_items:
        if line.quantity < 0:
            neg.append(f"line {line.line_no} quantity")
        if line.amount is not None and line.amount < 0:
            neg.append(f"line {line.line_no} amount")
    if neg:
        failures.append(
            CheckFailure(CheckCode.NEGATIVE_AMOUNT, Severity.WARNING, "header", ">= 0", ",".join(neg), "")
        )
    else:
        passed.add(CheckCode.NEGATIVE_AMOUNT)

    if inv.invoice_date > date.today():
        failures.append(
            CheckFailure(CheckCode.DATE_IN_FUTURE, Severity.WARNING, "header", "<= today", str(inv.invoice_date), "")
        )
    else:
        passed.add(CheckCode.DATE_IN_FUTURE)

    missing = [
        name
        for name, value in (
            ("invoice_number", inv.invoice_number),
            ("vendor_name", inv.vendor_name),
            ("currency", inv.currency),
        )
        if not value
    ]
    if missing:
        failures.append(
            CheckFailure(CheckCode.MISSING_REQUIRED_FIELD, Severity.BLOCKER, "header", "non-empty", ",".join(missing), "")
        )
    else:
        passed.add(CheckCode.MISSING_REQUIRED_FIELD)

    return _finish("invoice", passed, failures)


def validate_po(po: PurchaseOrder) -> ValidationResult:
    passed: set[CheckCode] = set()
    failures: list[CheckFailure] = []

    if not po.line_items:
        failures.append(
            CheckFailure(CheckCode.NO_LINE_ITEMS, Severity.BLOCKER, "header", "", "0 lines", "")
        )
    else:
        passed.add(CheckCode.NO_LINE_ITEMS)
        lines_sum = _q2(
            sum(
                (
                    line.quantity * (line.unit_price if line.unit_price is not None else Decimal("0"))
                    for line in po.line_items
                ),
                Decimal("0"),
            )
        )
        if abs(lines_sum - po.total) > TOTAL_TOLERANCE:
            failures.append(
                CheckFailure(
                    CheckCode.TOTAL_MISMATCH,
                    Severity.BLOCKER,
                    "header",
                    str(po.total),
                    str(lines_sum),
                    str(abs(lines_sum - po.total)),
                )
            )
        else:
            passed.add(CheckCode.TOTAL_MISMATCH)

    neg = []
    if po.total < 0:
        neg.append("total")
    for line in po.line_items:
        if line.quantity < 0:
            neg.append(f"line {line.line_no} quantity")
        if line.unit_price is not None and line.unit_price < 0:
            neg.append(f"line {line.line_no} unit_price")
    if neg:
        failures.append(
            CheckFailure(CheckCode.NEGATIVE_AMOUNT, Severity.WARNING, "header", ">= 0", ",".join(neg), "")
        )
    else:
        passed.add(CheckCode.NEGATIVE_AMOUNT)

    if po.po_date > date.today():
        failures.append(
            CheckFailure(CheckCode.DATE_IN_FUTURE, Severity.WARNING, "header", "<= today", str(po.po_date), "")
        )
    else:
        passed.add(CheckCode.DATE_IN_FUTURE)

    missing = [
        name
        for name, value in (
            ("po_number", po.po_number),
            ("vendor_name", po.vendor_name),
        )
        if not value
    ]
    if missing:
        failures.append(
            CheckFailure(CheckCode.MISSING_REQUIRED_FIELD, Severity.BLOCKER, "header", "non-empty", ",".join(missing), "")
        )
    else:
        passed.add(CheckCode.MISSING_REQUIRED_FIELD)

    return _finish("po", passed, failures)


def validate_grni(g: GRNI) -> ValidationResult:
    passed: set[CheckCode] = set()
    failures: list[CheckFailure] = []

    if not g.line_items:
        failures.append(
            CheckFailure(CheckCode.NO_LINE_ITEMS, Severity.BLOCKER, "header", "", "0 lines", "")
        )
    else:
        passed.add(CheckCode.NO_LINE_ITEMS)

    neg = [f"line {line.line_no} quantity" for line in g.line_items if line.quantity < 0]
    if neg:
        failures.append(
            CheckFailure(CheckCode.NEGATIVE_AMOUNT, Severity.WARNING, "header", ">= 0", ",".join(neg), "")
        )
    else:
        passed.add(CheckCode.NEGATIVE_AMOUNT)

    if g.grni_date > date.today():
        failures.append(
            CheckFailure(CheckCode.DATE_IN_FUTURE, Severity.WARNING, "header", "<= today", str(g.grni_date), "")
        )
    else:
        passed.add(CheckCode.DATE_IN_FUTURE)

    missing = [
        name
        for name, value in (
            ("grn_number", g.grn_number),
            ("vendor_name", g.vendor_name),
        )
        if not value
    ]
    if missing:
        failures.append(
            CheckFailure(CheckCode.MISSING_REQUIRED_FIELD, Severity.BLOCKER, "header", "non-empty", ",".join(missing), "")
        )
    else:
        passed.add(CheckCode.MISSING_REQUIRED_FIELD)

    return _finish("grni", passed, failures)


def validate_pard(p: PaymentAdvice) -> ValidationResult:
    passed: set[CheckCode] = set()
    failures: list[CheckFailure] = []

    if p.amount < 0:
        failures.append(
            CheckFailure(CheckCode.NEGATIVE_AMOUNT, Severity.WARNING, "header", ">= 0", str(p.amount), "")
        )
    else:
        passed.add(CheckCode.NEGATIVE_AMOUNT)

    if p.payment_date > date.today():
        failures.append(
            CheckFailure(CheckCode.DATE_IN_FUTURE, Severity.WARNING, "header", "<= today", str(p.payment_date), "")
        )
    else:
        passed.add(CheckCode.DATE_IN_FUTURE)

    missing = [
        name
        for name, value in (
            ("pard_number", p.pard_number),
            ("invoice_number", p.invoice_number),
        )
        if not value
    ]
    if missing:
        failures.append(
            CheckFailure(CheckCode.MISSING_REQUIRED_FIELD, Severity.BLOCKER, "header", "non-empty", ",".join(missing), "")
        )
    else:
        passed.add(CheckCode.MISSING_REQUIRED_FIELD)

    return _finish("pard", passed, failures)


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
        vendor_tax_id=d.get("vendor_tax_id"),
        discount_amount=to_money(d["discount_amount"]) if d.get("discount_amount") is not None else None,
        source_file=d.get("source_file"),
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


_BUILDERS = {"invoice": _build_invoice, "po": _build_po, "grni": _build_grni, "pard": _build_pard}
_VALIDATORS = {
    "invoice": validate_invoice,
    "po": validate_po,
    "grni": validate_grni,
    "pard": validate_pard,
}


def _enum_to_value(obj):
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _enum_to_value(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_enum_to_value(v) for v in obj]
    return obj


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m apmatch.validation.arithmetic <doc_kind> <json_path>", file=sys.stderr)
        return 2
    doc_kind, json_path = argv
    if doc_kind not in _BUILDERS:
        print(f"unknown doc_kind: {doc_kind}", file=sys.stderr)
        return 2
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    try:
        doc = _BUILDERS[doc_kind](data)
    except TypeError as e:
        print(f"coercion error: {e}", file=sys.stderr)
        return 2
    result = _VALIDATORS[doc_kind](doc)
    payload = dataclasses.asdict(result)
    payload["ok"] = result.ok
    payload["has_blocker"] = result.has_blocker
    print(json.dumps(_enum_to_value(payload), indent=2))
    if result.ok:
        return 0
    if result.has_blocker:
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
