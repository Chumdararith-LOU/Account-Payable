import glob
import json
import os
import re
import sqlite3
from typing import Any

from bs4 import BeautifulSoup

DATABASE_PATH = "ap_automation.db"

# ================= SPATIAL OCR HELPER =================

def get_text_below_label(text_blocks, label_keyword, x_tolerance=150, y_min_gap=5):
    """Finds text spatially located below a specific label using Bounding Boxes"""
    for i, block in enumerate(text_blocks):
        if label_keyword in block['text'].lower():
            label_bbox = block['bbox']
            label_x_min = label_bbox[0]
            label_y_max = label_bbox[3]

            best_match = None
            min_distance = float('inf')

            for j, candidate in enumerate(text_blocks):
                if i == j:
                    continue
                cand_bbox = candidate['bbox']
                cand_x_min = cand_bbox[0]
                cand_y_min = cand_bbox[1]

                if cand_y_min > label_y_max + y_min_gap and abs(cand_x_min - label_x_min) < x_tolerance:
                    distance = cand_y_min - label_y_max
                    if distance < min_distance and len(candidate['text'].strip()) > 3:
                        min_distance = distance
                        best_match = candidate['text'].strip()
            if best_match:
                return best_match
    return None

# ================= DATABASE SETUP =================

def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS PO_HEADER (PO_ID TEXT PRIMARY KEY, Vendor TEXT NOT NULL, Date TEXT NOT NULL, Total REAL NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS PO_LINE (PO_LINE_ID INTEGER PRIMARY KEY AUTOINCREMENT, PO_ID TEXT NOT NULL, Item TEXT NOT NULL, Qty REAL NOT NULL, Price REAL NOT NULL, FOREIGN KEY (PO_ID) REFERENCES PO_HEADER(PO_ID))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS GRNI_HEADER (GRNI_ID TEXT PRIMARY KEY, Vendor TEXT NOT NULL, Date TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS GRNI_LINE (GRNI_LINE_ID INTEGER PRIMARY KEY AUTOINCREMENT, GRNI_ID TEXT NOT NULL, Item TEXT NOT NULL, Qty REAL NOT NULL, FOREIGN KEY (GRNI_ID) REFERENCES GRNI_HEADER(GRNI_ID))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS INVOICE_HEADER (INV_ID TEXT PRIMARY KEY, Vendor TEXT NOT NULL, Date TEXT NOT NULL, Total REAL NOT NULL, Tax REAL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS INVOICE_LINE (INV_LINE_ID INTEGER PRIMARY KEY AUTOINCREMENT, INV_ID TEXT NOT NULL, Item TEXT NOT NULL, Qty REAL NOT NULL, Price REAL NOT NULL, FOREIGN KEY (INV_ID) REFERENCES INVOICE_HEADER(INV_ID))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS PARD (PARD_ID TEXT PRIMARY KEY, INV_ID TEXT NOT NULL, Amount REAL NOT NULL, Date TEXT NOT NULL, Ref TEXT, FOREIGN KEY (INV_ID) REFERENCES INVOICE_HEADER(INV_ID))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS MATCH_RESULT (MATCH_ID INTEGER PRIMARY KEY AUTOINCREMENT, INV_ID TEXT NOT NULL, PO_ID TEXT, GRNI_ID TEXT, PARD_ID TEXT, Status TEXT NOT NULL CHECK(Status IN ('MATCH', 'DISCREPANCY', 'PENDING INFO')), Score REAL NOT NULL, Remark TEXT, Processed_Date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (INV_ID) REFERENCES INVOICE_HEADER(INV_ID))''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoice_vendor ON INVOICE_HEADER(Vendor)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_match_status ON MATCH_RESULT(Status)')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_invoice ON INVOICE_HEADER(INV_ID, Vendor)')

    conn.commit()
    conn.close()
    print("✓ Database initialized successfully")

# ================= INSERT FUNCTIONS =================

def insert_po(po_data: dict[str, Any]) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT OR REPLACE INTO PO_HEADER (PO_ID, Vendor, Date, Total) VALUES (?, ?, ?, ?)', (po_data['po_id'], po_data['vendor'], po_data['date'], po_data['total']))
        if 'lines' in po_data:
            cursor.execute('DELETE FROM PO_LINE WHERE PO_ID = ?', (po_data['po_id'],))
            for line in po_data['lines']:
                cursor.execute('INSERT INTO PO_LINE (PO_ID, Item, Qty, Price) VALUES (?, ?, ?, ?)', (po_data['po_id'], line['item'], line['qty'], line['price']))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error inserting PO: {e}")
        return False
    finally:
        conn.close()

def insert_grni(grni_data: dict[str, Any]) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT OR REPLACE INTO GRNI_HEADER (GRNI_ID, Vendor, Date) VALUES (?, ?, ?)', (grni_data['grni_id'], grni_data['vendor'], grni_data['date']))
        if 'lines' in grni_data:
            cursor.execute('DELETE FROM GRNI_LINE WHERE GRNI_ID = ?', (grni_data['grni_id'],))
            for line in grni_data['lines']:
                cursor.execute('INSERT INTO GRNI_LINE (GRNI_ID, Item, Qty) VALUES (?, ?, ?)', (grni_data['grni_id'], line['item'], line['qty']))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error inserting GRNI: {e}")
        return False
    finally:
        conn.close()

def insert_invoice(inv_data: dict[str, Any]) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT OR REPLACE INTO INVOICE_HEADER (INV_ID, Vendor, Date, Total, Tax) VALUES (?, ?, ?, ?, ?)', (inv_data['inv_id'], inv_data['vendor'], inv_data['date'], inv_data['total'], inv_data.get('tax', 0)))
        if 'lines' in inv_data:
            cursor.execute('DELETE FROM INVOICE_LINE WHERE INV_ID = ?', (inv_data['inv_id'],))
            for line in inv_data['lines']:
                cursor.execute('INSERT INTO INVOICE_LINE (INV_ID, Item, Qty, Price) VALUES (?, ?, ?, ?)', (inv_data['inv_id'], line['item'], line['qty'], line['price']))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error inserting invoice: {e}")
        return False
    finally:
        conn.close()

def insert_pard(pard_data: dict[str, Any]) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT OR REPLACE INTO PARD (PARD_ID, INV_ID, Amount, Date, Ref) VALUES (?, ?, ?, ?, ?)', (pard_data['pard_id'], pard_data['inv_id'], pard_data['amount'], pard_data['date'], pard_data.get('ref')))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error inserting PARD: {e}")
        return False
    finally:
        conn.close()

def insert_match_result(match_data: dict[str, Any]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''INSERT INTO MATCH_RESULT (INV_ID, PO_ID, GRNI_ID, PARD_ID, Status, Score, Remark) VALUES (?, ?, ?, ?, ?, ?, ?)''', (match_data['inv_id'], match_data.get('po_id'), match_data.get('grni_id'), match_data.get('pard_id'), match_data['status'], match_data['score'], match_data.get('remark')))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"Error inserting match result: {e}")
        return -1
    finally:
        conn.close()

# ================= EXTRACTION FUNCTIONS =================

def extract_po_from_json(data: dict) -> dict | None:
    try:
        text_blocks = data.get('text_blocks', [])
        po_id, date, total = None, None, 0.0

        for block in text_blocks:
            match = re.search(r'No\.:\s*([A-Z0-9-]+)', block['text'], re.IGNORECASE)
            if match:
                po_id = match.group(1)
                break
        if not po_id:
            return None

        for block in text_blocks:
            match = re.search(r'Date[:\s]+(\d{1,2}[-/]\w{3}[-/]\d{4}|\d{1,2}[-/]\d{1,2}[-/]\d{4})', block['text'], re.IGNORECASE)
            if match:
                date = match.group(1)
                break

        vendor = get_text_below_label(text_blocks, 'vendor')
        if not vendor:
            company_names = [b['text'].strip() for b in text_blocks if re.search(r'(Co\.\s*Ltd\.|Ltd\.|Inc\.)', b['text'])]
            vendor = company_names[1] if len(company_names) >= 2 else (company_names[0] if company_names else "Unknown Vendor")

        for block in text_blocks:
            if 'total' in block['text'].lower():
                match = re.search(r'USD\s*([\d,]+\.?\d*)', block['text'], re.IGNORECASE)
                if match:
                    total = float(match.group(1).replace(',', ''))
                    break

        lines = []
        for table in data.get('tables', []):
            soup = BeautifulSoup(table.get('html', ''), 'html.parser')
            for row in soup.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 4:
                    try:
                        cell_texts = [c.get_text().strip() for c in cells]
                        if 'description' in cell_texts[1].lower() or 'subtotal' in cell_texts[0].lower():
                            continue
                        item_desc = cells[1].get_text().strip()
                        qty_text = cells[2].get_text().strip()
                        price_text = cells[3].get_text().strip()
                        qty = float(re.sub(r'[^\d.]', '', qty_text) or 0)
                        price = float(re.sub(r'[^\d.]', '', price_text) or 0)
                        if qty > 0 and price > 0 and item_desc:
                            lines.append({'item': item_desc, 'qty': qty, 'price': price})
                    except (ValueError, IndexError):
                        continue

        return {'po_id': po_id, 'vendor': vendor, 'date': date or "", 'total': total, 'lines': lines}
    except Exception as e:
        print(f"Error extracting PO: {e}")
        return None

def extract_grni_from_json(data: dict) -> dict | None:
    try:
        text_blocks = data.get('text_blocks', [])
        grni_id, date = None, None

        for block in text_blocks:
            match = re.search(r'(GRN|GRNI|Delivery)[-\s]?No\.?\s*[:\s]*([A-Z0-9-]+)', block['text'], re.IGNORECASE)
            if match:
                grni_id = match.group(2)
                break
        if not grni_id:
            for block in text_blocks:
                match = re.search(r'No\.:\s*([A-Z0-9-]+)', block['text'], re.IGNORECASE)
                if match:
                    grni_id = match.group(1)
                    break
        if not grni_id:
            return None

        for block in text_blocks:
            match = re.search(r'Date[:\s]+(\d{1,2}[-/]\w{3}[-/]\d{4}|\d{1,2}[-/]\d{1,2}[-/]\d{4})', block['text'], re.IGNORECASE)
            if match:
                date = match.group(1)
                break

        vendor = get_text_below_label(text_blocks, 'vendor')
        if not vendor:
            vendor = "Unknown Vendor"

        lines = []
        for table in data.get('tables', []):
            soup = BeautifulSoup(table.get('html', ''), 'html.parser')
            for row in soup.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 3:
                    try:
                        cell_texts = [c.get_text().strip() for c in cells]
                        if len(cell_texts) > 1 and 'description' in cell_texts[1].lower():
                            continue
                        item_desc = cells[1].get_text().strip()
                        qty_text = cells[2].get_text().strip()
                        qty = float(re.sub(r'[^\d.]', '', qty_text) or 0)
                        if qty > 0 and item_desc:
                            lines.append({'item': item_desc, 'qty': qty})
                    except (ValueError, IndexError):
                        continue

        return {'grni_id': grni_id, 'vendor': vendor, 'date': date or "", 'lines': lines}
    except Exception as e:
        print(f"Error extracting GRNI: {e}")
        return None

def extract_invoice_from_json(data: dict) -> dict | None:
    try:
        text_blocks = data.get('text_blocks', [])
        inv_id, date, total, tax = None, None, 0.0, 0.0

        for block in text_blocks:
            match = re.search(r'(Invoice|Inv|Bill)[-\s]?No\.?\s*[:\s]*([A-Z0-9-]+)', block['text'], re.IGNORECASE)
            if match:
                inv_id = match.group(2)
                break
        if not inv_id:
            for block in text_blocks:
                match = re.search(r'No\.:\s*([A-Z0-9-]+)', block['text'], re.IGNORECASE)
                if match:
                    inv_id = match.group(1)
                    break
        if not inv_id:
            return None

        for block in text_blocks:
            match = re.search(r'Date[:\s]+(\d{1,2}[-/]\w{3}[-/]\d{4}|\d{1,2}[-/]\d{1,2}[-/]\d{4})', block['text'], re.IGNORECASE)
            if match:
                date = match.group(1)
                break

        vendor = get_text_below_label(text_blocks, 'vendor')
        if not vendor:
            company_names = [b['text'].strip() for b in text_blocks if re.search(r'(Co\.\s*Ltd\.|Ltd\.|Inc\.)', b['text'])]
            vendor = company_names[1] if len(company_names) >= 2 else (company_names[0] if company_names else "Unknown Vendor")

        for block in text_blocks:
            if 'total' in block['text'].lower() and 'subtotal' not in block['text'].lower():
                match = re.search(r'USD\s*([\d,]+\.?\d*)', block['text'], re.IGNORECASE)
                if match:
                    total = float(match.group(1).replace(',', ''))
            if 'vat' in block['text'].lower() or 'tax' in block['text'].lower():
                match = re.search(r'USD\s*([\d,]+\.?\d*)', block['text'], re.IGNORECASE)
                if match:
                    tax = float(match.group(1).replace(',', ''))

        lines = []
        for table in data.get('tables', []):
            soup = BeautifulSoup(table.get('html', ''), 'html.parser')
            for row in soup.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 4:
                    try:
                        cell_texts = [c.get_text().strip() for c in cells]
                        if len(cell_texts) > 1 and 'description' in cell_texts[1].lower():
                            continue
                        if 'subtotal' in cell_texts[0].lower() or 'total' in cell_texts[0].lower():
                            continue
                        item_desc = cells[1].get_text().strip()
                        qty_text = cells[2].get_text().strip()
                        price_text = cells[3].get_text().strip()
                        qty = float(re.sub(r'[^\d.]', '', qty_text) or 0)
                        price = float(re.sub(r'[^\d.]', '', price_text) or 0)
                        if qty > 0 and price > 0 and item_desc:
                            lines.append({'item': item_desc, 'qty': qty, 'price': price})
                    except (ValueError, IndexError):
                        continue

        return {'inv_id': inv_id, 'vendor': vendor, 'date': date or "", 'total': total, 'tax': tax, 'lines': lines}
    except Exception as e:
        print(f"Error extracting invoice: {e}")
        return None

def extract_pard_from_json(data: dict) -> dict | None:
    try:
        text_blocks = data.get('text_blocks', [])
        pard_id, date, inv_id, amount = None, None, None, 0.0

        for block in text_blocks:
            match = re.search(r'(PARD|Payment|Receipt)[-\s]?No\.?\s*[:\s]*([A-Z0-9-]+)', block['text'], re.IGNORECASE)
            if match:
                pard_id = match.group(2)
                break
        if not pard_id:
            for block in text_blocks:
                match = re.search(r'No\.:\s*([A-Z0-9-]+)', block['text'], re.IGNORECASE)
                if match:
                    pard_id = match.group(1)
                    break
        if not pard_id:
            return None

        for block in text_blocks:
            match = re.search(r'Date[:\s]+(\d{1,2}[-/]\w{3}[-/]\d{4}|\d{1,2}[-/]\d{1,2}[-/]\d{4})', block['text'], re.IGNORECASE)
            if match:
                date = match.group(1)
                break

        for block in text_blocks:
            if 'amount' in block['text'].lower() or 'total' in block['text'].lower():
                match = re.search(r'USD\s*([\d,]+\.?\d*)', block['text'], re.IGNORECASE)
                if match:
                    amount = float(match.group(1).replace(',', ''))
                    break

        for block in text_blocks:
            match = re.search(r'(Invoice|Inv)[-\s]?No\.?\s*[:\s]*([A-Z0-9-]+)', block['text'], re.IGNORECASE)
            if match:
                inv_id = match.group(2)
                break

        return {'pard_id': pard_id, 'inv_id': inv_id or pard_id, 'amount': amount, 'date': date or "", 'ref': None}
    except Exception as e:
        print(f"Error extracting PARD: {e}")
        return None

# ================= MIGRATION LOGIC =================

def migrate_json_to_db(json_folder: str = "output/ocr"):
    print("Starting migration from JSON to database...")
    json_files = glob.glob(f"{json_folder}/*.json")
    migrated = 0

    for json_file in json_files:
        try:
            with open(json_file, encoding='utf-8') as f:
                data = json.load(f)
            filename = os.path.basename(json_file).lower()

            if 'po' in filename:
                po_data = extract_po_from_json(data)
                if po_data and insert_po(po_data):
                    migrated += 1
                    print(f"  ✓ Migrated PO: {po_data['po_id']}")
            elif 'grn' in filename or 'grni' in filename:
                grni_data = extract_grni_from_json(data)
                if grni_data and insert_grni(grni_data):
                    migrated += 1
                    print(f"  ✓ Migrated GRNI: {grni_data['grni_id']}")
            elif 'inv' in filename or 'invoice' in filename:
                inv_data = extract_invoice_from_json(data)
                if inv_data and insert_invoice(inv_data):
                    migrated += 1
                    print(f"  ✓ Migrated Invoice: {inv_data['inv_id']}")
            elif 'pard' in filename:
                pard_data = extract_pard_from_json(data)
                if pard_data and insert_pard(pard_data):
                    migrated += 1
                    print(f"  ✓ Migrated PARD: {pard_data['pard_id']}")
        except Exception as e:
            print(f"  ✗ Error migrating {json_file}: {e}")

    print(f"\nMigration complete: {migrated} documents migrated")

# ================= QUERY FUNCTIONS =================

def get_invoice_by_id(inv_id: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM INVOICE_HEADER WHERE INV_ID = ?', (inv_id,))
        row = cursor.fetchone()
        if not row:
            return None
        invoice = dict(row)
        cursor.execute('SELECT * FROM INVOICE_LINE WHERE INV_ID = ?', (inv_id,))
        invoice['lines'] = [dict(line) for line in cursor.fetchall()]
        return invoice
    finally:
        conn.close()

def get_dashboard_stats() -> dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT COUNT(*) FROM INVOICE_HEADER')
        total = cursor.fetchone()[0]
        cursor.execute("SELECT Status, COUNT(*) FROM MATCH_RESULT GROUP BY Status")
        status_counts = {row['Status']: row[1] for row in cursor.fetchall()}
        cursor.execute("SELECT Remark, COUNT(*) as cnt FROM MATCH_RESULT WHERE Status = 'DISCREPANCY' GROUP BY Remark ORDER BY cnt DESC LIMIT 5")
        top_reasons = [{'reason': row['Remark'], 'count': row['cnt']} for row in cursor.fetchall()]
        return {'total_invoices': total, 'matched': status_counts.get('MATCH', 0), 'discrepancy': status_counts.get('DISCREPANCY', 0), 'pending': status_counts.get('PENDING INFO', 0), 'top_reasons': top_reasons}
    finally:
        conn.close()

def get_pending_invoices() -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''SELECT mr.*, ih.Vendor, ih.Date as Invoice_Date, ih.Total FROM MATCH_RESULT mr JOIN INVOICE_HEADER ih ON mr.INV_ID = ih.INV_ID WHERE mr.Status = 'DISCREPANCY' OR mr.Status = 'PENDING INFO' ORDER BY mr.Processed_Date DESC''')
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def check_duplicate_invoice(inv_id: str, vendor: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT COUNT(*) FROM INVOICE_HEADER WHERE INV_ID = ? AND Vendor = ?', (inv_id, vendor))
        return cursor.fetchone()[0] > 0
    finally:
        conn.close()

if __name__ == "__main__":
    init_database()
