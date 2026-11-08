"""canonical_documents() -> documents_from_canonical() round-trips exactly."""

import json
from datetime import date
from decimal import Decimal as D

from apmatch.audit.hashing import canonical_documents, compute_input_hash
from apmatch.schema.documents import GRNI, Invoice, LineItem, PaymentAdvice, PurchaseOrder
from apmatch.schema.serialize import document_from_dict, documents_from_canonical


def _docs():
    line = LineItem(line_no=1, description="Chair", quantity=D("2.0000"),
                    unit_price=D("10.0000"), amount=D("20.00"))
    inv = Invoice(invoice_number="INV-1", vendor_name="V", invoice_date=date(2026, 1, 2),
                  currency="USD", subtotal=D("20.00"), tax_amount=D("2.00"), total=D("22.00"),
                  line_items=(line,), po_number="PO-1", vendor_tax_id="K001",
                  discount_amount=None, tax_rate=D("0.10"))
    po = PurchaseOrder(po_number="PO-1", vendor_name="V", po_date=date(2026, 1, 1),
                       total=D("20.00"), line_items=(line,), currency="USD")
    grni = GRNI(grn_number="GRN-1", vendor_name="V", grni_date=date(2026, 1, 1),
                line_items=(LineItem(line_no=1, description="Chair", quantity=D("2.0000")),))
    pard = PaymentAdvice(pard_number="P-1", invoice_number="INV-1", amount=D("22.00"),
                         payment_date=date(2026, 1, 5), reference=None, currency="USD")
    return inv, po, grni, pard


def test_round_trip_through_json_is_exact():
    docs = _docs()
    canonical = json.loads(json.dumps(canonical_documents(*docs)))
    rebuilt = documents_from_canonical(canonical)
    assert rebuilt == docs
    assert compute_input_hash(*rebuilt) == compute_input_hash(*docs)


def test_missing_documents_and_fields_stay_none():
    inv = document_from_dict("invoice", {"invoice_number": None, "line_items": []})
    assert inv.invoice_number is None and inv.total is None and inv.line_items == ()
    assert document_from_dict("po", None) is None
    assert documents_from_canonical({"invoice": {"line_items": []}})[1:] == (None, None, None)
