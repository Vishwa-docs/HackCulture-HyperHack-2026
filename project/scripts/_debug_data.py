"""Debug script to inspect what data is in DuckDB."""
import duckdb, json

db = duckdb.connect('data/indexes/needle_finder.duckdb', read_only=True)

# --- INVOICES ---
print("=== INVOICE COLUMNS ===")
for c in db.execute("DESCRIBE invoices").fetchall():
    print(f"  {c[0]}: {c[1]}")

print("\n=== INVOICE COUNT ===")
print(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0])

print("\n=== INVOICE line_items_json SAMPLE ===")
rows = db.execute("SELECT invoice_number, po_number, line_items_json, tax_rate FROM invoices LIMIT 5").fetchall()
for r in rows:
    print(f"  {r[0]} PO={r[1]} tax_rate={r[3]} line_items_json={str(r[2])[:300] if r[2] else 'NULL'}")

# Check how many have non-empty line_items_json
ct = db.execute("SELECT COUNT(*) FROM invoices WHERE line_items_json IS NOT NULL AND line_items_json != '' AND line_items_json != '[]'").fetchone()[0]
print(f"\n  Invoices with line_items_json: {ct}")

# Check how many have po_number
ct2 = db.execute("SELECT COUNT(*) FROM invoices WHERE po_number IS NOT NULL AND po_number != ''").fetchone()[0]
print(f"  Invoices with po_number: {ct2}")

# --- PURCHASE ORDERS ---
print("\n=== PO COLUMNS ===")
for c in db.execute("DESCRIBE purchase_orders").fetchall():
    print(f"  {c[0]}: {c[1]}")

print("\n=== PO COUNT ===")
print(db.execute("SELECT COUNT(*) FROM purchase_orders").fetchone()[0])

print("\n=== PO line_items_json SAMPLE ===")
rows = db.execute("SELECT po_number, line_items_json FROM purchase_orders LIMIT 5").fetchall()
for r in rows:
    print(f"  {r[0]}: {str(r[1])[:300] if r[1] else 'NULL'}")

ct3 = db.execute("SELECT COUNT(*) FROM purchase_orders WHERE line_items_json IS NOT NULL AND line_items_json != '' AND line_items_json != '[]'").fetchone()[0]
print(f"\n  POs with line_items_json: {ct3}")

# --- EXPENSE REPORTS ---
print("\n=== EXPENSE REPORT COLUMNS ===")
for c in db.execute("DESCRIBE expense_reports").fetchall():
    print(f"  {c[0]}: {c[1]}")

print("\n=== EXPENSE REPORT COUNT ===")
print(db.execute("SELECT COUNT(*) FROM expense_reports").fetchone()[0])

print("\n=== EXPENSE REPORT SAMPLE ===")
rows = db.execute("SELECT report_id, employee_name, employee_id, hotel_name, stay_start, stay_end, total_amount, expense_lines_json FROM expense_reports LIMIT 5").fetchall()
for r in rows:
    print(f"  {r[0]} emp={r[1]} emp_id={r[2]} hotel={r[3]} stay={r[4]}-{r[5]} total={r[6]}")
    print(f"    expense_lines_json={str(r[7])[:300] if r[7] else 'NULL'}")

ct4 = db.execute("SELECT COUNT(*) FROM expense_reports WHERE expense_lines_json IS NOT NULL AND expense_lines_json != '' AND expense_lines_json != '[]'").fetchone()[0]
print(f"\n  Reports with expense_lines_json: {ct4}")

# --- Check if PO numbers in invoices match POs ---
print("\n=== PO NUMBER CROSS-CHECK ===")
inv_pos = db.execute("SELECT DISTINCT po_number FROM invoices WHERE po_number IS NOT NULL AND po_number != ''").fetchall()
po_nums = db.execute("SELECT DISTINCT po_number FROM purchase_orders").fetchall()
print(f"  Unique PO refs in invoices: {[r[0] for r in inv_pos[:10]]}")
print(f"  Unique PO numbers in POs: {[r[0] for r in po_nums[:10]]}")

# --- Check line item structure ---
print("\n=== LINE ITEM KEYS (first invoice) ===")
row = db.execute("SELECT line_items_json FROM invoices WHERE line_items_json IS NOT NULL AND line_items_json != '' AND line_items_json != '[]' LIMIT 1").fetchone()
if row and row[0]:
    items = json.loads(row[0])
    if items:
        print(f"  Keys: {list(items[0].keys())}")
        print(f"  First item: {items[0]}")

print("\n=== LINE ITEM KEYS (first PO) ===")
row = db.execute("SELECT line_items_json FROM purchase_orders WHERE line_items_json IS NOT NULL AND line_items_json != '' AND line_items_json != '[]' LIMIT 1").fetchone()
if row and row[0]:
    items = json.loads(row[0])
    if items:
        print(f"  Keys: {list(items[0].keys())}")
        print(f"  First item: {items[0]}")

print("\n=== EXPENSE LINE KEYS (first report) ===")
row = db.execute("SELECT expense_lines_json FROM expense_reports WHERE expense_lines_json IS NOT NULL AND expense_lines_json != '' AND expense_lines_json != '[]' LIMIT 1").fetchone()
if row and row[0]:
    items = json.loads(row[0])
    if items:
        print(f"  Keys: {list(items[0].keys())}")
        print(f"  First item: {items[0]}")

# Group invoices by PO to check multi-invoice POs
print("\n=== INVOICES PER PO ===")
rows = db.execute("SELECT po_number, COUNT(*) as cnt FROM invoices WHERE po_number IS NOT NULL AND po_number != '' GROUP BY po_number ORDER BY cnt DESC LIMIT 10").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} invoices")

db.close()
