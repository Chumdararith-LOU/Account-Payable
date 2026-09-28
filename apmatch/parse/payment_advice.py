"""Payment-advice extractor: OCRResult -> PaymentAdvice (P1-06 schema).

Flat document — no line items. Total function: given ANY OCRResult
(including empty), returns a PaymentAdvice. Undetermined fields are None;
the validator (P1-06) decides what is a blocker.
"""

from __future__ import annotations

import json
import sys

from apmatch.ocr.engine import OCRResult
from apmatch.parse._common import labeled_money, labeled_value
from apmatch.parse._table import find_column, parse_table_rows
from apmatch.parse.coerce import (
    detect_currency,
    parse_date,
    parse_document_number,
    parse_money,
)
from apmatch.schema.coercion import to_money
from apmatch.schema.documents import PaymentAdvice

PARD_NUMBER_VARIANTS = ("PARD No", "Payment No", "Receipt No", "No.")
INVOICE_VARIANTS = ("Ref. Invoice", "Invoice No", "Invoice")
DATE_VARIANTS = ("Date",)
AMOUNT_VARIANTS = ("TOTAL PAID", "Total", "Amount")


def extract_payment_advice(ocr: OCRResult) -> PaymentAdvice:
    blocks = ocr.text_blocks

    pard_number = parse_document_number(labeled_value(blocks, PARD_NUMBER_VARIANTS))
    invoice_number = parse_document_number(labeled_value(blocks, INVOICE_VARIANTS))
    payment_date = parse_date(labeled_value(blocks, DATE_VARIANTS))

    amount = labeled_money(blocks, AMOUNT_VARIANTS)
    if amount is None and ocr.tables:
        # Fallback: first data row of the first table, amount column.
        header, rows = parse_table_rows(ocr.tables[0].html)
        col_amount = find_column(header, "amount")
        if col_amount is not None and rows and col_amount < len(rows[0]):
            value = parse_money(rows[0][col_amount])
            amount = to_money(value) if value is not None else None

    currency = detect_currency(blocks)  # optional field — None is a valid answer

    return PaymentAdvice(
        pard_number=pard_number,
        invoice_number=invoice_number,
        amount=amount,
        payment_date=payment_date,
        reference=None,
        currency=currency,
    )


if __name__ == "__main__":
    from apmatch.parse.dispatch import dump_document, ocr_result_from_dict

    print(dump_document(extract_payment_advice(ocr_result_from_dict(json.load(open(sys.argv[1]))))))
