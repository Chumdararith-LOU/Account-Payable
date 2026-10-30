# Line-item alignment diagnostics

## Summary
- Cases analyzed: 59 (all failed cases from PROD-B1a)

- Dominant line-item category: similarity_below_review (33 cases, 56%)

## By category
| Category | Count | % of failures |
|---|---|---|
| similarity_below_review | 33 | 56% |
| no_invoice_lines | 16 | 27% |
| qty_mismatch | 6 | 10% |
| no_grn_lines | 2 | 3% |
| unmatched_other | 1 | 2% |
| no_po_lines | 1 | 2% |

## Report first-failure code (for correlation)
| First failure code | Count |
|---|---|
| MISSING_REQUIRED_FIELD | 48 |
| LINE_AMOUNT_MISMATCH | 11 |

## By style x category
| Style | Category | Count |
|---|---|---|
| in | similarity_below_review | 11 |
| in | no_invoice_lines | 4 |
| in | qty_mismatch | 1 |
| in | no_grn_lines | 1 |
| kh | similarity_below_review | 15 |
| kh | qty_mismatch | 3 |
| kh | no_invoice_lines | 2 |
| kh | unmatched_other | 1 |
| kh | no_po_lines | 1 |
| kh | no_grn_lines | 1 |
| us | no_invoice_lines | 10 |
| us | similarity_below_review | 7 |
| us | qty_mismatch | 2 |

## Concrete examples

### similarity_below_review — CASE-0001 (kh)
- Report first failure: LINE_AMOUNT_MISMATCH
- Detail: no candidates
- line 1: '' (qty=6.0000, amount=None) -> no_match
    po: no_match (best sim=None)
    grn: no_match (best sim=None)
- line 17: '' (qty=3.0000, amount=17.00) -> no_match
    po: no_match (best sim=None)
    grn: no_match (best sim=None)
- line 3: '' (qty=115.0000, amount=7.00) -> no_match
    po: no_match (best sim=None)
    grn: no_match (best sim=None)
- line 4: '234.60' (qty=345.0000, amount=1169.00) -> no_match
    po: no_match (best sim=0.1834)
      candidate: 'Cement (50kg bag)/' (sim=0.1834)
      candidate: 'Extension Cord/iejius' (sim=0.1742)
      candidate: 'Envelope (pack）/' (sim=0.1679)
    grn: no_match (best sim=0.1848)
      candidate: 'ExtensionCord/ieus' (sim=0.1848)
      candidate: 'Cement (50kg bag)/' (sim=0.1834)
      candidate: 'Stapler/su' (sim=0.166)

### similarity_below_review — CASE-0004 (kh)
- Report first failure: LINE_AMOUNT_MISMATCH
- Detail: max similarity = 0.368
- line 1: 'Whiteboard/s' (qty=1.0000, amount=75.75) -> no_match
    po: exact (line 1)
    grn: no_match (best sim=0.3679)
      candidate: '4' (sim=0.3679)
      candidate: '1' (sim=0.3093)
      candidate: '16' (sim=0.3083)
- line 2: 'ElectricFan/' (qty=16.0000, amount=1024.00) -> no_match
    po: sim_accept (line 2)
    grn: no_match (best sim=0.3163)
      candidate: '16' (sim=0.3163)
      candidate: '1' (sim=0.3085)
      candidate: '4' (sim=0.2802)
- line 3: 'AirConditioner/sn' (qty=4.0000, amount=2588.00) -> no_match
    po: exact (line 3)
    grn: no_match (best sim=0.1944)
      candidate: '1' (sim=0.1944)
      candidate: '4' (sim=0.1704)
      candidate: '16' (sim=0.0836)

### no_invoice_lines — CASE-0005 (us)
- Report first failure: MISSING_REQUIRED_FIELD
- Detail: invoice table parse returned empty

### no_invoice_lines — CASE-0006 (in)
- Report first failure: MISSING_REQUIRED_FIELD
- Detail: invoice table parse returned empty

### qty_mismatch — CASE-0010 (kh)
- Report first failure: MISSING_REQUIRED_FIELD
- Detail: invoice qty 157.0000 differs from matched line
- line 1: '6 27 20' (qty=157.0000, amount=None) -> qty_mismatch
    po: exact (line 1)
    grn: sim_accept (line 5)
- line 3: '62.50' (qty=1250.0000, amount=None) -> no_match
    po: sim_accept (line 4)
    grn: no_match (best sim=0.4538)
      candidate: '5' (sim=0.4538)
      candidate: '2' (sim=0.4516)
      candidate: '3' (sim=0.3885)
- line 4: '61 57' (qty=2.0000, amount=None) -> qty_mismatch
    po: sim_accept (line 4)
    grn: sim_review (line 5)

### qty_mismatch — CASE-0044 (us)
- Report first failure: MISSING_REQUIRED_FIELD
- Detail: invoice qty 54.5000 differs from matched line
- line 2: 'Chain replacement' (qty=54.5000, amount=None) -> qty_mismatch
    po: exact (line 4)
    grn: exact (line 4)
- line 2: '' (qty=12.2500, amount=None) -> no_match
    po: no_match (best sim=None)
    grn: no_match (best sim=None)
- line 3: '' (qty=76.0000, amount=None) -> no_match
    po: no_match (best sim=None)
    grn: no_match (best sim=None)
- line 1: 'Wheel truing' (qty=31.7500, amount=None) -> qty_mismatch
    po: sim_accept (line 5)
    grn: exact (line 5)
- line 5: '' (qty=None, amount=None) -> no_match
    po: no_match (best sim=None)
    grn: no_match (best sim=None)
- line 6: '' (qty=6.6250, amount=None) -> no_match
    po: no_match (best sim=None)
    grn: no_match (best sim=None)
- line 7: '' (qty=None, amount=None) -> no_match
    po: no_match (best sim=None)
    grn: no_match (best sim=None)

### unmatched_other — CASE-0073 (kh)
- Report first failure: LINE_AMOUNT_MISMATCH
- Detail: no failing line identified (line items align; failure is elsewhere)

### no_po_lines — CASE-0079 (kh)
- Report first failure: MISSING_REQUIRED_FIELD
- Detail: PO table parse returned empty
- line 1: '1' (qty=None, amount=1.00) -> no_match
    po: no_match (best sim=None)
    grn: no_match (best sim=None)
- line 2: '2' (qty=None, amount=50.00) -> no_match
    po: no_match (best sim=None)
    grn: no_match (best sim=None)

### no_grn_lines — CASE-0085 (kh)
- Report first failure: LINE_AMOUNT_MISMATCH
- Detail: GRN table parse returned empty
- line 1: 'Office Chair/nmjww' (qty=13.0000, amount=None) -> no_match
    po: exact (line 1)
    grn: no_match (best sim=None)
- line 2: '80' (qty=5.5000, amount=3.00) -> no_match
    po: no_match (best sim=0.4908)
      candidate: '4' (sim=0.4908)
      candidate: '143.00' (sim=0.4652)
      candidate: '5.50' (sim=0.3955)
    grn: no_match (best sim=None)
- line 3: '4' (qty=95.0000, amount=4.00) -> no_match
    po: exact (line 4)
    grn: no_match (best sim=None)
- line 4: '2.75' (qty=143.0000, amount=52.00) -> no_match
    po: sim_review (line 80)
    grn: no_match (best sim=None)

### no_grn_lines — CASE-0111 (in)
- Report first failure: MISSING_REQUIRED_FIELD
- Detail: GRN table parse returned empty
- line 1: 'RO Water Purifier 7L' (qty=1.0000, amount=None) -> no_match
    po: sim_accept (line 1)
    grn: no_match (best sim=None)
- line 2: 'Mixer Grinder 750W 3 Jars' (qty=2.0000, amount=None) -> no_match
    po: sim_accept (line 2)
    grn: no_match (best sim=None)
- line 3: 'Steel Almirah 4 Door' (qty=2.0000, amount=47223.60) -> no_match
    po: sim_accept (line 3)
    grn: no_match (best sim=None)

## Interpretation

**This is not an embedding problem.** The embedding model is behaving correctly: it
reports low similarity because the descriptions it is comparing are empty or numeric
garbage. The root cause is upstream, in the table parser
(`line_items_from_table`, `apmatch/parse/_table.py` / `_common.py`).

### Root cause 1 — table column mis-identification (39 cases, 66%)

`similarity_below_review` (33) + `qty_mismatch` (6). The parser picks the wrong
columns, so descriptions come out empty or as numbers (line numbers, quantities, or
amounts). Description quality across these 39 cases:

| Doc | Empty/numeric | % of lines |
|---|---|---|
| invoice | 148 / 238 | 62% |
| grn | 81 / 145 | 56% |
| po | 42 / 139 | 30% |

Invoice and GRN parsing are hit hardest; PO is less affected.

- **CASE-0004 (kh):** invoice and PO parse fine (`Whiteboard/s`, `ElectricFan/`),
  but the GRN descriptions are `'1'`, `'16'`, `'4'` — line numbers, not descriptions.
  Invoice→PO matches; invoice→GRN fails (sim ≈ 0.3).
- **CASE-0044 (us):** invoice quantities are `54.5`, `76`, `31.75` — these are
  amounts, not quantities. Several invoice descriptions are empty. The "quantity"
  column is actually holding the amount column.

Because descriptions are empty/numeric, exact match fails and similarity is very low
(0.1–0.4), so the engine correctly emits `NO_MATCHING_*`. The `qty_mismatch` cases
are the same bug seen from the quantity side: the quantity column holds an amount.

### Root cause 2 — table detection failure (19 cases, 32%)

`no_invoice_lines` (16) + `no_po_lines` (1) + `no_grn_lines` (2). The table is not
found/parsed at all, so the document yields zero line items. Invoice detection fails
most for the `us` style (10 of the 16 `no_invoice_lines` cases are `us`).

### Correlation with the header failures

48 of the 59 cases fail first on `MISSING_REQUIRED_FIELD` (a header validation
blocker, so matching never runs in the real pipeline). But the diagnostic shows most
of those cases **also** have broken line items. Fixing the header alone will not make
them pass — they would then fail on line-item matching. The table-parsing problem is
deeper and affects most cases regardless of the header.

## PROD-B1c recommendations (prioritized)

1. **Fix table column identification** in `line_items_from_table`
   (`apmatch/parse/_table.py` / `_common.py`). Highest impact (~39 cases, 66%).
   The description / quantity / amount columns are mis-identified, especially for
   invoice and GRN. Investigate the column-identification heuristic — it likely picks
   the wrong column when the table has a leading line-number column or when an amount
   column is present.
2. **Fix table detection** for `us`-style invoices (10 `no_invoice_lines`) and the
   GRN/PO empty-table cases (~19 cases, 32%). The layout engine is not finding the
   table, or the parser is not extracting it.
3. **Header `MISSING_REQUIRED_FIELD` (48 cases)** is a separate, template-driven
   issue, but it is not the bottleneck: most of those cases also have broken line
   items, so header fixes alone will not move the pass rate.

**Expected impact:** fixing root cause 1 + 2 addresses 58 of 59 failed cases (98%).
The remaining case (`unmatched_other`, CASE-0073) has aligned line items and fails on
a `LINE_AMOUNT_MISMATCH` that is not a line-alignment issue.
