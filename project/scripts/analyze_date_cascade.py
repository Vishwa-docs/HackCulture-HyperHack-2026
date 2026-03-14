"""Analyze date cascade findings."""
import sys
sys.path.insert(0, ".")
from src.normalization.dates import parse_date
import duckdb
from collections import Counter

db = duckdb.connect("data/indexes/needle_finder.duckdb", read_only=True)

rows = db.execute("""
    SELECT i.invoice_number, i.invoice_date, i.po_number, p.po_date
    FROM invoices i
    JOIN purchase_orders p ON i.po_number = p.po_number
    WHERE i.po_number IS NOT NULL AND i.po_number != ''
    AND i.invoice_date != '' AND p.po_date != ''
""").fetchall()

before_count = 0
differences = []
for r in rows:
    inv_d = parse_date(r[1])
    po_d = parse_date(r[3])
    if inv_d and po_d and inv_d < po_d:
        before_count += 1
        diff = (po_d - inv_d).days
        differences.append((diff, r[0], r[1], r[2], r[3]))

print(f"Invoices before PO: {before_count} / {len(rows)}")
diffs = [d[0] for d in differences]
print(f"Diff distribution (days): min={min(diffs)}, max={max(diffs)}, median={sorted(diffs)[len(diffs)//2]}")

buckets = {"1-7": 0, "8-30": 0, "31-90": 0, "91-180": 0, "180+": 0}
for d in diffs:
    if d <= 7: buckets["1-7"] += 1
    elif d <= 30: buckets["8-30"] += 1
    elif d <= 90: buckets["31-90"] += 1
    elif d <= 180: buckets["91-180"] += 1
    else: buckets["180+"] += 1
print(f"Buckets: {buckets}")

# How many PO numbers are reused?
po_nums = [r[2] for r in rows]
po_counts = Counter(po_nums)
multi_use = {k: v for k, v in po_counts.items() if v > 1}
print(f"POs referenced by multiple invoices: {len(multi_use)} (max {max(po_counts.values())} refs)")

# Show some examples from each bucket
print("\nSmall diffs (1-7 days):")
for d in sorted(differences)[:5]:
    print(f"  {d[1]}: inv={d[2]} po={d[3]} po_date={d[4]} diff={d[0]}d")

print("\nLarge diffs (180+ days):")
for d in sorted(differences, reverse=True)[:5]:
    print(f"  {d[1]}: inv={d[2]} po={d[3]} po_date={d[4]} diff={d[0]}d")
