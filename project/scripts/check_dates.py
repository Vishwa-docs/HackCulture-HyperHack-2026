"""Check date cascade findings."""
import json

e = json.load(open("data/extracted/all_extracted.json"))

# Build PO lookup
po_lookup = {}
for po in e["pos"]:
    if po.get("po_number"):
        po_lookup[po["po_number"]] = po

# Check inv dates vs PO dates
count = 0
for inv in e["invoices"]:
    po_ref = inv.get("po_number", "")
    if not po_ref:
        continue
    po = po_lookup.get(po_ref)
    if not po:
        continue
    inv_date = inv.get("invoice_date", "")
    po_date = po.get("po_date", "")
    if inv_date and po_date:
        count += 1

print(f"Invoices with matching PO: {count}")
print(f"POs with dates: {sum(1 for p in e['pos'] if p.get('po_date'))}/{len(e['pos'])}")

# Show some PO dates
for po in e["pos"][:10]:
    if po.get("po_number"):
        print(f"  {po['po_number']} date={po.get('po_date','')} delivery={po.get('delivery_date','')}")
