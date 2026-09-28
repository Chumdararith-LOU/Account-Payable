"""Tests for the tamper-evidence input hash.

No database needed — the hash is a pure function of the documents.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from apmatch.audit.hashing import compute_input_hash
from tests.store._builders import mk_grni, mk_invoice, mk_pard, mk_po

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_hash_is_deterministic():
    inv = mk_invoice(invoice_number="INV-HASH-1")
    po = mk_po(po_number="PO-HASH-1")
    assert compute_input_hash(inv, po, None, None) == compute_input_hash(inv, po, None, None)


def test_hash_changes_with_content():
    inv_a = mk_invoice(invoice_number="INV-HASH-2", total="100.00")
    inv_b = mk_invoice(invoice_number="INV-HASH-2", total="100.01")
    assert compute_input_hash(inv_a, None, None, None) != compute_input_hash(inv_b, None, None, None)


def test_hash_is_stable_across_processes():
    inv = mk_invoice(invoice_number="INV-HASH-PROC")
    expected = compute_input_hash(inv, None, None, None)
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from apmatch.audit.hashing import compute_input_hash\n"
        "from tests.store._builders import mk_invoice\n"
        "inv = mk_invoice(invoice_number='INV-HASH-PROC')\n"
        "print(compute_input_hash(inv, None, None, None))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)  # noqa: S603 — args hardcoded
    assert result.stdout.strip() == expected


def test_hash_is_64_hex_chars():
    inv = mk_invoice(invoice_number="INV-HASH-3")
    h = compute_input_hash(inv, None, None, None)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_handles_none_documents():
    inv = mk_invoice(invoice_number="INV-HASH-4")
    h = compute_input_hash(inv, None, None, None)
    assert len(h) == 64
    # A full set and a partial set differ.
    full = compute_input_hash(inv, mk_po(), mk_grni(), mk_pard())
    assert full != h
