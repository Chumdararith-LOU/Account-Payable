"""Tamper-evidence hash over the four pipeline documents.

``compute_input_hash`` serializes the four documents to canonical JSON and
returns the SHA-256 hex digest. Same inputs -> same hash, byte-for-byte, across
processes and machines. This is the field a third party can recompute to verify
a stored decision was not altered.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from apmatch.schema.documents import GRNI, Invoice, PaymentAdvice, PurchaseOrder


def _canonical(obj):
    """Recursively convert a document (or nested value) to a JSON-serializable form.

    Rules (documented explicitly):
    - None -> None (preserved)
    - Decimal -> str (exact decimal representation, no float round-trip)
    - date / datetime -> ISO format string
    - Enum -> its ``.value``
    - dataclass -> dict of ``{field_name: _canonical(field_value)}``
    - tuple / list -> list of ``_canonical(item)`` (tuples become lists)
    - dict -> ``{key: _canonical(value)}``
    - str / int / float / bool -> as-is
    """
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _canonical(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (tuple, list)):
        return [_canonical(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _canonical(value) for key, value in obj.items()}
    return obj


def compute_input_hash(
    invoice: Invoice,
    po: PurchaseOrder | None,
    grni: GRNI | None,
    pard: PaymentAdvice | None,
) -> str:
    """SHA-256 hex digest over the canonical JSON of the four documents.

    Canonical JSON: ``sort_keys=True``, ``separators=(",", ":")``, Decimals as
    strings, dates as ISO, None preserved, tuples as lists.
    """
    payload = {
        "invoice": _canonical(invoice),
        "po": _canonical(po),
        "grni": _canonical(grni),
        "pard": _canonical(pard),
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
