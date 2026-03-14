"""Debug script: check PO raw text and expense cross-report matches."""
import duckdb, json

db = duckdb.connect('data/indexes/needle_finder.duckdb', read_only=True)

# Check PO raw text to understand line item extraction failure
print("=== PO RAW TEXT SAMPLE (first 800 chars) ===")
row = db.execute("SELECT po_number, raw_text FROM purchase_orders WHERE po_number != '' AND raw_text IS NOT NULL AND raw_text != '' LIMIT 1").fetchone()
if row:
    print(f"PO: {row[0]}")
    print(row[1][:800])
else:
    print("No PO with raw_text found!")

# Check if PO raw text has LINE ITEMS section header
print("\n=== PO TEXT LINE ITEMS CHECK ===")
ct = db.execute("SELECT COUNT(*) FROM purchase_orders WHERE raw_text LIKE '%LINE ITEMS%'").fetchone()[0]
print(f"  POs with 'LINE ITEMS' in text: {ct}")
ct2 = db.execute("SELECT COUNT(*) FROM purchase_orders WHERE raw_text LIKE '%line items%'").fetchone()[0]
print(f"  POs with 'line items' (case-ins) in text: {ct2}")
ct3 = db.execute("SELECT COUNT(*) FROM purchase_orders WHERE raw_text LIKE '%Description%'").fetchone()[0]
print(f"  POs with 'Description' in text: {ct3}")
ct4 = db.execute("SELECT COUNT(*) FROM purchase_orders WHERE raw_text LIKE '%Amount%'").fetchone()[0]
print(f"  POs with 'Amount' in text: {ct4}")

# Check invoice raw text for tax rate info
print("\n=== INVOICE TAX RATE IN RAW TEXT ===")
row = db.execute("SELECT invoice_number, raw_text FROM invoices WHERE raw_text IS NOT NULL AND raw_text != '' AND raw_text LIKE '%GST%' LIMIT 1").fetchone()
if row:
    print(f"Invoice: {row[0]}")
    # Find the GST section
    text = row[1]
    import re
    matches = re.findall(r'(?:GST|IGST|CGST|SGST|Tax).*?\n?.*?(\d+(?:\.\d+)?)\s*%', text, re.I)
    print(f"  Tax rate patterns found: {matches}")
    # Also find the subtotal/tax line area
    idx = text.lower().find('sub')
    if idx > 0:
        print(f"  Text around subtotal: {text[idx:idx+300]}")

# Check invoice-level tax_rate vs tax_amount / subtotal
print("\n=== COMPUTED TAX RATES ===")
rows = db.execute("""
    SELECT invoice_number, subtotal, tax_amount, tax_rate, grand_total 
    FROM invoices 
    WHERE subtotal > 0 AND tax_amount > 0 
    LIMIT 10
""").fetchall()
for r in rows:
    computed = round(r[2] / r[1] * 100, 2) if r[1] and r[1] > 0 else None
    print(f"  {r[0]}: subtotal={r[1]} tax={r[2]} stored_rate={r[3]} computed_rate={computed}%")

# Check for cross-report expense duplicates
print("\n=== EXPENSE CROSS-REPORT DUPLICATE CHECK ===")
rows = db.execute("SELECT report_id, employee_id, expense_lines_json FROM expense_reports").fetchall()
from collections import defaultdict
groups = defaultdict(list)
for r in rows:
    emp_id = str(r[1]).strip().upper()
    lines = json.loads(r[2]) if r[2] else []
    for line in lines:
        merchant = str(line.get("merchant", "")).strip().upper()
        amount = str(line.get("amount", ""))
        date = str(line.get("date", "")).strip()
        key = f"{emp_id}|{merchant}|{amount}|{date}"
        groups[key].append(r[0])

dupes = {k: v for k, v in groups.items() if len(v) >= 2 and len(set(v)) >= 2}
print(f"  Cross-report duplicate groups found: {len(dupes)}")
for k, v in list(dupes.items())[:5]:
    print(f"    {k} -> reports: {v}")

# Check for triple hotel claims
print("\n=== TRIPLE HOTEL CLAIM CHECK ===")
hotel_groups = defaultdict(list)
for r in rows:
    emp_id = str(r[1]).strip().upper()
    lines = json.loads(r[2]) if r[2] else []
    for line in lines:
        desc = str(line.get("description", "")).lower()
        if any(kw in desc for kw in ["hotel", "accommodation", "lodging", "stay"]):
            merchant = str(line.get("merchant", "")).strip().upper()
            date = str(line.get("date", "")).strip()
            amount = str(line.get("amount", ""))
            key = f"{emp_id}|{merchant}|{date}|{amount}"
            hotel_groups[key].append(r[0])

hotel_dupes = {k: v for k, v in hotel_groups.items() if len(v) >= 3 and len(set(v)) >= 3}
print(f"  Triple hotel claim groups: {len(hotel_dupes)}")
for k, v in list(hotel_dupes.items())[:5]:
    print(f"    {k} -> reports: {v}")

# Also check with just emp_id|description|amount (ignoring date)
print("\n=== EXPENSE DUPLICATES BY DESCRIPTION+AMOUNT (relaxed) ===")
groups2 = defaultdict(list)
for r in rows:
    emp_id = str(r[1]).strip().upper()
    lines = json.loads(r[2]) if r[2] else []
    for line in lines:
        desc = str(line.get("description", "")).strip().upper()
        amount = str(line.get("amount", ""))
        key = f"{emp_id}|{desc}|{amount}"
        groups2[key].append(r[0])
dupes2 = {k: v for k, v in groups2.items() if len(v) >= 2 and len(set(v)) >= 2}
print(f"  Cross-report matches by desc+amount: {len(dupes2)}")
for k, v in list(dupes2.items())[:5]:
    print(f"    {k} -> {sorted(set(v))}")

db.close()
