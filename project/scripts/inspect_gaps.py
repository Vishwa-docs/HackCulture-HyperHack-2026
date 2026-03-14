#!/usr/bin/env python3
import json

d = json.load(open('data/extracted/all_extracted.json'))
vm = json.load(open('data/extracted/vendor_master.json'))

# 1. wrong_tax_rate: check what tax info is available
print("=== INVOICE TAX FIELDS ===")
inv = d['invoices'][0]
print(f"tax_rate: {inv.get('tax_rate')}")
print(f"gst_rate: {inv.get('gst_rate')}")
print(f"tax_amount: {inv.get('tax_amount')}")
li = inv.get('line_items', [])
if li:
    print(f"Line item keys: {list(li[0].keys())}")
    print(f"Line item sample: {li[0]}")
print()

has_li_tax = sum(1 for inv2 in d['invoices'] for li2 in inv2.get('line_items',[]) if li2.get('tax_rate'))
print(f"Line items with tax_rate set: {has_li_tax}")

gst_rates = {}
for inv2 in d['invoices']:
    r = str(inv2.get('gst_rate', ''))
    gst_rates[r] = gst_rates.get(r, 0) + 1
print(f"GST rate distribution: {gst_rates}")

# Check invoice-level: subtotal + tax vs what rate that implies
print("\n=== INFERRED TAX RATES ===")
from decimal import Decimal, InvalidOperation
count_rates = {}
for inv2 in d['invoices']:
    sub = inv2.get('subtotal')
    tax = inv2.get('tax_amount')
    if sub and tax:
        try:
            s = Decimal(str(sub).replace(',','').replace('I','').replace('₹',''))
            t = Decimal(str(tax).replace(',','').replace('I','').replace('₹',''))
            if s > 0:
                rate = (t / s * 100).quantize(Decimal("0.1"))
                k = str(rate)
                count_rates[k] = count_rates.get(k, 0) + 1
        except:
            pass
print(f"Inferred rate distribution: {dict(sorted(count_rates.items(), key=lambda x: -x[1]))}")

# 2. gstin_state_mismatch
print("\n=== VENDOR GSTIN STATE CHECK ===")
GST_STATE_CODES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "25": "Daman & Diu", "26": "Dadra & Nagar Haveli",
    "27": "Maharashtra", "28": "Andhra Pradesh", "29": "Karnataka",
    "30": "Goa", "31": "Lakshadweep", "32": "Kerala",
    "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman & Nicobar Islands", "36": "Telangana",
    "37": "Andhra Pradesh", "38": "Ladakh",
}
for v in vm:
    gstin = v.get('gstin','')
    code = gstin[:2] if len(gstin) >= 2 else ''
    expected = GST_STATE_CODES.get(code, 'UNKNOWN')
    state = v.get('state', '')
    match = expected.lower() == state.lower()
    if not match:
        print(f"  MISMATCH: {v['canonical_name']}: GSTIN={gstin}, code={code}={expected}, state={state}")

# 3. duplicate_expense
print("\n=== EXPENSE REPORT STRUCTURE ===")
er = d['expense_reports'][0]
print(f"report_id: {er.get('report_id')}")
print(f"employee_id: {er.get('employee_id')}")
print(f"employee_name: {er.get('employee_name')}")
print(f"hotel_name: {er.get('hotel_name')}")
print(f"stay_start: {er.get('stay_start')}")
print(f"stay_end: {er.get('stay_end')}")
if er.get('expense_lines'):
    print(f"Expense line keys: {list(er['expense_lines'][0].keys())}")
    for el in er['expense_lines'][:3]:
        print(f"  {el}")
print()

hotel_count = sum(1 for e in d['expense_reports'] if e.get('hotel_name'))
stay_count = sum(1 for e in d['expense_reports'] if e.get('stay_start'))
print(f"Expense reports with hotel_name: {hotel_count}/64")
print(f"Expense reports with stay_start: {stay_count}/64")

# Check expense lines for potential duplicates
from collections import defaultdict
all_exp_lines = []
for er2 in d['expense_reports']:
    for el in er2.get('expense_lines', []):
        el['_report_id'] = er2.get('report_id','')
        el['_employee_id'] = er2.get('employee_id','')
        all_exp_lines.append(el)

# Group by employee + amount + date
print(f"\nTotal expense lines: {len(all_exp_lines)}")
groups = defaultdict(list)
for el in all_exp_lines:
    key = f"{el.get('_employee_id','')}|{el.get('amount','')}|{el.get('date','')}"
    groups[key].append(el)

dupes = {k: v for k, v in groups.items() if len(v) >= 2 and len(set(e['_report_id'] for e in v)) >= 2}
print(f"Potential duplicate expense groups (same emp+amount+date, diff reports): {len(dupes)}")
for k, v in list(dupes.items())[:3]:
    print(f"  {k}: reports={[e['_report_id'] for e in v]}")

# 4. credit/debit notes for circular refs
print("\n=== CREDIT/DEBIT NOTES ===")
for cn in d['credit_debit_notes']:
    print(f"  {cn.get('note_number')}: type={cn.get('note_type')}, ref={cn.get('referenced_doc')}, target={cn.get('target_doc')}, linked={cn.get('linked_documents')}")

# 5. Check raw text of expense reports for hotel and triple claims
print("\n=== EXPENSE REPORT RAW TEXT SAMPLE ===")
er_sample = d['expense_reports'][0]
raw = er_sample.get('raw_text', '')[:500]
print(raw)
