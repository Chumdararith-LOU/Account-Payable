import re

from database import get_connection, get_invoice_by_id, insert_match_result

PRICE_TOLERANCE = 0.01  # 1%

def normalize_text(text):
    """Robustly clean up OCR noise from item descriptions"""
    if not text:
        return ""
    # 1. Remove slash followed by any letters (case-insensitive) e.g., /nmw, /Hni, /as
    text = re.sub(r'/[a-zA-Z]+', '', text)
    # 2. Remove any other non-alphanumeric characters (punctuation, etc.)
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    # 3. Collapse multiple spaces, strip, and lowercase
    text = re.sub(r'\s+', ' ', text).strip().lower()
    return text

def run_matching_engine(inv_id: str):
    conn = get_connection()
    cursor = conn.cursor()

    invoice = get_invoice_by_id(inv_id)
    if not invoice:
        print(f"Invoice {inv_id} not found in database.")
        conn.close()
        return

    inv_vendor = invoice['Vendor'].strip().lower()

    cursor.execute("SELECT * FROM PO_HEADER WHERE LOWER(TRIM(Vendor)) LIKE ? ORDER BY Date DESC LIMIT 1", (f"%{inv_vendor}%",))
    row = cursor.fetchone()
    po = dict(row) if row else None

    cursor.execute("SELECT * FROM GRNI_HEADER WHERE LOWER(TRIM(Vendor)) LIKE ? ORDER BY Date DESC LIMIT 1", (f"%{inv_vendor}%",))
    row = cursor.fetchone()
    grni = dict(row) if row else None

    cursor.execute("SELECT * FROM PARD WHERE INV_ID = ?", (inv_id,))
    row = cursor.fetchone()
    pard = dict(row) if row else None

    print(f"DEBUG: Looking for vendor '{inv_vendor}' -> Found PO: {bool(po)}, GRNI: {bool(grni)}, PARD: {bool(pard)}")

    missing_docs = []
    if not po: missing_docs.append("PO")
    if not grni: missing_docs.append("GRNI")
    if not pard: missing_docs.append("PARD")

    if missing_docs:
        status = "PENDING INFO"
        score = 0.5
        remark = f"Missing documents: {', '.join(missing_docs)}"
        insert_match_result({
            'inv_id': inv_id, 'status': status, 'score': score, 'remark': remark,
            'po_id': po['PO_ID'] if po else None,
            'grni_id': grni['GRNI_ID'] if grni else None,
            'pard_id': pard['PARD_ID'] if pard else None
        })
        print(f"[{inv_id}] -> {status}: {remark}")
        conn.close()
        return

    discrepancies = []
    score = 1.0

    cursor.execute("SELECT * FROM PO_LINE WHERE PO_ID = ?", (po['PO_ID'],))
    po_lines = {normalize_text(row['Item']): row for row in cursor.fetchall()}

    cursor.execute("SELECT * FROM GRNI_LINE WHERE GRNI_ID = ?", (grni['GRNI_ID'],))
    grni_lines = {normalize_text(row['Item']): row for row in cursor.fetchall()}

    cursor.execute("SELECT * FROM INVOICE_LINE WHERE INV_ID = ?", (inv_id,))
    inv_lines = {normalize_text(row['Item']): row for row in cursor.fetchall()}

    # Debug print to see what the normalized keys look like
    print(f"DEBUG: Invoice Items -> {list(inv_lines.keys())}")
    print(f"DEBUG: PO Items      -> {list(po_lines.keys())}")
    print(f"DEBUG: GRNI Items    -> {list(grni_lines.keys())}")

    for item_key, inv_line in inv_lines.items():
        po_line = po_lines.get(item_key)
        grni_line = grni_lines.get(item_key)

        if not po_line or not grni_line:
            discrepancies.append(f"Item '{item_key}' missing in PO/GRNI")
            score -= 0.2
            continue

        # Rule: Qty Received (GRNI) >= Qty Invoiced
        if grni_line['Qty'] < inv_line['Qty']:
            discrepancies.append(f"Qty Variance on '{item_key}': GRNI({grni_line['Qty']}) < INV({inv_line['Qty']})")
            score -= 0.3

        # Rule: Unit price within tolerance % of PO price
        price_diff = abs(po_line['Price'] - inv_line['Price'])
        if po_line['Price'] > 0 and (price_diff / po_line['Price']) > PRICE_TOLERANCE:
            discrepancies.append(f"Price Variance on '{item_key}': PO({po_line['Price']}) vs INV({inv_line['Price']})")
            score -= 0.3

    if pard and abs(pard['Amount'] - invoice['Total']) > 0.01:
        discrepancies.append(f"Payment mismatch: PARD({pard['Amount']}) != INV Total({invoice['Total']})")
        score -= 0.2

    if not discrepancies:
        status = "MATCH"
        remark = "All documents reconcile within tolerance."
    else:
        status = "DISCREPANCY"
        remark = "; ".join(discrepancies)
        score = max(0.0, score)

    insert_match_result({
        'inv_id': inv_id,
        'po_id': po['PO_ID'] if po else None,
        'grni_id': grni['GRNI_ID'] if grni else None,
        'pard_id': pard['PARD_ID'] if pard else None,
        'status': status,
        'score': round(score, 3),
        'remark': remark
    })

    print(f"[{inv_id}] -> {status} (Score: {score}) | {remark}")
    conn.close()

if __name__ == "__main__":
    run_matching_engine("INV-2026-1123")
