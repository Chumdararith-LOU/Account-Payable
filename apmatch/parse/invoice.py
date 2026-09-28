"""Invoice extractor: OCRResult -> Invoice (P1-06 schema).

Total function: given ANY OCRResult (including empty), returns an Invoice.
Undetermined fields are None (or the documented default); the validator
(P1-06) is the layer that decides what is a blocker.

Label variants are module constants on purpose — diffable, no config file.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal

from apmatch.ocr.engine import OCRResult
from apmatch.parse._common import (
    company_name_fallback,
    find_total_label,
    labeled_money,
    labeled_money_at,
    labeled_value,
    line_items_from_table,
)
from apmatch.parse.coerce import (
    detect_currency,
    parse_date,
    parse_document_number,
)
from apmatch.schema.coercion import to_money
from apmatch.schema.documents import Invoice

INVOICE_NUMBER_VARIANTS = ("Invoice No", "Invoice Number", "INV No", "No.")
# Bare "Vendor" is deliberately absent: it matches the document title
# "VENDOR INVOICE" before the real "From (Vendor)" label.
VENDOR_VARIANTS = ("From (Vendor)", "Bill From", "Supplier")
DATE_VARIANTS = ("Date",)
SUBTOTAL_VARIANTS = ("Subtotal",)
TAX_VARIANTS = ("VAT", "Tax")
DEFAULT_CURRENCY = "USD"  # documented default when no ISO 4217 token is found


def extract_invoice(ocr: OCRResult) -> Invoice:
    blocks = ocr.text_blocks

    invoice_number = parse_document_number(labeled_value(blocks, INVOICE_NUMBER_VARIANTS))

    vendor_name = labeled_value(blocks, VENDOR_VARIANTS)
    if vendor_name is None:
        vendor_name = company_name_fallback(blocks)

    invoice_date = parse_date(labeled_value(blocks, DATE_VARIANTS))

    currency = detect_currency(blocks) or DEFAULT_CURRENCY

    line_items = line_items_from_table(ocr)

    subtotal = labeled_money(blocks, SUBTOTAL_VARIANTS)
    tax_amount = labeled_money(blocks, TAX_VARIANTS)

    total = None
    total_label = find_total_label(blocks)
    if total_label is not None:
        total = labeled_money_at(blocks, total_label.bbox)

    # Derivation policy (P1-10c-fix): preserve explicit source values, derive
    # implicit ones when the source omits them.
    line_amounts = [li.amount for li in line_items if li.amount is not None]
    if subtotal is None and line_amounts:
        subtotal = to_money(sum(line_amounts))
    if total is None and line_amounts:
        base = subtotal if subtotal is not None else to_money(sum(line_amounts))
        total = to_money(base + (tax_amount if tax_amount is not None else Decimal("0")))

    return Invoice(
        invoice_number=invoice_number,
        vendor_name=vendor_name,
        invoice_date=invoice_date,
        currency=currency,
        subtotal=subtotal,
        tax_amount=tax_amount,
        total=total,
        line_items=line_items,
        source_file=ocr.source_file,
    )


if __name__ == "__main__":
    from apmatch.parse.dispatch import dump_document, ocr_result_from_dict

    with open(sys.argv[1]) as f:
        print(dump_document(extract_invoice(ocr_result_from_dict(json.load(f)))))
