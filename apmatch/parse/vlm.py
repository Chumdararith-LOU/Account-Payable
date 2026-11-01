"""VLM-based extraction using Qwen2.5-VL served by Ollama.

The pivot backend: one vision model reads the whole document and emits JSON
(schema injected into the prompt, JSON mode forced via response_format),
which is deserialized through the same strict coercion boundaries as the OCR
path (parse_document_number, parse_date, to_money / to_qty / to_unit_price).
Any failure — no server, HTTP error, bad JSON, coercion error — returns None
so the caller falls back to OCR + heuristics. The VLM is an enhancement,
never a hard dependency.

Network: the only call is to the local Ollama server (VLM_BASE_URL); no
external endpoints.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path

import httpx

from apmatch.parse.coerce import parse_date, parse_document_number
from apmatch.parse.dispatch import DocumentKind
from apmatch.schema.coercion import to_money, to_qty, to_unit_price
from apmatch.schema.documents import GRNI, Invoice, LineItem, PaymentAdvice, PurchaseOrder

logger = logging.getLogger(__name__)

# Ollama runs on the server host, bound to *:11434. The API runs in the
# apmatch-api container, so "localhost" would be the container itself — use
# the host's Tailscale IP (same pattern as the frontend's VITE_API_URL).
VLM_BASE_URL = os.getenv("VLM_BASE_URL", "http://100.88.94.91:11434/v1")
# Local Ollama model name (see `ollama list`).
VLM_MODEL = os.getenv("VLM_MODEL", "qwen2.5vl:7b")
# 7B Q4 on a 2080 Ti generates ~10-15 tok/s; a full invoice JSON is ~1K tokens.
VLM_TIMEOUT_S = float(os.getenv("VLM_TIMEOUT_S", "120"))

# Shared line-item properties (Invoice/PO carry price+amount; GRNI qty only).
_LINE_ITEM_PROPS = {
    "line_no": {"type": "integer"},
    "description": {"type": "string"},
    "quantity": {"type": ["string", "null"]},
    "unit_price": {"type": ["string", "null"]},
    "amount": {"type": ["string", "null"]},
}

# JSON Schemas — one per document kind, mirroring the fields in
# apmatch/schema/documents.py. Ollama has no grammar-constrained decoding, so
# these are injected into the prompt (response_format only guarantees valid
# JSON, not the schema).
SCHEMAS: dict[DocumentKind, dict] = {
    DocumentKind.INVOICE: {
        "type": "object",
        "properties": {
            "invoice_number": {"type": ["string", "null"]},
            "vendor_name": {"type": ["string", "null"]},
            "invoice_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
            "currency": {"type": ["string", "null"]},
            "subtotal": {"type": ["string", "null"]},
            "tax_amount": {"type": ["string", "null"]},
            "total": {"type": ["string", "null"]},
            "po_number": {"type": ["string", "null"]},
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": _LINE_ITEM_PROPS,
                    "required": ["line_no", "description", "quantity"],
                },
            },
        },
        "required": ["invoice_number", "vendor_name", "invoice_date", "total", "line_items"],
    },
    DocumentKind.PURCHASE_ORDER: {
        "type": "object",
        "properties": {
            "po_number": {"type": ["string", "null"]},
            "vendor_name": {"type": ["string", "null"]},
            "po_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
            "currency": {"type": ["string", "null"]},
            "total": {"type": ["string", "null"]},
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": _LINE_ITEM_PROPS,
                    "required": ["line_no", "description", "quantity"],
                },
            },
        },
        "required": ["po_number", "vendor_name", "po_date", "total", "line_items"],
    },
    DocumentKind.GRNI: {
        "type": "object",
        "properties": {
            "grn_number": {"type": ["string", "null"]},
            "vendor_name": {"type": ["string", "null"]},
            "grni_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
            # GRNI records quantities only — no price/amount (P1-08b-fix).
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "line_no": {"type": "integer"},
                        "description": {"type": "string"},
                        "quantity": {"type": ["string", "null"]},
                    },
                    "required": ["line_no", "description", "quantity"],
                },
            },
        },
        "required": ["grn_number", "vendor_name", "grni_date", "line_items"],
    },
    DocumentKind.PAYMENT_ADVICE: {
        "type": "object",
        "properties": {
            "pard_number": {"type": ["string", "null"]},
            "invoice_number": {"type": ["string", "null"]},
            "amount": {"type": ["string", "null"]},
            "payment_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
            "reference": {"type": ["string", "null"]},
            "currency": {"type": ["string", "null"]},
        },
        "required": ["pard_number", "invoice_number", "amount", "payment_date"],
    },
}


def _build_prompt(kind: DocumentKind) -> str:
    schema_str = json.dumps(SCHEMAS[kind], indent=2)
    return f"""You are an AP document extraction system.
Extract the fields from the image into JSON.
You MUST strictly follow this JSON schema:
{schema_str}

Rules:
- For dates, use YYYY-MM-DD.
- For numbers, use strings without commas (e.g. '1036000.00').
- If a field is missing, use null.
- Return ONLY valid JSON."""


def _encode_image(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _build_line_item(d: dict) -> LineItem:
    qty = to_qty(d["quantity"]) if d.get("quantity") else None
    price = to_unit_price(d["unit_price"]) if d.get("unit_price") else None
    amount = to_money(d["amount"]) if d.get("amount") else None
    return LineItem(
        line_no=d.get("line_no", 1),
        description=d.get("description", ""),
        quantity=qty,
        unit_price=price,
        amount=amount,
    )


def extract_vlm(kind: DocumentKind, image_path: Path) -> object | None:
    """Extract a document via the VLM. Returns None on any failure (fallback)."""
    try:
        base64_img = _encode_image(image_path)

        payload = {
            "model": VLM_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _build_prompt(kind)},
                        # OpenAI-compatible multimodal form (Ollama /v1). The
                        # native /api/chat "images" field is NOT accepted here.
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}},
                    ],
                }
            ],
            "temperature": 0.0,
            # Ollama JSON mode (OpenAI-compatible form of native "format": "json").
            "response_format": {"type": "json_object"},
        }

        response = httpx.post(f"{VLM_BASE_URL}/chat/completions", json=payload, timeout=VLM_TIMEOUT_S)
        response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        # Handle potential markdown wrapping (Ollama sometimes adds ```json).
        if content.startswith("```json"):
            content = content[7:-3]
        elif content.startswith("```"):
            content = content[3:-3]
        data = json.loads(content)

        # Deserialize based on kind
        if kind == DocumentKind.INVOICE:
            return Invoice(
                invoice_number=parse_document_number(data.get("invoice_number")),
                vendor_name=data.get("vendor_name"),
                invoice_date=parse_date(data.get("invoice_date")),
                currency=data.get("currency") or "USD",
                subtotal=to_money(data["subtotal"]) if data.get("subtotal") else None,
                tax_amount=to_money(data["tax_amount"]) if data.get("tax_amount") else None,
                total=to_money(data["total"]) if data.get("total") else None,
                line_items=tuple(_build_line_item(li) for li in data.get("line_items", [])),
                po_number=parse_document_number(data.get("po_number")),
            )
        if kind == DocumentKind.PURCHASE_ORDER:
            return PurchaseOrder(
                po_number=parse_document_number(data.get("po_number")),
                vendor_name=data.get("vendor_name"),
                po_date=parse_date(data.get("po_date")),
                total=to_money(data["total"]) if data.get("total") else None,
                line_items=tuple(_build_line_item(li) for li in data.get("line_items", [])),
                currency=data.get("currency"),
            )
        if kind == DocumentKind.GRNI:
            return GRNI(
                grn_number=parse_document_number(data.get("grn_number")),
                vendor_name=data.get("vendor_name"),
                grni_date=parse_date(data.get("grni_date")),
                line_items=tuple(_build_line_item(li) for li in data.get("line_items", [])),
            )
        if kind == DocumentKind.PAYMENT_ADVICE:
            return PaymentAdvice(
                pard_number=parse_document_number(data.get("pard_number")),
                invoice_number=parse_document_number(data.get("invoice_number")),
                amount=to_money(data["amount"]) if data.get("amount") else None,
                payment_date=parse_date(data.get("payment_date")),
                reference=data.get("reference"),
                currency=data.get("currency"),
            )

        return None
    except Exception as e:
        logger.warning(f"VLM extraction failed for {image_path}: {e}")
        return None
