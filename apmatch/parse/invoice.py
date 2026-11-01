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
from apmatch.parse.spatial import (
    _COMPANY_SUFFIX_RE,
    find_vendor_heuristic,
    position_blocks,
    value_after_label_with_validation,
)
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
# Column headers that contain "total" but are NOT the document's total row.
# Always excluded from find_total_label (merged with the template's list).
_TOTAL_HEADER_NOISE = ("subtotal", "sub total", "total price", "line total")


def _select_template(blocks) -> Template:
    """Pick the template for these blocks; generic if none load or match."""
    templates = templates_by_id()
    if not templates:
        return Template(template_id="generic", style="generic")
    template, _ = select_template(blocks, templates)
    if template is None:
        return templates.get("generic") or Template(template_id="generic", style="generic")
    return template


_BUYER_MARKERS = ("bill to", "buyer", "paid by", "received by")


def _looks_like_company(s: str) -> bool:
    """True if s plausibly names a company (rejects 'China', 'No.', 'Bill To').

    A company name either carries a legal suffix / business-type noun (the
    shared _COMPANY_SUFFIX_RE) or is a multi-word title-cased phrase. A single
    word like "China" or a label like "No." fails both tests.
    """
    if not s or len(s) < 4:
        return False
    if _COMPANY_SUFFIX_RE.search(s):
        return True
    words = s.split()
    return len(words) >= 2 and all(w[:1].isupper() for w in words if w[:1].isalpha())


def _extract_vendor(blocks, vendor_spec) -> str | None:
    """Vendor by template strategy: labeled, heuristic, or labeled-then-heuristic.

    The labeled result is validated with _looks_like_company and a buyer-marker
    check, so a label that matches line-item text ("Imported from China") or a
    buyer label falls through to the heuristic instead of returning garbage.
    """
    labels = vendor_spec.labels or VENDOR_VARIANTS

    def _ok(value: str) -> bool:
        return _looks_like_company(value) and not any(b in value.lower() for b in _BUYER_MARKERS)

    if vendor_spec.strategy in ("labeled", "labeled_then_heuristic"):
        value = labeled_value(blocks, labels)
        if value is not None and _ok(value):
            return value
    if vendor_spec.strategy in ("heuristic", "labeled_then_heuristic"):
        block = find_vendor_heuristic(blocks)
        if block is not None:
            val = block.text.strip()
            if _ok(val):
                return val
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
    """Currency: template symbol/code map, then ISO token, then the default.

    The default is the template's ``currency.default`` when set (kh: no marker
    means local currency — KHR invoices omit the code, USD always prints "$"),
    else the global DEFAULT_CURRENCY.
    """
    if currency_spec.symbol_map:
        for block in blocks:
            for token, code in currency_spec.symbol_map:
                if token and token in block.text:
                    return code
    return detect_currency(blocks) or currency_spec.default or DEFAULT_CURRENCY


def extract_invoice(ocr: OCRResult) -> Invoice:
    blocks = ocr.text_blocks
    template = _select_template(blocks)

    inv_labels = template.invoice_number.labels or INVOICE_NUMBER_VARIANTS
    # us/in header layouts put the number ~356px right of the label, beyond the
    # 200px default; widen so the right search reaches it (PROD-B1c).
    invoice_number = parse_document_number(labeled_value(blocks, inv_labels, max_gap_px=400.0))
    # FIX: If the parser grabbed a date string, it's wrong. Reject it.
    if invoice_number and ("date" in invoice_number.lower() or "-" not in invoice_number and len(invoice_number) > 10):
        invoice_number = None
    if invoice_number is None and template.invoice_number.position_fallback:
        # Unlabeled number in a page corner (kh_sme layout). Try the zone's
        # blocks largest-first, skipping dates; parse_document_number rejects
        # digitless titles ("Invoice", "Invoice Pvelec").
        for fb in position_blocks(blocks, template.invoice_number.position_fallback):
            text = fb.text.strip()
            if parse_date(text) is not None:
                continue
            candidate = parse_document_number(text)
            if candidate is not None:
                invoice_number = candidate
                break

    vendor_name = _extract_vendor(blocks, template.vendor)

    invoice_date = _extract_date(blocks, template.invoice_date)

    currency = _extract_currency(blocks, template.currency)

    line_items = line_items_from_table(ocr, template)

    subtotal = labeled_money(blocks, template.totals.subtotal.labels or SUBTOTAL_VARIANTS)
    tax_amount = labeled_money(blocks, template.totals.tax.labels or TAX_VARIANTS)

    total = None
    # Base excludes (column headers like "Total Price") always apply; the
    # template's list adds style-specific variants.
    total_label = find_total_label(
        blocks,
        exclude=_TOTAL_HEADER_NOISE + tuple(template.totals.total_exclude_labels or ()),
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
