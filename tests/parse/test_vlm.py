"""VLM extraction: schema-constrained call, transcribe-then-parse, per-field robustness."""

import json
from datetime import date
from decimal import Decimal

import httpx
import pytest

import apmatch.parse.vlm as vlm
from apmatch.parse.dispatch import DocumentKind
from apmatch.schema.documents import GRNI, Invoice, PaymentAdvice, PurchaseOrder


class _Resp:
    def __init__(self, content: str, status: int = 200):
        self._content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            req = httpx.Request("POST", "http://x/api/chat")
            raise httpx.HTTPStatusError("bad", request=req, response=httpx.Response(self.status_code, request=req))

    def json(self):
        return {"message": {"role": "assistant", "content": self._content}}


@pytest.fixture(autouse=True)
def _no_digest_lookup(monkeypatch):
    monkeypatch.setattr(vlm, "model_digest", lambda *a, **k: "sha256:test")


def _img(tmp_path):
    p = tmp_path / "doc.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0fake")
    return p


def _serve(monkeypatch, payload_or_text, seen=None):
    content = payload_or_text if isinstance(payload_or_text, str) else json.dumps(payload_or_text)

    def fake_post(url, json=None, timeout=None):
        if seen is not None:
            seen.append({"url": url, "payload": json})
        return _Resp(content)

    monkeypatch.setattr(vlm.httpx, "post", fake_post)


INVOICE_PAYLOAD = {
    "invoice_number": "No.: INV-2025-1832",
    "vendor_name": "Mekong Supplies Co., Ltd.",
    "vendor_tax_id": "K004-113169017",
    "invoice_date": "03/04/2025",
    "invoice_date_iso": "2025-04-03",
    "currency": None,
    "po_number": "PO-2025-6578",
    "grn_number": None,
    "subtotal": "USD 1,175.55",
    "discount_amount": None,
    "tax_amount": "USD 117.56",
    "total": "USD 1,293.11",
    "line_items": [
        {"description": "Office chair", "quantity": "11", "unit_price": "37.20", "amount": "409.20"},
        {"description": "Desk lamp", "quantity": "9", "unit_price": "85.15", "amount": "766.35"},
    ],
}


def test_schemas_cover_all_kinds():
    assert set(vlm.SCHEMAS) == set(DocumentKind)


def test_invoice_transcribed_values_are_parsed_by_code(monkeypatch, tmp_path):
    seen: list = []
    _serve(monkeypatch, INVOICE_PAYLOAD, seen)
    res = vlm.extract_vlm_detailed(DocumentKind.INVOICE, _img(tmp_path))

    doc = res.document
    assert isinstance(doc, Invoice)
    assert doc.invoice_number == "INV-2025-1832"  # label prefix stripped
    assert doc.vendor_name == "Mekong Supplies Co., Ltd."
    assert doc.invoice_date == date(2025, 4, 3)
    assert doc.currency == "USD"  # detected from the printed amounts
    assert doc.subtotal == Decimal("1175.55")
    assert doc.tax_amount == Decimal("117.56")
    assert doc.total == Decimal("1293.11")
    assert doc.line_items[1].amount == Decimal("766.35")
    assert doc.line_items[1].line_no == 2
    assert res.error is None and res.field_errors == []
    assert res.model_digest == "sha256:test"
    assert res.prompt_version == vlm.PROMPT_VERSION
    assert res.format_used == "schema"

    payload = seen[0]["payload"]
    assert seen[0]["url"].endswith("/api/chat")
    assert payload["format"] == vlm.SCHEMAS[DocumentKind.INVOICE]  # structured output
    assert payload["options"]["temperature"] == 0.0
    assert payload["stream"] is False
    msg = payload["messages"][0]
    assert len(msg["images"]) == 1
    assert "exactly as printed" in msg["content"].lower()
    assert "NOT the 'Bill To'" in msg["content"]


def test_json_numbers_never_become_floats(monkeypatch, tmp_path):
    payload = dict(INVOICE_PAYLOAD, subtotal=1175.55, tax_amount=117.56, total=1293.11)
    payload["line_items"] = [{"description": "x", "quantity": 2, "unit_price": 10.5, "amount": 21.0}]
    _serve(monkeypatch, payload)
    doc = vlm.extract_vlm(DocumentKind.INVOICE, _img(tmp_path))
    assert doc.total == Decimal("1293.11")
    assert doc.line_items[0].unit_price == Decimal("10.5000")


def test_one_bad_field_does_not_lose_the_document(monkeypatch, tmp_path):
    payload = dict(INVOICE_PAYLOAD, total="illegible")
    payload["line_items"] = [
        {"description": "Office chair", "quantity": "eleven", "unit_price": "37.20", "amount": "409.20"},
    ]
    _serve(monkeypatch, payload)
    res = vlm.extract_vlm_detailed(DocumentKind.INVOICE, _img(tmp_path))
    assert isinstance(res.document, Invoice)
    assert res.document.total is None
    assert res.document.line_items[0].quantity is None
    assert res.document.line_items[0].amount == Decimal("409.20")
    assert any(e.startswith("total") for e in res.field_errors)
    assert any("quantity" in e for e in res.field_errors)


def test_retries_in_json_mode_when_schema_format_rejected(monkeypatch, tmp_path):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append(json["format"])
        if isinstance(json["format"], dict):
            return _Resp("", status=400)
        return _Resp(__import__("json").dumps(INVOICE_PAYLOAD))

    monkeypatch.setattr(vlm.httpx, "post", fake_post)
    res = vlm.extract_vlm_detailed(DocumentKind.INVOICE, _img(tmp_path))
    assert isinstance(calls[0], dict) and calls[1] == "json"
    assert res.format_used == "json"
    assert isinstance(res.document, Invoice)


def test_markdown_fence_and_surrounding_text(monkeypatch, tmp_path):
    _serve(monkeypatch, "```json\n" + json.dumps(INVOICE_PAYLOAD) + "\n```")
    assert isinstance(vlm.extract_vlm(DocumentKind.INVOICE, _img(tmp_path)), Invoice)
    _serve(monkeypatch, "Here is the JSON: " + json.dumps(INVOICE_PAYLOAD) + " done")
    assert isinstance(vlm.extract_vlm(DocumentKind.INVOICE, _img(tmp_path)), Invoice)


def test_connection_error_returns_none_with_reason(monkeypatch, tmp_path):
    def boom(url, json=None, timeout=None):
        raise httpx.ConnectError("no server")

    monkeypatch.setattr(vlm.httpx, "post", boom)
    res = vlm.extract_vlm_detailed(DocumentKind.INVOICE, _img(tmp_path))
    assert res.document is None and res.error.startswith("ConnectError")
    assert vlm.extract_vlm(DocumentKind.INVOICE, _img(tmp_path)) is None


def test_bad_json_returns_none(monkeypatch, tmp_path):
    _serve(monkeypatch, "not json at all")
    res = vlm.extract_vlm_detailed(DocumentKind.INVOICE, _img(tmp_path))
    assert res.document is None and res.raw_output == "not json at all"


def test_po_grni_pard(monkeypatch, tmp_path):
    cases = {
        DocumentKind.PURCHASE_ORDER: ({
            "po_number": "PO-2026-8066", "vendor_name": "V", "po_date": "1-Apr-2026",
            "po_date_iso": "2026-04-01", "currency": "KHR", "total": "1,036,000",
            "line_items": [{"description": "Widget", "quantity": "2", "unit_price": "518,000",
                            "amount": "1,036,000"}],
        }, PurchaseOrder),
        DocumentKind.GRNI: ({
            "grn_number": "GRN-2026-8112", "vendor_name": "V", "grni_date": "Apr 5, 2026",
            "grni_date_iso": "2026-04-05",
            "line_items": [{"description": "Widget", "quantity": "2 pcs"}],
        }, GRNI),
        DocumentKind.PAYMENT_ADVICE: ({
            "pard_number": "PARD-2026-8755", "invoice_number": "SM-5021", "amount": "$1,036.00",
            "currency": None, "payment_date": "30/04/2026", "payment_date_iso": "2026-04-30",
            "reference": "REF-1",
        }, PaymentAdvice),
    }
    for kind, (payload, cls) in cases.items():
        _serve(monkeypatch, payload)
        doc = vlm.extract_vlm(kind, _img(tmp_path))
        assert isinstance(doc, cls), kind
        if kind == DocumentKind.PURCHASE_ORDER:
            assert doc.total == Decimal("1036000.00") and doc.currency == "KHR"
            assert doc.po_date == date(2026, 4, 1)
        if kind == DocumentKind.GRNI:
            assert doc.line_items[0].quantity == Decimal("2.0000")
            assert doc.grni_date == date(2026, 4, 5)
        if kind == DocumentKind.PAYMENT_ADVICE:
            assert doc.amount == Decimal("1036.00") and doc.currency == "USD"


@pytest.mark.parametrize(
    ("printed", "iso", "expected"),
    [
        ("03/04/2026", "2026-03-04", date(2026, 3, 4)),  # ambiguous: model's reading wins
        ("03/04/2026", None, date(2026, 4, 3)),  # ambiguous, no reading: DD/MM default
        ("03/04/2026", "2026-12-25", date(2026, 4, 3)),  # model contradicts print: ignored
        ("25/12/2026", "2026-12-25", date(2026, 12, 25)),
        ("Mar 15, 2026", None, date(2026, 3, 15)),
        ("15th March 2026", None, date(2026, 3, 15)),
        ("១៥/០៣/២០២៦", "2026-03-15", date(2026, 3, 15)),  # unparseable print: model reading
        (None, None, None),
    ],
)
def test_resolve_date(printed, iso, expected):
    assert vlm.resolve_date(printed, iso) == expected


def test_currency_from_text():
    assert vlm.currency_from_text(None, "1,036,000 KHR") == "KHR"
    assert vlm.currency_from_text("៛") == "KHR"
    assert vlm.currency_from_text(None, "$12.00") == "USD"
    assert vlm.currency_from_text("Rs. 500") == "INR"
    assert vlm.currency_from_text(None, None) is None
