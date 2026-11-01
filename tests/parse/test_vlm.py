"""VLM extraction: schemas, deserialization via the coercion boundaries, fallback."""

import json
from datetime import date
from decimal import Decimal

import apmatch.parse.vlm as vlm
from apmatch.parse.dispatch import DocumentKind
from apmatch.schema.documents import GRNI, Invoice, PaymentAdvice, PurchaseOrder


class _Resp:
    def __init__(self, content: str):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def _img(tmp_path):
    p = tmp_path / "doc.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0fake")
    return p


def test_schemas_cover_all_kinds():
    assert set(vlm.SCHEMAS) == set(DocumentKind)


def test_extract_invoice_success(monkeypatch, tmp_path):
    payload = {
        "invoice_number": "SM-5021",
        "vendor_name": "Sunshine Motors Service",
        "invoice_date": "2026-04-30",
        "currency": "USD",
        "subtotal": "1000.00",
        "tax_amount": "36.00",
        "total": "1036.00",
        "po_number": "2456_2026",
        "line_items": [
            {"line_no": 1, "description": "Oil change", "quantity": "1",
             "unit_price": "1000.00", "amount": "1000.00"},
        ],
    }
    seen = {}
    content = json.dumps(payload)

    def fake_post(url, json=None, timeout=None):
        seen.update(url=url, payload=json, timeout=timeout)
        return _Resp(content)

    monkeypatch.setattr(vlm.httpx, "post", fake_post)
    doc = vlm.extract_vlm(DocumentKind.INVOICE, _img(tmp_path))

    assert isinstance(doc, Invoice)
    assert doc.invoice_number == "SM-5021"
    assert doc.vendor_name == "Sunshine Motors Service"
    assert doc.invoice_date == date(2026, 4, 30)
    assert doc.total == Decimal("1036.00")
    assert doc.line_items[0].quantity == Decimal("1.0000")
    assert doc.po_number == "2456_2026"
    # Ollama JSON mode + schema injected into the prompt (no grammar backend)
    assert seen["payload"]["response_format"] == {"type": "json_object"}
    prompt_text = seen["payload"]["messages"][0]["content"][0]["text"]
    assert "JSON schema" in prompt_text and "invoice_number" in prompt_text
    # image sent as OpenAI-compatible multimodal content (not native "images")
    assert seen["payload"]["messages"][0]["content"][1]["type"] == "image_url"


def test_extract_invoice_markdown_wrapped(monkeypatch, tmp_path):
    payload = {"invoice_number": "INV-1", "vendor_name": "V", "invoice_date": "2026-01-01",
               "total": "10.00", "line_items": []}
    content = "```json\n" + json.dumps(payload) + "\n```"
    monkeypatch.setattr(
        vlm.httpx, "post",
        lambda url, json=None, timeout=None: _Resp(content),
    )
    doc = vlm.extract_vlm(DocumentKind.INVOICE, _img(tmp_path))
    assert isinstance(doc, Invoice) and doc.invoice_number == "INV-1"


def test_extract_returns_none_on_connection_error(monkeypatch, tmp_path):
    def boom(url, json=None, timeout=None):
        raise vlm.httpx.ConnectError("no vllm server")

    monkeypatch.setattr(vlm.httpx, "post", boom)
    assert vlm.extract_vlm(DocumentKind.INVOICE, _img(tmp_path)) is None


def test_extract_returns_none_on_bad_json(monkeypatch, tmp_path):
    monkeypatch.setattr(
        vlm.httpx, "post",
        lambda url, json=None, timeout=None: _Resp("not json at all"),
    )
    assert vlm.extract_vlm(DocumentKind.INVOICE, _img(tmp_path)) is None


def test_extract_po_grni_pard(monkeypatch, tmp_path):
    payloads = {
        DocumentKind.PURCHASE_ORDER: {
            "po_number": "PO-2026-8066", "vendor_name": "V", "po_date": "2026-04-01",
            "currency": "USD", "total": "500.00",
            "line_items": [{"line_no": 1, "description": "Widget", "quantity": "2",
                            "unit_price": "250.00", "amount": "500.00"}],
        },
        DocumentKind.GRNI: {
            "grn_number": "GRN-2026-8112", "vendor_name": "V", "grni_date": "2026-04-05",
            "line_items": [{"line_no": 1, "description": "Widget", "quantity": "2"}],
        },
        DocumentKind.PAYMENT_ADVICE: {
            "pard_number": "PARD-2026-8755", "invoice_number": "SM-5021",
            "amount": "1036.00", "payment_date": "2026-04-30", "reference": "REF-1",
        },
    }
    expected = {
        DocumentKind.PURCHASE_ORDER: PurchaseOrder,
        DocumentKind.GRNI: GRNI,
        DocumentKind.PAYMENT_ADVICE: PaymentAdvice,
    }
    for kind, payload in payloads.items():
        content = json.dumps(payload)
        monkeypatch.setattr(
            vlm.httpx, "post",
            lambda url, json=None, timeout=None, c=content: _Resp(c),
        )
        doc = vlm.extract_vlm(kind, _img(tmp_path))
        assert isinstance(doc, expected[kind]), kind

    # spot-check coercion on the PARD amount
    pard_content = json.dumps(payloads[DocumentKind.PAYMENT_ADVICE])
    monkeypatch.setattr(
        vlm.httpx, "post",
        lambda url, json=None, timeout=None: _Resp(pard_content),
    )
    pard = vlm.extract_vlm(DocumentKind.PAYMENT_ADVICE, _img(tmp_path))
    assert pard.amount == Decimal("1036.00")
    assert pard.invoice_number == "SM-5021"
