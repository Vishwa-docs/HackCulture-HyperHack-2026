"""Debug script: deeper investigation."""
import duckdb, json, re

db = duckdb.connect('data/indexes/needle_finder.duckdb', read_only=True)

# Check a few more invoice raw texts for GST patterns
print("=== INVOICE RAW TEXTS - GST PATTERNS ===")
rows = db.execute("SELECT invoice_number, raw_text FROM invoices WHERE raw_text IS NOT NULL AND raw_text != '' LIMIT 5").fetchall()
for r in rows:
    text = r[1]
    inv = r[0]
    # Find all GST-related lines
    gst_lines = []
    for line in text.split('\n'):
        if re.search(r'GST|CGST|SGST|IGST|tax', line, re.I):
            gst_lines.append(line.strip())
    print(f"\n  {inv} GST lines: {gst_lines[:8]}")
    
    # Extract the tax section
    idx = text.lower().find('subtotal')
    if idx >= 0:
        section = text[idx:idx+200]
        print(f"  Tax section: {repr(section[:200])}")

# Check a broader sample - how many have GST percentage in text
print("\n\n=== INVOICES WITH GST PERCENTAGE IN TEXT ===")
rows = db.execute("SELECT invoice_number, raw_text FROM invoices WHERE raw_text LIKE '%GST%(%' OR raw_text LIKE '%gst%(%'").fetchall()
print(f"  Invoices with 'GST(': {len(rows)}")
for r in rows[:3]:
    m = re.search(r'(?:I?GST|CGST|SGST)\s*\(\s*(\d+(?:\.\d+)?)\s*%\s*\)', r[1], re.I)
    if m:
        print(f"  {r[0]}: found rate {m.group(1)}%")

# Check the REAL invoice subtotal + tax math
print("\n\n=== INVOICE AMOUNTS (raw text extraction) ===")
rows = db.execute("SELECT invoice_number, raw_text FROM invoices WHERE raw_text IS NOT NULL AND raw_text != '' LIMIT 3").fetchall()
for r in rows:
    text = r[1]
    # Find ALL amounts after Subtotal
    idx = text.lower().find('subtotal')
    if idx >= 0:
        amounts_section = text[idx:]
        amounts = re.findall(r'I([\d,]+\.?\d*)', amounts_section[:500])
        labels_and_amounts = re.findall(r'([A-Za-z/ ]+):\s*\n?\s*I?([\d,]+\.?\d*)', amounts_section[:500])
        print(f"\n  {r[0]}:")
        for label, amt in labels_and_amounts:
            print(f"    {label.strip()}: {amt}")

# Check PO section headers
print("\n\n=== PO SECTION HEADERS ===")
rows = db.execute("SELECT po_number, raw_text FROM purchase_orders WHERE raw_text IS NOT NULL AND raw_text != '' LIMIT 5").fetchall()
for r in rows:
    text = r[1]
    # Find section headers
    headers = re.findall(r'^([A-Z][A-Z\s]+)$', text, re.M)
    print(f"  {r[0]}: {headers}")

# Try extracting PO line items with ORDER ITEMS header
print("\n\n=== PO LINE ITEMS WITH ORDER ITEMS HEADER ===")
row = db.execute("SELECT po_number, raw_text FROM purchase_orders WHERE raw_text LIKE '%ORDER ITEMS%' LIMIT 1").fetchone()
if row:
    text = row[1]
    m = re.search(r'ORDER\s+ITEMS\s*\n', text, re.I)
    if m:
        section = text[m.end():]
        # Skip header
        hdr = re.search(r'Amount\s*\n', section, re.I)
        if hdr:
            items_text = section[hdr.end():]
            print(f"  Items text (first 500 chars):")
            print(items_text[:500])

# Check expense data for same emp across reports with hotel
print("\n\n=== EXPENSE HOTEL STAYS (top-level fields) ===")
rows = db.execute("""
    SELECT report_id, employee_id, employee_name, hotel_name, stay_start, stay_end, total_amount 
    FROM expense_reports 
    WHERE hotel_name IS NOT NULL AND hotel_name != '' 
    LIMIT 10
""").fetchall()
for r in rows:
    print(f"  {r[0]} emp={r[1]} hotel={r[3]} stay={r[4]}-{r[5]}")

# Check if same employees appear in multiple reports
print("\n\n=== EMPLOYEES IN MULTIPLE REPORTS ===")
rows = db.execute("""
    SELECT employee_id, COUNT(*) as cnt, 
           GROUP_CONCAT(report_id) as reports
    FROM expense_reports 
    GROUP BY employee_id 
    HAVING cnt >= 2
    ORDER BY cnt DESC 
    LIMIT 10
""").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} reports: {r[2]}")

# Check if same employee + hotel across reports
print("\n\n=== SAME EMPLOYEE+HOTEL ACROSS REPORTS ===")
rows = db.execute("""
    SELECT employee_id, hotel_name, COUNT(*) as cnt,
           GROUP_CONCAT(report_id) as reports
    FROM expense_reports 
    WHERE hotel_name IS NOT NULL AND hotel_name != ''
    GROUP BY employee_id, hotel_name
    HAVING cnt >= 2
    ORDER BY cnt DESC
    LIMIT 10
""").fetchall()
for r in rows:
    print(f"  {r[0]} at {r[1]}: {r[2]} reports: {r[3]}")

db.close()
