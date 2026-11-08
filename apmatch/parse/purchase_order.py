"""Purchase-order extractor: OCRResult -> PurchaseOrder (P1-06 schema).

Total function: given ANY OCRResult (including empty), returns a
PurchaseOrder. Undetermined fields are None; the validator (P1-06) decides
what is a blocker.
"""

from __future__ import annotations

import json
import sys

from apmatch.ocr.engine import OCRResult
from apmatch.parse._common import (
    company_name_fallback,
    find_total_label,
    labeled_money_at,
    labeled_value,
    line_items_from_table,
)
from apmatch.parse.coerce import (
    detect_currency,
    parse_date,
    parse_document_number,
)
from apmatch.parse.template_loader import templates_by_id
from apmatch.parse.template_selector import select_template
from apmatch.parse.templates import Template
from apmatch.schema.coercion import to_money
from apmatch.schema.documents import PurchaseOrder

PO_NUMBER_VARIANTS = ("PO No", "Purchase Order No", "No.")
VENDOR_VARIANTS = ("Vendor", "Supplier", "From")
DATE_VARIANTS = ("Date",)


def _select_template(blocks) -> Template:
    """Pick the style template for these blocks; generic if none match."""
    templates = templates_by_id()
    if not templates:
        return Template(template_id="generic", style="generic")
    template, _ = select_template(blocks, templates)
    if template is None:
        return templates.get("generic") or Template(template_id="generic", style="generic")
    return template


def extract_purchase_order(ocr: OCRResult) -> PurchaseOrder:
    blocks = ocr.text_blocks
    template = _select_template(blocks)

    po_number = parse_document_number(labeled_value(blocks, PO_NUMBER_VARIANTS))

    # Vendor labels come from the style template (consistent with the invoice);
    # the hardcoded VENDOR_VARIANTS is the fallback when the template has none.
    vendor_name = labeled_value(blocks, template.vendor.labels or VENDOR_VARIANTS)
    if vendor_name is None:
        vendor_name = company_name_fallback(blocks)

    po_date = parse_date(labeled_value(blocks, DATE_VARIANTS))

    currency = detect_currency(blocks)  # optional field — None is a valid answer

    line_items = line_items_from_table(ocr)

    total = None
    total_label = find_total_label(blocks)
    if total_label is not None:
        total = labeled_money_at(blocks, total_label.bbox)

    # Derivation policy (P1-10c-fix): derive the total from line amounts when
    # the source omits it.
    line_amounts = [li.amount for li in line_items if li.amount is not None]
    if total is None and line_amounts:
        total = to_money(sum(line_amounts))

    return PurchaseOrder(
        po_number=po_number,
        vendor_name=vendor_name,
        po_date=po_date,
        total=total,
        line_items=line_items,
        currency=currency,
    )


if __name__ == "__main__":
    from apmatch.parse.dispatch import dump_document, ocr_result_from_dict

    with open(sys.argv[1]) as f:
        print(dump_document(extract_purchase_order(ocr_result_from_dict(json.load(f)))))
