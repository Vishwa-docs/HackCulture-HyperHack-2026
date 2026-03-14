"""Inspect PO and bank statement text to fix extraction."""
import fitz, json

doc = fitz.open('data/input/gauntlet.pdf')
splits = json.loads(open('data/split_docs/document_splits.json').read())

# Find first PO document
for s in splits:
    if s['doc_type'] == 'purchase_order':
        p = s['page_start']
        print(f"=== PO PAGE {p} (doc {s['doc_id']}) ===")
        print(doc[p-1].get_text('text')[:3000])
        print()
        break

# Find bank statement
for s in splits:
    if s['doc_type'] == 'bank_statement':
        p = s['page_start']
        text = doc[p-1].get_text('text')
        print(f"=== BANK STMT PAGE {p} (doc {s['doc_id']}) ===")
        print(text[:3000])
        print()
        break

# Find expense report
for s in splits:
    if s['doc_type'] == 'expense_report':
        p = s['page_start']
        text = doc[p-1].get_text('text')
        print(f"=== EXPENSE PAGE {p} (doc {s['doc_id']}) ===")
        print(text[:3000])
        print()
        break

# Find credit note
for s in splits:
    if s['doc_type'] == 'credit_note':
        p = s['page_start']
        text = doc[p-1].get_text('text')
        print(f"=== CREDIT NOTE PAGE {p} (doc {s['doc_id']}) ===")
        print(text[:3000])
        print()
        break

# Also count POs by checking all PO docs
po_docs = [s for s in splits if s['doc_type'] == 'purchase_order']
print(f"\n=== PO SUMMARY ===")
print(f"Total PO docs: {len(po_docs)}")

# Check extracted data
ext = json.loads(open('data/extracted/all_extracted.json').read())
for po in ext['pos'][:3]:
    print(f"PO {po.get('po_number','?')}: items={len(po.get('line_items',[]))}, vendor={po.get('vendor_name_raw','?')[:30]}")

doc.close()
