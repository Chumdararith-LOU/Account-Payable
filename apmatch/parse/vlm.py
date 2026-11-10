"""VLM-based extraction using a vision-language model served by Ollama.

Design rule (D-109): the model READS, deterministic code DECIDES.

The model is asked to *transcribe* each field exactly as printed (numbers with
their separators and currency marks, dates in the printed format). Every value
is then converted by the same deterministic parsers the OCR path uses
(``parse_money`` / ``parse_qty`` / ``parse_document_number`` and a date
resolver that cross-checks the model's own ISO reading). The model never does
arithmetic and never decides anything; downstream validation and matching are
unchanged pure code.

Robustness rules:
- Output is constrained by passing the JSON schema in Ollama's ``format``
  field (structured outputs). If the server rejects that, the call is retried
  once with plain JSON mode and the schema in the prompt.
- JSON is parsed with ``parse_float=Decimal``: a number the model emits as a
  JSON number can never become a float.
- Coercion is per field and per line: one unparseable value becomes ``None``
  (recorded in ``field_errors``) instead of throwing the whole document away.
- Every call returns a ``VlmExtraction`` carrying the raw model output, the
  model name + digest, the prompt version and timings, so a decision can be
  explained and replayed later.

Network: the only call is to the local Ollama server (VLM_BASE_URL); no
external endpoints.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import httpx

from apmatch.parse.coerce import parse_document_number, parse_money, parse_qty
from apmatch.parse.dispatch import DocumentKind
from apmatch.schema.coercion import to_money, to_qty, to_unit_price
from apmatch.schema.documents import GRNI, Invoice, LineItem, PaymentAdvice, PurchaseOrder

logger = logging.getLogger(__name__)

# Ollama runs on the server host, bound to *:11434. The API runs in the
# apmatch-api container, so "localhost" would be the container itself — use
# the host address. NO /v1 suffix: the native /api/chat endpoint is used,
# because the OpenAI-compatible /v1 layer silently ignores "options".
VLM_BASE_URL = os.getenv("VLM_BASE_URL", "http://100.88.94.91:11434")
VLM_MODEL = os.getenv("VLM_MODEL", "qwen2.5vl:7b")
VLM_TIMEOUT_S = float(os.getenv("VLM_TIMEOUT_S", "180"))
VLM_NUM_CTX = int(os.getenv("VLM_NUM_CTX", "8192"))
# "schema": pass the JSON schema in `format` (Ollama structured outputs).
# "json":   plain JSON mode, schema only in the prompt (older Ollama).
VLM_FORMAT = os.getenv("VLM_FORMAT", "schema")

# Bump whenever the prompt or schemas change: it is recorded with every
# extraction and is part of the extraction-cache key.
PROMPT_VERSION = "2026-11-08.1"  # unchanged in PROD-B4: parsing changed, not the prompt

_STR = {"type": ["string", "null"]}


def _printed(desc: str) -> dict:
    return {"type": ["string", "null"], "description": desc}


_NUMBER_DESC = "exactly as printed, including separators and currency mark"
_DATE_DESC = "exactly as printed on the document"
_ISO_DESC = "the same date as YYYY-MM-DD"

_LINE_MONEY = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "description": _STR,
            "quantity": _printed(_NUMBER_DESC),
            "unit_price": _printed(_NUMBER_DESC),
            "amount": _printed(_NUMBER_DESC),
        },
        "required": ["description", "quantity", "unit_price", "amount"],
    },
}
_LINE_QTY = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "description": _STR,
            "quantity": _printed("quantity received, exactly as printed"),
        },
        "required": ["description", "quantity"],
    },
}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props)}


SCHEMAS: dict[DocumentKind, dict] = {
    DocumentKind.INVOICE: _obj({
        "invoice_number": _STR,
        "vendor_name": _STR,
        "vendor_tax_id": _STR,
        "invoice_date": _printed(_DATE_DESC),
        "invoice_date_iso": _printed(_ISO_DESC),
        "currency": _STR,
        "po_number": _STR,
        "grn_number": _STR,
        "subtotal": _printed(_NUMBER_DESC),
        "discount_amount": _printed(_NUMBER_DESC),
        "tax_amount": _printed(_NUMBER_DESC),
        "total": _printed(_NUMBER_DESC),
        "line_items": _LINE_MONEY,
    }),
    DocumentKind.PURCHASE_ORDER: _obj({
        "po_number": _STR,
        "vendor_name": _STR,
        "po_date": _printed(_DATE_DESC),
        "po_date_iso": _printed(_ISO_DESC),
        "currency": _STR,
        "total": _printed(_NUMBER_DESC),
        "line_items": _LINE_MONEY,
    }),
    DocumentKind.GRNI: _obj({
        "grn_number": _STR,
        "vendor_name": _STR,
        "grni_date": _printed(_DATE_DESC),
        "grni_date_iso": _printed(_ISO_DESC),
        "line_items": _LINE_QTY,
    }),
    DocumentKind.PAYMENT_ADVICE: _obj({
        "pard_number": _STR,
        "invoice_number": _STR,
        "amount": _printed(_NUMBER_DESC),
        "currency": _STR,
        "payment_date": _printed(_DATE_DESC),
        "payment_date_iso": _printed(_ISO_DESC),
        "reference": _STR,
    }),
}

_KIND_RULES: dict[DocumentKind, str] = {
    DocumentKind.INVOICE: (
        "This is a vendor INVOICE. vendor_name is the SELLER who issued the "
        "invoice (often labeled From / Vendor / Seller, or the company name at "
        "the top). It is NOT the 'Bill To' / buyer company. total is the final "
        "amount payable (Grand Total), not the subtotal."
    ),
    DocumentKind.PURCHASE_ORDER: (
        "This is a PURCHASE ORDER issued by a buyer. vendor_name is the "
        "SUPPLIER the order is addressed to (labeled Vendor / Supplier / To), "
        "NOT the company issuing the purchase order."
    ),
    DocumentKind.GRNI: (
        "This is a GOODS RECEIVED NOTE. vendor_name is the SUPPLIER who "
        "delivered the goods (labeled Vendor / Supplier / Delivered By), NOT "
        "the receiving company. quantity is the quantity RECEIVED (if there "
        "are both 'ordered' and 'received' columns, use 'received')."
    ),
    DocumentKind.PAYMENT_ADVICE: (
        "This is a PAYMENT ADVICE / remittance. pard_number is the payment "
        "advice's own number; invoice_number is the invoice being paid; amount "
        "is the amount paid."
    ),
}


def build_prompt(kind: DocumentKind) -> str:
    schema_str = json.dumps(SCHEMAS[kind], indent=2)
    return f"""You are a careful data-entry clerk. Transcribe fields from this document image into JSON.
{_KIND_RULES[kind]}

Rules:
- Copy every value EXACTLY as printed. Do not calculate, convert, round or reformat numbers.
  Keep thousands separators, decimal points and currency marks ("$1,036.50", "1,036,000 KHR").
- Dates: copy the printed text into the date field, and give your reading of it as YYYY-MM-DD in the *_iso field.
- Document numbers: copy the full number including its prefix (e.g. "INV-2026-1123"), without the label.
- line_items: every item row of the table, top to bottom, one object per row. Skip subtotal/tax/total rows.
  description: the item name as printed; if it is printed in both English and Khmer, give the English part only.
- If a field is not on the document, use null. Never invent values.
- Return ONLY JSON matching this schema:
{schema_str}"""


@dataclass
class VlmExtraction:
    """Everything one VLM call produced, for the audit trail and diagnostics."""

    document: object | None
    model: str
    model_digest: str | None
    prompt_version: str
    format_used: str | None = None
    raw_output: str | None = None
    error: str | None = None
    field_errors: list[str] = field(default_factory=list)
    date_candidates: list[date] = field(default_factory=list)
    duration_s: float = 0.0

    def summary(self) -> dict:
        """JSON-safe diagnostics (raw output included, truncated)."""
        return {
            "model": self.model,
            "model_digest": self.model_digest,
            "prompt_version": self.prompt_version,
            "format_used": self.format_used,
            "ok": self.document is not None,
            "error": self.error,
            "field_errors": list(self.field_errors),
            "date_candidates": [d.isoformat() for d in self.date_candidates],
            "duration_s": round(self.duration_s, 2),
            "raw_output": (self.raw_output or "")[:8000],
        }


# --- value coercion (deterministic) ---------------------------------------

_CURRENCY_MARKS = (
    ("៛", "KHR"), ("RIEL", "KHR"), ("KHR", "KHR"),
    ("₹", "INR"), ("INR", "INR"), ("RS.", "INR"), ("RS ", "INR"),
    ("US$", "USD"), ("USD", "USD"), ("$", "USD"),
    ("THB", "THB"), ("฿", "THB"), ("VND", "VND"), ("EUR", "EUR"), ("€", "EUR"),
)


def _text(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _num_str(v) -> str | None:
    """A model value as a string for the number parsers (Decimal/int stay exact)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    return str(v).strip() or None


def currency_from_text(*texts) -> str | None:
    """Currency code from a currency field or the printed amounts."""
    for t in texts:
        s = _text(t)
        if not s:
            continue
        up = s.upper()
        for mark, code in _CURRENCY_MARKS:
            if mark in up:
                return code
        if re.fullmatch(r"[A-Z]{3}", up):
            return up
    return None


def strong_currency(*texts) -> str | None:
    """Currency only from an explicit code or an unambiguous sign; a bare "$"
    is not enough (returns None so the case-level reconcile decides)."""
    for t in texts:
        s = _text(t)
        if not s:
            continue
        code = currency_from_text(s.upper().replace("US$", "USD").replace("$", ""))
        if code is not None and code != "USD":
            return code
        if "USD" in s.upper():
            return "USD"
    return None


def _money_value(v):
    s = _num_str(v)
    if s is None:
        return None
    # Drop words the parser does not know ("USD 1,000.00 only").
    parsed = parse_money(s)
    if parsed is None:
        m = re.search(r"\d[\d,]*(?:\.\d+)?", s)
        parsed = parse_money(m.group(0)) if m else None
    return parsed


def _docnum(v) -> str | None:
    s = _text(v)
    if s is None:
        return None
    s = re.sub(r"^(?:no\s*[.:]|number\s*[:.]?|#)\s*[:.]?\s*", "", s, flags=re.IGNORECASE)
    if _date_candidates(s):
        return None  # the model put a date in a document-number field
    return parse_document_number(s.replace(" ", ""))


_DMY = ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y")
_MDY = ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y")
_OTHER = (
    "%Y-%m-%d", "%Y/%m/%d",
    "%d-%b-%Y", "%d-%b-%y", "%d %b %Y", "%d %B %Y", "%d-%B-%Y", "%d %b, %Y",
    "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y",
)


def _date_candidates(raw: str) -> list[date]:
    text = re.sub(r"\s+", " ", raw.strip()).rstrip(".")
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE)
    out: list[date] = []
    for fmt in _DMY + _MDY + _OTHER:
        try:
            d = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        if d not in out:
            out.append(d)
    return out


def resolve_date(printed, iso) -> date | None:
    """Pick the date: the model's ISO reading only if the printed text allows it.

    - printed text parses to one date -> that date
    - printed text is ambiguous (03/04/2026) -> the model's ISO reading when it
      is one of the candidates, else DD/MM (regional default, D-043)
    - printed text unparseable -> the model's ISO reading (may be None)
    """
    iso_date = None
    s_iso = _text(iso)
    if s_iso:
        try:
            iso_date = date.fromisoformat(s_iso[:10])
        except ValueError:
            iso_date = None
    s = _text(printed)
    candidates = _date_candidates(s) if s else []
    if iso_date is not None and iso_date in candidates:
        return iso_date
    if candidates:
        return candidates[0]
    return iso_date


# The main date field of each document kind (printed text, model's ISO reading).
DATE_FIELDS: dict[DocumentKind, str] = {
    DocumentKind.INVOICE: "invoice_date",
    DocumentKind.PURCHASE_ORDER: "po_date",
    DocumentKind.GRNI: "grni_date",
    DocumentKind.PAYMENT_ADVICE: "payment_date",
}


def date_candidates(kind: DocumentKind, data: dict) -> list[date]:
    """Every date the printed text can mean (two for "03/04/2026", one otherwise).

    Used by the case-level reconcile step to pick, for ambiguous dates, the
    reading that gives a coherent PO -> GRN -> invoice -> payment order.
    Falls back to the single resolved date when the print is unparseable.
    """
    name = DATE_FIELDS[DocumentKind(kind)]
    printed = _text(data.get(name))
    cands = _date_candidates(printed) if printed else []
    if cands:
        return cands
    resolved = resolve_date(printed, data.get(f"{name}_iso"))
    return [resolved] if resolved else []


def _lines(items, field_errors: list[str], with_money: bool) -> tuple[LineItem, ...]:
    out: list[LineItem] = []
    if not isinstance(items, list):
        return ()
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            field_errors.append(f"line {idx}: not an object")
            continue
        desc = _text(item.get("description")) or ""
        qty = price = amount = None
        q = parse_qty(_num_str(item.get("quantity")))
        if q is not None:
            qty = to_qty(q)
        elif item.get("quantity") is not None:
            field_errors.append(f"line {idx}: quantity {item.get('quantity')!r}")
        if with_money:
            p = _money_value(item.get("unit_price"))
            if p is not None:
                price = to_unit_price(p)
            elif item.get("unit_price") is not None:
                field_errors.append(f"line {idx}: unit_price {item.get('unit_price')!r}")
            a = _money_value(item.get("amount"))
            if a is not None:
                amount = to_money(a)
            elif item.get("amount") is not None:
                field_errors.append(f"line {idx}: amount {item.get('amount')!r}")
        if not desc and qty is None and price is None and amount is None:
            continue  # an empty row the model emitted
        out.append(
            LineItem(
                line_no=len(out) + 1,
                description=desc,
                quantity=qty,
                unit_price=price,
                amount=amount,
            )
        )
    return tuple(out)


def _money_field(data: dict, key: str, field_errors: list[str]):
    v = data.get(key)
    m = _money_value(v)
    if m is None:
        if v not in (None, ""):
            field_errors.append(f"{key}: {v!r}")
        return None
    return to_money(m)


def document_from_payload(kind: DocumentKind, data: dict, field_errors: list[str]):
    """Build the schema dataclass from the model's JSON. Never raises for bad values."""
    if kind == DocumentKind.INVOICE:
        # No default here: when the invoice prints no currency — or only a
        # bare "$", which the model also reports for the riel sign — the
        # case-level reconcile step takes it from the PO / payment advice (D-114).
        currency = strong_currency(data.get("currency"), data.get("total"), data.get("subtotal"))
        return Invoice(
            invoice_number=_docnum(data.get("invoice_number")),
            vendor_name=_text(data.get("vendor_name")),
            invoice_date=resolve_date(data.get("invoice_date"), data.get("invoice_date_iso")),
            currency=currency,
            subtotal=_money_field(data, "subtotal", field_errors),
            tax_amount=_money_field(data, "tax_amount", field_errors),
            total=_money_field(data, "total", field_errors),
            line_items=_lines(data.get("line_items"), field_errors, with_money=True),
            po_number=_docnum(data.get("po_number")),
            grn_number=_docnum(data.get("grn_number")),
            vendor_tax_id=_text(data.get("vendor_tax_id")),
            discount_amount=_money_field(data, "discount_amount", field_errors),
        )
    if kind == DocumentKind.PURCHASE_ORDER:
        return PurchaseOrder(
            po_number=_docnum(data.get("po_number")),
            vendor_name=_text(data.get("vendor_name")),
            po_date=resolve_date(data.get("po_date"), data.get("po_date_iso")),
            total=_money_field(data, "total", field_errors),
            line_items=_lines(data.get("line_items"), field_errors, with_money=True),
            currency=currency_from_text(data.get("currency"), data.get("total")),
        )
    if kind == DocumentKind.GRNI:
        return GRNI(
            grn_number=_docnum(data.get("grn_number")),
            vendor_name=_text(data.get("vendor_name")),
            grni_date=resolve_date(data.get("grni_date"), data.get("grni_date_iso")),
            line_items=_lines(data.get("line_items"), field_errors, with_money=False),
        )
    if kind == DocumentKind.PAYMENT_ADVICE:
        return PaymentAdvice(
            pard_number=_docnum(data.get("pard_number")),
            invoice_number=_docnum(data.get("invoice_number")),
            amount=_money_field(data, "amount", field_errors),
            payment_date=resolve_date(data.get("payment_date"), data.get("payment_date_iso")),
            reference=_text(data.get("reference")),
            currency=currency_from_text(data.get("currency"), data.get("amount")),
        )
    raise ValueError(f"unknown document kind {kind!r}")


def parse_model_json(content: str) -> dict:
    """Parse the model's reply. Tolerates ```json fences and text around the object."""
    text = content.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start : end + 1], parse_float=Decimal)
    if not isinstance(data, dict):
        raise ValueError("model output is not a JSON object")
    return data


# --- Ollama call ------------------------------------------------------------


_DIGESTS: dict[tuple[str, str], str] = {}


def model_digest(base_url: str = VLM_BASE_URL, model: str = VLM_MODEL) -> str | None:
    """The served model's digest (identifies the exact weights). None if unknown.

    Successful lookups are cached per process; failures are not, so a server
    that comes up later is still identified.
    """
    key = (base_url, model)
    if key in _DIGESTS:
        return _DIGESTS[key]
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=3)
        resp.raise_for_status()
        for m in resp.json().get("models", []):
            if m.get("name") == model or m.get("model") == model:
                digest = m.get("digest")
                if digest:
                    _DIGESTS[key] = digest
                return digest
    except Exception:
        return None
    return None


def _encode_image(image_path: Path) -> str:
    return base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")


def _payload(kind: DocumentKind, image_b64: str, fmt) -> dict:
    return {
        "model": VLM_MODEL,
        "messages": [{"role": "user", "content": build_prompt(kind), "images": [image_b64]}],
        "format": fmt,
        "options": {"num_ctx": VLM_NUM_CTX, "temperature": 0.0, "seed": 0},
        "stream": False,
    }


def _chat(kind: DocumentKind, image_b64: str) -> tuple[str, str]:
    """POST to Ollama. Returns (content, format_used). Raises on failure."""
    formats = ["schema", "json"] if VLM_FORMAT == "schema" else ["json"]
    last_exc: Exception | None = None
    for fmt_name in formats:
        fmt = SCHEMAS[kind] if fmt_name == "schema" else "json"
        try:
            resp = httpx.post(
                f"{VLM_BASE_URL}/api/chat", json=_payload(kind, image_b64, fmt), timeout=VLM_TIMEOUT_S
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"], fmt_name
        except httpx.HTTPStatusError as exc:
            # An older Ollama rejects a schema in `format`: retry in JSON mode.
            last_exc = exc
            continue
    assert last_exc is not None
    raise last_exc


def extract_vlm_detailed(kind: DocumentKind, image_path: Path) -> VlmExtraction:
    """Run one extraction and return the document plus full diagnostics."""
    kind = DocumentKind(kind)
    result = VlmExtraction(
        document=None,
        model=VLM_MODEL,
        model_digest=model_digest(VLM_BASE_URL, VLM_MODEL),
        prompt_version=PROMPT_VERSION,
    )
    t0 = time.time()
    try:
        content, result.format_used = _chat(kind, _encode_image(Path(image_path)))
        result.raw_output = content
        data = parse_model_json(content)
        result.document = document_from_payload(kind, data, result.field_errors)
        result.date_candidates = date_candidates(kind, data)
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {str(exc)[:300]}"
        logger.warning("VLM extraction failed for %s: %s", Path(image_path).name, result.error)
    result.duration_s = time.time() - t0
    return result


def extract_vlm(kind: DocumentKind, image_path: Path) -> object | None:
    """Backward-compatible wrapper: the document, or None on failure (fallback)."""
    return extract_vlm_detailed(kind, image_path).document
