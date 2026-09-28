"""
Generates a consistent set of Cambodia-format business documents for testing
ai_engine.py: Purchase Order, Goods Received Note (GRNI), Vendor Invoice, and
Payment Advice & Receipt Doc (PARD) — all referencing the same case so the
3-way match should resolve to MATCH.

Built as HTML/CSS and rendered via WeasyPrint (Pango/HarfBuzz backed), which
shapes Khmer script correctly (subscripts, vowel reordering) — ReportLab does
not do this and produces broken glyphs / dotted-circle placeholders.

Output: PDF + PNG (200dpi) for each doc, ready to drop into:
    documents/po/, documents/grni/, documents/invoice/, documents/pard/
"""

import os
import subprocess

from weasyprint import HTML

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_docs")
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Shared case data
# ---------------------------------------------------------------------------
BUYER = {
    "name_en": "Golden Angkor Trading Co., Ltd.",
    "name_km": "ក្រុមហ៊ុន ហ្គោលដិន អង្គរ ត្រេឌីង ខូអិលធីឌី",
    "address": "No. 12, Street 271, Sangkat Boeung Tumpun, Khan Mean Chey, Phnom Penh, Cambodia",
    "tin": "K001-987654321",
    "tel": "+855 23 555 123",
}
VENDOR = {
    "name_en": "Mekong Supplies Co., Ltd.",
    "name_km": "ក្រុមហ៊ុន មេគង្គ ស៊ុបផ្លាយ ខូអិលធីឌី",
    "address": "No. 88, Street 214, Sangkat Veal Vong, Khan 7 Makara, Phnom Penh, Cambodia",
    "tin": "K002-123456789",
    "tel": "+855 23 987 654",
}

PO_NO, PO_DATE = "PO-2026-0451", "15-Aug-2026"
GRN_NO, GRN_DATE = "GRN-2026-0322", "19-Aug-2026"
INV_NO, INV_DATE = "INV-2026-1123", "20-Aug-2026"
PARD_NO, PARD_DATE = "PARD-2026-0210", "25-Aug-2026"

ITEMS = [
    # description_en, description_km, qty, unit_price
    ("Office Chair", "កៅអីការិយាល័យ", 10, 45.00),
    ("Desk Lamp", "អំពូលភ្លើងតុ", 20, 12.50),
    ("Whiteboard", "ក្តារខៀនស", 5, 60.00),
]
SUBTOTAL = sum(q * p for _, _, q, p in ITEMS)
VAT = round(SUBTOTAL * 0.10, 2)
TOTAL = round(SUBTOTAL + VAT, 2)

# ---------------------------------------------------------------------------
# CSS shared by every document
# ---------------------------------------------------------------------------
CSS = """
@page { size: A4; margin: 15mm 18mm; }
* { box-sizing: border-box; }
body {
    font-family: "Noto Sans", "Noto Sans Khmer", sans-serif;
    font-size: 10.5pt;
    color: #1a1a1a;
}
.kingdom { color: #888; font-size: 8pt; letter-spacing: 0.5px; margin-bottom: 10px; }
.title-en { text-align: center; font-size: 18pt; font-weight: 700; margin: 0; }
.title-km { text-align: center; font-size: 13pt; margin: 2px 0 14px 0; }
.meta { width: 260px; margin: 0 0 16px auto; }
.meta td { padding: 1px 4px; font-size: 9.5pt; }
.meta td:first-child { font-weight: 700; text-align: right; width: 110px; }
.parties { display: flex; gap: 24px; margin-bottom: 14px; }
.party { flex: 1; }
.party h3 { font-size: 10pt; margin: 0 0 4px 0; }
.party .name-en { font-weight: 700; font-size: 11.5pt; margin: 0; }
.party .name-km { font-size: 10.5pt; margin: 1px 0 4px 0; }
.party .line { font-size: 9.5pt; margin: 1px 0; color: #333; }
table.items { width: 100%; border-collapse: collapse; margin-bottom: 10px; }
table.items th {
    background: #2c3e50; color: #fff; font-size: 9.5pt;
    padding: 7px 6px; text-align: center; border: 0.5px solid #888;
}
table.items td {
    border: 0.5px solid #999; padding: 6px; font-size: 9.5pt;
    text-align: center; vertical-align: middle;
}
table.items td.desc { text-align: left; }
table.totals { width: 100%; margin-bottom: 12px; }
table.totals td { padding: 3px 4px; font-size: 10pt; text-align: right; }
table.totals tr.grand td { font-weight: 700; border-top: 1px solid #000; font-size: 11pt; }
table.totals td:first-child { text-align: left; }
.note { font-size: 9.5pt; margin: 10px 0; }
.sign-row { display: flex; gap: 40px; margin-top: 40px; }
.sign-box { flex: 1; text-align: center; font-size: 9.5pt; }
.sign-line { border-top: 1px solid #444; margin-bottom: 4px; padding-top: 30px; }
"""


def party_html(party, label_en, label_km):
    return f"""
    <div class="party">
        <h3>{label_en} / {label_km}</h3>
        <p class="name-en">{party['name_en']}</p>
        <p class="name-km">{party['name_km']}</p>
        <p class="line">{party['address']}</p>
        <p class="line">TIN: {party['tin']} &nbsp;&nbsp; Tel: {party['tel']}</p>
    </div>"""


def meta_html(rows):
    trs = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return f'<table class="meta">{trs}</table>'


def items_table_html(mode="price"):
    """mode: 'price' (PO/Invoice), 'received' (GRNI)"""
    if mode == "received":
        head = "<tr><th>#</th><th>Description / បរិយាយ</th><th>Qty Ordered</th>" \
               "<th>Qty Received</th><th>Condition</th></tr>"
        rows = "".join(
            f"<tr><td>{i}</td><td class='desc'>{en} / {km}</td>"
            f"<td>{qty}</td><td>{qty}</td><td>Good</td></tr>"
            for i, (en, km, qty, _) in enumerate(ITEMS, 1)
        )
    else:
        head = "<tr><th>#</th><th>Description / បរិយាយ</th><th>Qty</th>" \
               "<th>Unit Price (USD)</th><th>Amount (USD)</th></tr>"
        rows = "".join(
            f"<tr><td>{i}</td><td class='desc'>{en} / {km}</td>"
            f"<td>{qty}</td><td>{price:,.2f}</td><td>{qty * price:,.2f}</td></tr>"
            for i, (en, km, qty, price) in enumerate(ITEMS, 1)
        )
    return f'<table class="items"><thead>{head}</thead><tbody>{rows}</tbody></table>'


def totals_html():
    return f"""
    <table class="totals">
        <tr><td></td><td style="width:120px">Subtotal / សរុបរង</td><td style="width:110px">USD {SUBTOTAL:,.2f}</td></tr>
        <tr><td></td><td>VAT 10% / ពន្ធអតិលើតម្លៃបន្ថែម</td><td>USD {VAT:,.2f}</td></tr>
        <tr class="grand"><td></td><td>TOTAL / សរុប</td><td>USD {TOTAL:,.2f}</td></tr>
    </table>"""


def sign_html(labels):
    boxes = "".join(f'<div class="sign-box"><div class="sign-line"></div>{lbl}</div>' for lbl in labels)
    return f'<div class="sign-row">{boxes}</div>'


def page(title_en, title_km, doc_no, doc_date, body_html):
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{CSS}</style></head>
<body>
    <div class="kingdom">KINGDOM OF CAMBODIA — NATION RELIGION KING</div>
    <p class="title-en">{title_en}</p>
    <p class="title-km">{title_km}</p>
    {meta_html([("No.:", doc_no), ("Date:", doc_date)])}
    {body_html}
</body></html>"""


def render(filename, html):
    pdf_path = os.path.join(OUT_DIR, filename + ".pdf")
    HTML(string=html).write_pdf(pdf_path)
    png_base = os.path.join(OUT_DIR, filename)
    subprocess.run(["pdftoppm", "-png", "-r", "200", "-singlefile", pdf_path, png_base], check=True)  # noqa: S603, S607 — fixed binary, local dev paths
    print(f"✅ {png_base}.png")


# ---------------------------------------------------------------------------
# 1. Purchase Order
# ---------------------------------------------------------------------------
po_body = f"""
<div class="parties">
    {party_html(BUYER, "Buyer", "អ្នកទិញ")}
    {party_html(VENDOR, "Vendor", "អ្នកលក់")}
</div>
{items_table_html("price")}
{totals_html()}
<p class="note">Please deliver goods to the above buyer address within 5 business days of this
Purchase Order. / សូមធ្វើការដឹកជញ្ជូនទំនិញក្នុងរយៈពេល ៥ថ្ងៃធ្វើការ។</p>
{sign_html(["Authorized by (Buyer)", "Acknowledged by (Vendor)"])}
"""
render("PO_2026_0451", page("PURCHASE ORDER", "លិខិតបញ្ជាទិញ", PO_NO, PO_DATE, po_body))

# ---------------------------------------------------------------------------
# 2. Goods Received Note / Inventory (GRNI)
# ---------------------------------------------------------------------------
grn_body = f"""
<div class="parties">
    {party_html(BUYER, "Received By (Warehouse)", "អ្នកទទួល")}
    {party_html(VENDOR, "Delivered By (Vendor)", "អ្នកដឹកជញ្ជូន")}
</div>
{meta_html([("Ref. PO No.:", PO_NO)])}
{items_table_html("received")}
<p class="note">All items received in good condition and matched against the referenced
Purchase Order quantities. / ទំនិញទាំងអស់បានទទួលក្នុងស្ថានភាពល្អ។</p>
{sign_html(["Received by (Warehouse)", "Inspected by (QA)"])}
"""
render("GRN_2026_0322", page("GOODS RECEIVED NOTE (GRNI)", "លិខិតបញ្ជាក់ទទួលទំនិញ",
                              GRN_NO, GRN_DATE, grn_body))

# ---------------------------------------------------------------------------
# 3. Vendor Invoice
# ---------------------------------------------------------------------------
inv_body = f"""
<div class="parties">
    {party_html(BUYER, "Bill To", "ថ្លែងវិក័យប័ត្រទៅ")}
    {party_html(VENDOR, "From (Vendor)", "ពីអ្នកលក់")}
</div>
{meta_html([("Ref. PO No.:", PO_NO)])}
{items_table_html("price")}
{totals_html()}
<p class="note">Amount in words: One Thousand One Hundred US Dollars Only ({TOTAL:,.2f}).
Payment due within 15 days.</p>
{sign_html(["Issued by (Vendor)", "Approved by (Buyer)"])}
"""
render("INV_2026_1123", page("VENDOR INVOICE", "វិក្កយបត្រ", INV_NO, INV_DATE, inv_body))

# ---------------------------------------------------------------------------
# 4. Payment Advice & Receipt Doc (PARD)
# ---------------------------------------------------------------------------
pard_body = f"""
<div class="parties">
    {party_html(BUYER, "Paid By", "អ្នកបង់ប្រាក់")}
    {party_html(VENDOR, "Paid To", "អ្នកទទួលប្រាក់")}
</div>
{meta_html([
    ("Ref. Invoice No.:", INV_NO),
    ("Payment Method:", "Bank Transfer"),
    ("Bank:", "ABA Bank Cambodia"),
    ("Account No.:", "000-XXXXXX-01 (Mekong Supplies Co., Ltd.)"),
])}
<table class="items">
    <thead><tr><th>Description</th><th>Amount (USD)</th></tr></thead>
    <tbody>
        <tr><td class="desc">Payment for Invoice {INV_NO}</td><td>{TOTAL:,.2f}</td></tr>
        <tr><td class="desc"><b>TOTAL PAID / សរុបបានបង់</b></td><td><b>USD {TOTAL:,.2f}</b></td></tr>
    </tbody>
</table>
<p class="note">This document confirms receipt of payment in full settlement of the referenced
invoice. / លិខិតនេះបញ្ជាក់ការទទួលបានប្រាក់ពេញលេញ។</p>
{sign_html(["Paid by (Buyer/Finance)", "Received by (Vendor)"])}
"""
render("PARD_2026_0210", page("PAYMENT ADVICE & RECEIPT DOC (PARD)",
                               "លិខិតបញ្ជាក់ការទូទាត់ប្រាក់", PARD_NO, PARD_DATE, pard_body))

print("\nAll test documents generated in:", OUT_DIR)
