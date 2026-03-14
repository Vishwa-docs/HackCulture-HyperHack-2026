#!/usr/bin/env python3
"""Check current extraction data quality."""
import json, sys
from collections import Counter
from pathlib import Path

base = Path(__file__).parent.parent

# Load extracted data
ext_path = base / "data/extracted/all_extracted.json"
if not ext_path.exists():
    print("ERROR: all_extracted.json not found")
    sys.exit(1)

with open(ext_path) as f:
    data = json.load(f)

types = Counter(d.get('doc_type','?') for d in data)
print("Document types:")
for t, c in types.most_common():
    print(f"  {t}: {c}")
print(f"Total documents: {len(data)}")

invs = [d for d in data if d.get('doc_type') == 'invoice']
with_li = sum(1 for d in invs if d.get('line_items'))
print(f"\nInvoices with line_items: {with_li}/{len(invs)}")

# Check PO line items
pos = [d for d in data if d.get('doc_type') == 'purchase_order']
with_poli = sum(1 for d in pos if d.get('line_items'))
print(f"POs with line_items: {with_poli}/{len(pos)}")

# Bank statements
bs = [d for d in data if d.get('doc_type') == 'bank_statement']
with_ob = sum(1 for d in bs if d.get('opening_balance'))
print(f"Bank stmts with opening_balance: {with_ob}/{len(bs)}")

# Expense reports
er = [d for d in data if d.get('doc_type') == 'expense_report']
print(f"Expense reports: {len(er)}")

# Credit/Debit notes
cn = [d for d in data if d.get('doc_type') in ('credit_note', 'debit_note')]
print(f"Credit/Debit notes: {len(cn)}")

# Vendor master
vm_path = base / "data/extracted/vendor_master.json"
if vm_path.exists():
    with open(vm_path) as f:
        vm = json.load(f)
    print(f"Vendors in master: {len(vm)}")

# Show a sample invoice
if invs:
    sample = invs[0]
    print(f"\nSample invoice keys: {list(sample.keys())}")
    print(f"  invoice_number: {sample.get('invoice_number')}")
    print(f"  vendor_name: {sample.get('vendor_name')}")
    print(f"  po_number: {sample.get('po_number')}")
    print(f"  line_items count: {len(sample.get('line_items', []))}")
    if sample.get('line_items'):
        li = sample['line_items'][0]
        print(f"  first line_item keys: {list(li.keys())}")

# Show sample PO
if pos:
    sample = pos[0]
    print(f"\nSample PO keys: {list(sample.keys())}")
    print(f"  po_number: {sample.get('po_number')}")
    li = sample.get('line_items', [])
    print(f"  line_items count: {len(li)}")
    if li:
        print(f"  first PO line_item: {li[0]}")

# Show sample bank statement
if bs:
    sample = bs[0]
    print(f"\nSample bank_statement keys: {list(sample.keys())}")
    print(f"  statement_month: {sample.get('statement_month')}")
    print(f"  opening_balance: {sample.get('opening_balance')}")
    print(f"  closing_balance: {sample.get('closing_balance')}")
    txns = sample.get('transactions', [])
    print(f"  transactions count: {len(txns)}")

# Show sample expense report  
if er:
    sample = er[0]
    print(f"\nSample expense_report keys: {list(sample.keys())}")

# Show sample credit note
if cn:
    sample = cn[0]
    print(f"\nSample credit/debit note keys: {list(sample.keys())}")
    print(f"  note_type: {sample.get('note_type')}")
    print(f"  referenced_doc: {sample.get('referenced_doc')}")
