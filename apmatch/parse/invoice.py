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
from apmatch.parse.spatial import find_vendor_heuristic, value_after_label_with_validation
from apmatch.parse.template_loader import templates_by_id
from apmatch.parse.template_selector import select_template
from apmatch.parse.templates import Template
from apmatch.schema.coercion import to_money
from apmatch.schema.documents import Invoice

# Hardcoded fallbacks: used when the selected template has empty label lists
# (the generic template) or when no templates are loaded at all. These are the
# pre-template constants, kept verbatim so the generic path is byte-identical
# to the legacy behavior.
INVOICE_NUMBER_VARIANTS = ("Invoice No", "Invoice Number", "INV No", "No.")
# Bare "Vendor" is deliberately absent: it matches the document title
# "VENDOR INVOICE" before the real "From (Vendor)" label.
VENDOR_VARIANTS = ("From (Vendor)", "Bill From", "Supplier")
DATE_VARIANTS = ("Date",)
SUBTOTAL_VARIANTS = ("Subtotal",)
TAX_VARIANTS = ("VAT", "Tax")
DEFAULT_CURRENCY = "USD"  # documented default when no ISO 4217 token is found


def _select_template(blocks) -> Template:
    """Pick the template for these blocks; generic if none load or match."""
    templates = templates_by_id()
    if not templates:
        return Template(template_id="generic", style="generic")
    template, _ = select_template(blocks, templates)
    if template is None:
        return templates.get("generic") or Template(template_id="generic", style="generic")
    return template


def _extract_vendor(blocks, vendor_spec) -> str | None:
    """Vendor by template strategy: labeled, heuristic, or labeled-then-heuristic."""
    labels = vendor_spec.labels or VENDOR_VARIANTS
    if vendor_spec.strategy in ("labeled", "labeled_then_heuristic"):
        value = labeled_value(blocks, labels)
        if value is not None:
            return value
    if vendor_spec.strategy in ("heuristic", "labeled_then_heuristic"):
        block = find_vendor_heuristic(blocks)
        if block is not None:
            return block.text.strip()
    return None


def _extract_date(blocks, date_spec):
    """Invoice date via candidate iteration (first candidate that parses wins)."""
    labels = date_spec.labels or DATE_VARIANTS
    formats = date_spec.formats or None  # None -> coerce layer's default formats

    def _parse(text: str):
        return parse_date(text, formats=formats)

    parsed, _ = value_after_label_with_validation(
        blocks,
        labels,
        _parse,
        candidate_order=date_spec.candidate_order or None,
        position_fallback=date_spec.position_fallback,
        # us/in header layouts put the date ~250px right of the label, beyond
        # the 200px default; widen so the right search reaches it instead of
        # falling through to the "below" search (which grabs the next label,
        # e.g. "DUE DATE", that fails date parsing).
        max_gap_px=400.0,
    )
    return parsed


def _extract_currency(blocks, currency_spec) -> str:
    """Currency: template symbol/code map, then ISO token, then the default."""
    if currency_spec.symbol_map:
        for block in blocks:
            for token, code in currency_spec.symbol_map:
                if token and token in block.text:
                    return code
    return detect_currency(blocks) or DEFAULT_CURRENCY


def extract_invoice(ocr: OCRResult) -> Invoice:
    blocks = ocr.text_blocks
    template = _select_template(blocks)

    inv_labels = template.invoice_number.labels or INVOICE_NUMBER_VARIANTS
    # us/in header layouts put the number ~356px right of the label, beyond the
    # 200px default; widen so the right search reaches it (PROD-B1c).
    invoice_number = parse_document_number(labeled_value(blocks, inv_labels, max_gap_px=400.0))

    vendor_name = _extract_vendor(blocks, template.vendor)

    invoice_date = _extract_date(blocks, template.invoice_date)

    currency = _extract_currency(blocks, template.currency)

    line_items = line_items_from_table(ocr, template)

    subtotal = labeled_money(blocks, template.totals.subtotal.labels or SUBTOTAL_VARIANTS)
    tax_amount = labeled_money(blocks, template.totals.tax.labels or TAX_VARIANTS)

    total = None
    total_label = find_total_label(
        blocks, exclude=template.totals.total_exclude_labels or ("subtotal",)
    )
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
    if tax_amount is None and total is not None and subtotal is not None:
        # total = subtotal - discount + tax; this parser does not extract
        # discount_amount (discount is 0), so tax = total - subtotal. Recovers
        # the tax value when OCR garbles its label but reads the amount.
        tax_amount = to_money(total - subtotal)

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
