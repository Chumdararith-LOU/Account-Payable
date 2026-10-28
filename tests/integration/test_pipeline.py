"""First end-to-end proof of the deterministic decision path.

Runs the full chain — document dataclasses -> validation -> matching -> remark
— on committed JSON fixtures, with NO OCR, NO database, and NO network. Money
arrives as strings and is converted via the P1-06 coercion helpers. A guard
test asserts no ML / network import can leak into this layer.
"""

import ast
import json
from datetime import date
from pathlib import Path

from apmatch.matching.engine import MatchingEngine
from apmatch.matching.result import MatchCode, Outcome
from apmatch.remarks.matching import summarize_match
from apmatch.schema.coercion import to_money, to_qty, to_unit_price
from apmatch.schema.documents import GRNI, Invoice, LineItem, PaymentAdvice, PurchaseOrder
from apmatch.validation.arithmetic import validate_invoice
from apmatch.validation.result import Severity

FIXTURES = Path(__file__).resolve().parent / "fixtures"


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
        currency=d.get("currency"),
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
        currency=d.get("currency"),
    )


def _load(name: str):
    root = FIXTURES / name
    return (
        _build_invoice(json.loads((root / "invoice.json").read_text(encoding="utf-8"))),
        _build_po(json.loads((root / "po.json").read_text(encoding="utf-8"))),
        _build_grni(json.loads((root / "grni.json").read_text(encoding="utf-8"))),
        _build_pard(json.loads((root / "pard.json").read_text(encoding="utf-8"))),
    )


def test_happy_path_end_to_end(tmp_path):
    invoice, po, grni, pard = _load("happy_path")

    validation = validate_invoice(invoice)
    assert validation.ok is True

    result = MatchingEngine().match(invoice, po, grni, pard)
    assert result.outcome is Outcome.MATCH
    assert result.score == 1.0
    assert result.failures == ()

    assert summarize_match(result) == "All documents match."


def test_discrepancy_path_end_to_end(tmp_path):
    invoice, po, grni, pard = _load("discrepancy_path")

    result = MatchingEngine().match(invoice, po, grni, pard)
    assert result.outcome is Outcome.DISCREPANCY

    codes = {f.code for f in result.failures}
    assert {MatchCode.NO_MATCHING_PO_LINE, MatchCode.QTY_MISMATCH, MatchCode.PARD_AMOUNT_MISMATCH} <= codes

    assert result.failures[0].severity is Severity.BLOCKER

    remark = summarize_match(result)
    assert remark.startswith(f"{len(result.failures)} issue(s). Most severe:")
    assert "Payment advice amount mismatch" in remark


_FORBIDDEN_TOP = {
    "paddleocr",
    "tror_yong_ocr",
    "paddlex",
    "requests",
    "urllib",
    "httpx",
    "aiohttp",
    "socket",
    "http",
}
_FORBIDDEN_PREFIX = ("apmatch.ocr", "apmatch.layout")


def test_integration_has_no_ml_or_network_imports():
    for py in sorted(Path(__file__).resolve().parent.rglob("*.py")):
        # The demo module runs the real OCR pipeline by design (EMB-08);
        # the no-ML rule applies to the fast, deterministic tests only.
        if py.name == "test_embeddings_demo.py":
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for mod in modules:
                top = mod.split(".")[0]
                assert top not in _FORBIDDEN_TOP, f"{py.name}: forbidden import {mod!r}"
                assert not any(mod == p or mod.startswith(p + ".") for p in _FORBIDDEN_PREFIX), (
                    f"{py.name}: forbidden import {mod!r}"
                )
