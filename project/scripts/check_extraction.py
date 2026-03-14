"""Check extraction quality."""
import json

e = json.load(open("data/extracted/all_extracted.json"))

# Check POs
po_with_num = sum(1 for p in e["pos"] if p.get("po_number"))
po_no_num = sum(1 for p in e["pos"] if not p.get("po_number"))
print(f"POs with number: {po_with_num}, without: {po_no_num}")
for p in e["pos"][:3]:
    print(f"  po={p.get('po_number','?')} vendor={p.get('vendor_name_raw','?')[:40]} pages={p.get('source_pages')}")

# Check invoices
inv_with_po = sum(1 for i in e["invoices"] if i.get("po_number"))
inv_with_items = sum(1 for i in e["invoices"] if len(i.get("line_items", [])) > 0)
print(f"\nInvoices with PO ref: {inv_with_po}/{len(e['invoices'])}")
print(f"Invoices with line items: {inv_with_items}/{len(e['invoices'])}")

# Sample invoice
i = e["invoices"][0]
print(f"\nSample invoice: {i['invoice_number']}")
print(f"  vendor: {i.get('vendor_name_raw','')}")
print(f"  date: {i.get('invoice_date','')}")
print(f"  po: {i.get('po_number','')}")
print(f"  gstin: {i.get('gstin_vendor','')}")
print(f"  ifsc: {i.get('bank_ifsc','')}")
print(f"  subtotal: {i.get('subtotal')}")
print(f"  tax_rate: {i.get('tax_rate')}")
print(f"  tax_amount: {i.get('tax_amount')}")
print(f"  grand total: {i.get('grand_total')}")
print(f"  line items: {len(i.get('line_items',[]))}")
for li in i.get("line_items", [])[:3]:
    print(f"    #{li['line_num']}: {li['description'][:40]} qty={li.get('quantity')} rate={li.get('unit_rate')} amt={li.get('amount')}")

# Check bank statements
print(f"\nBank statements: {len(e['bank_statements'])}")
for bs in e["bank_statements"][:3]:
    print(f"  {bs.get('statement_id','')} month={bs.get('statement_month','')} open={bs.get('opening_balance')} close={bs.get('closing_balance')} txns={len(bs.get('transactions',[]))}")

# Check expense reports
print(f"\nExpense reports: {len(e['expense_reports'])}")
for er in e["expense_reports"][:3]:
    print(f"  {er.get('report_id','')} emp={er.get('employee_name','')} emp_id={er.get('employee_id','')} lines={len(er.get('expense_lines',[]))}")

# Check credit/debit notes
print(f"\nCredit/debit notes: {len(e['credit_debit_notes'])}")
for n in e["credit_debit_notes"][:5]:
    print(f"  {n.get('note_number','')} type={n.get('note_type','')} ref={n.get('referenced_doc','')} amt={n.get('amount')}")
