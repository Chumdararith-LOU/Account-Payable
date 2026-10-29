# Batch failure diagnostics — 120-case baseline

## Summary
Total failures: 59

Top missing field: invoice_date (36 cases)

## By missing field
| Field | Count | % of failures |
|---|---|---|
| invoice_date | 36 | 61% |
| vendor_name | 34 | 58% |
| invoice_number | 33 | 56% |
| line_items | 16 | 27% |
| subtotal | 6 | 10% |
| tax_amount | 6 | 10% |
| total | 2 | 3% |

## By failure category
| Category | Count | Meaning |
|---|---|---|
| label_not_found | 92 | No OCR block contains a known label for this field |
| value_parse_failed | 24 | Label and value both found, but value couldn't be converted |
| table_structure | 16 | Line items missing — table parse failed |
| other | 1 |  |

## By style x missing field (top combos)
| Style | Missing fields | Count |
|---|---|---|
| kh | (none) | 21 |
| in | invoice_date, invoice_number, vendor_name | 10 |
| us | invoice_date, invoice_number, line_items, vendor_name | 8 |
| us | invoice_date, invoice_number, vendor_name | 7 |
| in | invoice_date, vendor_name | 3 |
| in | invoice_date, invoice_number, line_items, subtotal, tax_amount, vendor_name | 2 |
| us | invoice_date, invoice_number | 2 |
| in | invoice_number, line_items, subtotal, tax_amount, vendor_name | 1 |
| in | invoice_date, invoice_number, line_items, subtotal, tax_amount, total, vendor_name | 1 |
| kh | invoice_date, line_items, subtotal, tax_amount, vendor_name | 1 |
| kh | line_items, tax_amount, total | 1 |
| us | invoice_date, invoice_number, line_items, subtotal, vendor_name | 1 |

## Concrete examples

### Example 1: CASE-0005 (us)
- Expected: MATCH
- Actual route: REJECT
- Missing: invoice_number, vendor_name, invoice_date, line_items
  - invoice_number: **label_not_found**
    - OCR block: 'INVOICE'
    - OCR block: 'Sunshine Motors Service'
    - OCR block: 'INVOICE #'
  - vendor_name: **label_not_found**
    - OCR block: 'BILL TO'
  - invoice_date: **value_parse_failed**
    - OCR block: 'INVOICE DATE' (value='P.0.#')
  - line_items: **table_structure**
- What the document shows (raw OCR):
```
INVOICE
LOGO
Sunshine Motors Service
615 Palm Boulevard
Miami, FL 33130
BILL TO
SHIP TO
INVOICE #
US-275
Coral Limo Service
Maria Garcia
INVOICE DATE
Mar 15, 2026
Jessica Martinez
18 Elm Street
P.0.#
PO-84689
21 Coral Way
Cambridge, MA 02139
Miami, FL 33145
DUE DATE
Apr 29, 2026
UNIT PRICE
AMOUNT
QTY
DESCRIPTION
88.00
44.00
2
bulb, Headlight
91.50
91.50
1
Diagnostic fee
36.00
36.00
1
Wheel truing
Subtotal
215.50
13.47
Sales Tax 6.25%
TOTAL
$228.97
D. Lee
TERMS & CONDITIONS
Thank you
Payment is due within 45 days
```

### Example 2: CASE-0091 (kh)
- Expected: MATCH
- Actual route: REJECT
- Missing: tax_amount, total, line_items
  - tax_amount: **label_not_found**
  - total: **other**
    - OCR block: 'Subtotal /' (value='USD 1,175.55')
  - line_items: **table_structure**
- What the document shows (raw OCR):
```
KINGDOM OF CAMBODIA - NATION RELIGION KING
VENDOR INVOICE
Iğwuja
No.: INV-2025-1832
Date: 03/04/2025
មានលក់គ្រឿងសំណង់គ្រប់ប្រភេទ
From (Vendor)/n
Mekong Supplies Co., Ltd.
Bayon Office Solutions Co., Ltd.
81007 7 ថ្នាំ 1ថែរក្សា (ការ៉េម
vus mąa yga zze ggvał
No. 88, Street 214, Sangkat Veal Vong, Khan 7
No. 7B, Street 63, Sangkat Boeung Keng Kang 1,
Makara, Phnom Penh, Cambodia
Khan Boeung Keng Kang, Phnom Penh, Cambodia
TIN: K004-113169017 Tel: +855 17 464 601
TIN: K006-494159510  Tel: +855 77 629 620
Ref. PO No.: PO-2025-6578
Description / ulunw
Qty
Unit Price (USD)
Amount (USD)
ស្រីមានលក់
11
37.20
409.20
2
ទី 047 / 077 តកកាត់
9
85.15
766.35
USD 1,175.55
Subtotal /
USD 117.56
ទទទួលបង្រៀនសិស្សានុស្សចាស់ធារណៈរដ្ឋបាលខេត្តបាត់ដំបង និងប្រទេសកម្ពុជា
TOTAL/ NJU  USD 1,293.11
Payment due within 7 days.
Issued by (Vendor)
Approved by (Buyer)
PAID
```

## Immediate fix targets (for PROD-B1)

### High-priority label variants to add (from `label_not_found`, 92 field-hits)
- **invoice_number (33 cases)** — documents use `INVOICE` / `INVOICE #` as the label;
  `INVOICE_NUMBER_VARIANTS` only has `("Invoice No", "Invoice Number", "INV No", "No.")`.
  Add `"INVOICE"` and `"INVOICE #"`.
- **vendor_name (34 cases)** — documents label the *buyer* as `BILL TO` / `Bill to` and
  leave the vendor as an unlabeled company name at the top. `VENDOR_VARIANTS`
  (`"From (Vendor)"`, `"Bill From"`, `"Supplier"`) never matches. Needs a vendor
  heuristic (top company-name block) or new variants.
- **invoice_date (36 cases)** — documents use `INVOICE DATE` (or no date label at all).
  `DATE_VARIANTS` is just `("Date",)`. Add `"Invoice Date"`.

### High-priority format / false-match fixes (from `value_parse_failed`, 24 field-hits)
- **`Date` label false-matches P.O. blocks (18 cases)** — the bare `"Date"` variant
  matches `P.O.#` / `P.0.#` / `P.O.B` blocks, so the "value" is a P.O. number, not a
  date. Make the date label more specific (`"Invoice Date"`) so it stops grabbing P.O.
  blocks.
- **Date format `%b %d, %Y` (e.g. `Mar 15, 2026`)** — `parse_date` only tries
  `%d-%b-%Y`, `%Y-%m-%d`, `%d/%m/%Y`, `%m/%d/%Y`. Add `%b %d, %Y`.
- **`Tax`/`VAT` label grabs an `Amount` block (4 cases)** and **`Total` grabs
  `ENTERED` (1 case)** — the money labels are too loose; tighten them.

### High-priority table fixes (from `table_structure`, 16 cases)
- Line items are missing even when the table is visible (columns `QTY` / `UNIT PRICE` /
  `AMOUNT` / `DESCRIPTION` are present in the OCR). The table detection / column
  mapping is failing on these layouts — needs a table-structure pass.

## The kh puzzle (17/40 pass)

23 kh cases fail, but **21 of them have zero missing header fields** (`missing=[]`) —
the parser extracts every header field correctly. They fail downstream, in the
**line-item match**:

| kh failure signal | count (of 23) |
|---|---|
| NO_MATCHING_GRNI_LINE / NO_MATCHING_PO_LINE | 17 |
| LINE_AMOUNT_MISMATCH | 10 |

Root cause: kh invoices carry **many line items (11+)** whose descriptions are Khmer
and OCR-garbled (e.g. `ស្រីមានលក់`, `ទី 047 / 077 តកកាត់`). The exact-match on
`normalize_text(description)` fails, the lines misalign, and the amounts no longer
line up (`LINE_AMOUNT_MISMATCH` with wildly different expected/actual, e.g.
`exp='121000000.00' act='11000.00'`). This is a **line-item matching** problem, not a
header-label problem — the embedding similarity fallback is not rescuing the garbled
Khmer descriptions. It is a separate workstream from the header-label fixes above.

## What this tells us about PROD-B1 scope

The failures split into two independent workstreams. **(1) Header labels** — 92
`label_not_found` hits across `invoice_number` / `vendor_name` / `invoice_date`, plus
24 `value_parse_failed` from loose labels and a missing date format. This is the
high-leverage, template-absorbable work: add the `INVOICE`/`INVOICE #`/`INVOICE DATE`
variants, a vendor heuristic, the `%b %d, %Y` format, and tighten the money labels.
Closing most of these would lift the 50.8% baseline substantially (the 48
`MISSING_REQUIRED_FIELD` rejections are almost all in this bucket). **(2) Line-item
matching** — the 16 `table_structure` misses and the 21 kh no-missing-field failures
are table-parse and Khmer-description alignment problems that the current
description-keyed matcher (with its embedding fallback) does not absorb; they need a
dedicated table/alignment pass, likely beyond the first template iteration.
