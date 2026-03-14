#!/usr/bin/env python3
"""Check current data quality."""
import json
from pathlib import Path

base = Path(__file__).parent.parent

d = json.load(open(base / "data/extracted/all_extracted.json"))

pos = d['pos']
with_li = sum(1 for p in pos if p.get('line_items'))
print(f"POs with line_items: {with_li}/{len(pos)}")

invs = d['invoices']
with_li_inv = sum(1 for i in invs if i.get('line_items'))
with_po = sum(1 for i in invs if i.get('po_number'))
print(f"Invoices with line_items: {with_li_inv}/{len(invs)}")
print(f"Invoices with po_number: {with_po}/{len(invs)}")

# Sample invoice
if invs:
    s = invs[0]
    print(f"Sample inv: {s.get('invoice_number')}, vendor={s.get('vendor_name_raw')}, po={s.get('po_number')}")
    if s.get('line_items'):
        print(f"  LI[0]: {s['line_items'][0]}")
    print(f"  subtotal={s.get('subtotal')}, tax={s.get('tax_amount')}, total={s.get('grand_total')}")

bs = d['bank_statements']
with_ob = sum(1 for b in bs if b.get('opening_balance'))
with_txns = sum(1 for b in bs if b.get('transactions'))
print(f"\nBank stmts with opening_balance: {with_ob}/{len(bs)}")
print(f"Bank stmts with transactions: {with_txns}/{len(bs)}")
if bs:
    s = bs[0]
    print(f"Sample BS: month={s.get('statement_month')}, OB={s.get('opening_balance')}, CB={s.get('closing_balance')}")

er = d['expense_reports'] 
with_el = sum(1 for e in er if e.get('expense_lines'))
with_hotel = sum(1 for e in er if e.get('hotel_name'))
print(f"\nExpense reports: {len(er)}, with_lines: {with_el}, with_hotel: {with_hotel}")
if er:
    s = er[0]
    print(f"Sample ER: id={s.get('report_id')}, emp={s.get('employee_name')}, eid={s.get('employee_id')}")
    if s.get('expense_lines'):
        print(f"  EL[0]: {s['expense_lines'][0]}")

cn = d['credit_debit_notes']
with_ref = sum(1 for c in cn if c.get('referenced_doc'))
print(f"\nCredit/debit notes: {len(cn)}, with_ref: {with_ref}")

# Sample PO
if pos and with_li > 0:
    for p in pos:
        if p.get('line_items'):
            print(f"\nSample PO: {p.get('po_number')}")
            if p['line_items']:
                print(f"  LI[0]: {p['line_items'][0]}")
            break

vm = json.load(open(base / "data/extracted/vendor_master.json"))
print(f"\nVendors in master: {len(vm)}")
if vm:
    print(f"Sample vendor: {vm[0]}")
