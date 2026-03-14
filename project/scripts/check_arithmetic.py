"""Check arithmetic error patterns."""
import json
from decimal import Decimal

e = json.load(open("data/extracted/all_extracted.json"))

# Show line item count distribution
li_counts = [len(i.get("line_items", [])) for i in e["invoices"]]
from collections import Counter
print("Line items per invoice:")
for count, freq in sorted(Counter(li_counts).items()):
    print(f"  {count} items: {freq} invoices")

# Check a specific invoice to see if extraction is complete
inv = next(i for i in e["invoices"] if i["invoice_number"] == "INV-2025-00015")
print(f"\nINV-2025-00015:")
print(f"  line items: {len(inv['line_items'])}")
for li in inv["line_items"]:
    print(f"    #{li['line_num']}: {li['description'][:40]} qty={li.get('quantity')} rate={li.get('unit_rate')} amt={li.get('amount')}")
print(f"  subtotal: {inv.get('subtotal')}")
print(f"  tax_rate: {inv.get('tax_rate')}")
print(f"  tax_amount: {inv.get('tax_amount')}")
print(f"  grand_total: {inv.get('grand_total')}")

# Calculate expected subtotal
total = sum(Decimal(str(li.get("amount", 0) or 0)) for li in inv["line_items"])
print(f"  calc subtotal: {total}")

# Check invoices where line items >= 7 (spanning 2 pages)
many_items = [i for i in e["invoices"] if len(i.get("line_items", [])) >= 7]
print(f"\nInvoices with >= 7 line items: {len(many_items)}")
print(f"Invoices with < 5 line items: {sum(1 for i in e['invoices'] if len(i.get('line_items', [])) < 5)}")

# Show a 2-page invoice
for inv in e["invoices"]:
    pages = inv.get("source_pages", [])
    if len(pages) == 2 and len(inv.get("line_items", [])) >= 7:
        print(f"\n2-page inv {inv['invoice_number']} pages={pages} items={len(inv['line_items'])}")
        for li in inv["line_items"]:
            print(f"    #{li['line_num']}: {li['description'][:40]} amt={li.get('amount')}")
        print(f"  subtotal={inv.get('subtotal')} grand_total={inv.get('grand_total')}")
        break
