#!/usr/bin/env python3
"""Diagnostic for v5 improvements - understand data quality."""
import json
from collections import Counter, defaultdict

data = json.load(open('data/extracted/all_extracted.json'))
vendors = json.load(open('data/extracted/vendor_master.json'))

# Basic data inventory
print("=== DATA QUALITY ===")

inv = data['invoices'][0]
print('Invoice keys:', list(inv.keys()))
if inv.get('line_items'):
    print('Invoice line_item keys:', list(inv['line_items'][0].keys()))

# HSN codes in invoices 
hsn_count = 0
for inv in data['invoices']:
    for li in inv.get('line_items', []):
        if li.get('hsn_sac'):
            hsn_count += 1
            break
print(f'Invoices with HSN codes: {hsn_count}/{len(data["invoices"])}')

# GSTIN on invoices
gstin_count = sum(1 for inv in data['invoices'] if inv.get('gstin_vendor'))
print(f'Invoices with gstin_vendor: {gstin_count}/{len(data["invoices"])}')

# IFSC on invoices
ifsc_count = sum(1 for inv in data['invoices'] if inv.get('bank_ifsc'))
print(f'Invoices with bank_ifsc: {ifsc_count}/{len(data["invoices"])}')

# PO refs
po_count = sum(1 for inv in data['invoices'] if inv.get('po_number'))
print(f'Invoices with po_number: {po_count}/{len(data["invoices"])}')

# Sample line items
for po in data['pos']:
    if po.get('line_items'):
        print(f'\nSample PO line item ({po["po_number"]}):')
        print(json.dumps(po['line_items'][0], indent=2))
        break

for inv in data['invoices'][:5]:
    if inv.get('line_items'):
        print(f'\nSample Invoice line item ({inv["invoice_number"]}):')
        print(json.dumps(inv['line_items'][0], indent=2))
        break

# Check how many invoice<->PO pairs match by HSN
print("\n=== PO-INVOICE HSN MATCHING ===")
# Build PO lookup
import re
def normalize_ref(ref):
    return re.sub(r'\s+', '', str(ref).strip().upper())

po_lookup = {}
for po in data['pos']:
    pn = po.get('po_number', '').strip()
    if pn.startswith('PO-') and po.get('line_items'):
        po_lookup[normalize_ref(pn)] = po

matched_pairs = 0
unmatched_pairs = 0
hsn_match_count = 0
desc_only_count = 0
no_match_count = 0

for inv in data['invoices']:
    po_ref = inv.get('po_number', '').strip()
    if not po_ref:
        continue
    po = po_lookup.get(normalize_ref(po_ref))
    if not po:
        continue
    
    inv_items = inv.get('line_items', [])
    po_items = po.get('line_items', [])
    
    for inv_li in inv_items:
        inv_hsn = str(inv_li.get('hsn_sac', '')).strip()
        inv_desc = str(inv_li.get('description', '')).strip().lower()
        
        # Try HSN match
        found_hsn = False
        found_desc = False
        for po_li in po_items:
            po_hsn = str(po_li.get('hsn_sac', '')).strip()
            po_desc = str(po_li.get('description', '')).strip().lower()
            
            if inv_hsn and po_hsn and inv_hsn == po_hsn:
                found_hsn = True
                break
            
            inv_words = set(inv_desc.split())
            po_words = set(po_desc.split())
            if len(inv_words) >= 2 and len(po_words) >= 2:
                overlap = len(inv_words & po_words) / max(len(inv_words), len(po_words))
                if overlap >= 0.6:
                    found_desc = True
        
        if found_hsn:
            hsn_match_count += 1
        elif found_desc:
            desc_only_count += 1
        else:
            no_match_count += 1

print(f"Line items with HSN match to PO: {hsn_match_count}")
print(f"Line items with desc-only match to PO: {desc_only_count}")
print(f"Line items with no match to PO: {no_match_count}")

# Show IFSC mismatch details
print("\n=== IFSC MISMATCH ANALYSIS ===")
vendor_by_gstin = {}
vendor_by_name = {}
for v in vendors:
    if v.get('gstin'):
        vendor_by_gstin[v['gstin'].upper()] = v
    vendor_by_name[v['canonical_name'].lower()] = v
    vendor_by_name[v['raw_name'].lower()] = v

gstin_based = 0
exact_name_based = 0
for inv in data['invoices']:
    inv_ifsc = inv.get('bank_ifsc', '').strip().upper()
    if not inv_ifsc:
        continue
    
    gstin = inv.get('gstin_vendor', '').strip().upper()
    vendor_raw = inv.get('vendor_name_raw', '')
    
    vendor = None
    match_method = None
    if gstin and gstin in vendor_by_gstin:
        vendor = vendor_by_gstin[gstin]
        match_method = 'gstin'
    elif vendor_raw and vendor_raw.lower() in vendor_by_name:
        vendor = vendor_by_name[vendor_raw.lower()]
        match_method = 'exact_name'
    
    if vendor and vendor.get('ifsc'):
        master_ifsc = vendor['ifsc'].strip().upper()
        if inv_ifsc != master_ifsc:
            if match_method == 'gstin':
                gstin_based += 1
            else:
                exact_name_based += 1

print(f"IFSC mismatches (GSTIN-based vendor match): {gstin_based}")
print(f"IFSC mismatches (exact name match): {exact_name_based}")

# Check date_cascade magnitude distribution
print("\n=== DATE CASCADE ANALYSIS ===")
from datetime import datetime

def parse_date(s):
    s = str(s).strip()
    for fmt_str in ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"]:
        try:
            return datetime.strptime(s, fmt_str).date()
        except ValueError:
            continue
    return None

gaps = []
for inv in data['invoices']:
    po_ref = inv.get('po_number', '').strip()
    inv_date_str = inv.get('invoice_date', '')
    if not po_ref or not inv_date_str:
        continue
    po = po_lookup.get(normalize_ref(po_ref))
    if not po:
        continue
    po_date_str = po.get('po_date', '')
    if not po_date_str:
        continue
    inv_date = parse_date(inv_date_str)
    po_date = parse_date(po_date_str)
    if inv_date and po_date and inv_date < po_date:
        gap = (po_date - inv_date).days
        gaps.append((gap, inv.get('invoice_number'), po.get('po_number')))

gaps.sort(reverse=True)
print(f"Total date cascades: {len(gaps)}")
print(f"Top 15 by gap:")
for gap, inv_num, po_num in gaps[:15]:
    print(f"  {gap:4d} days: {inv_num} before {po_num}")
print(f"Bottom 10 by gap:")
for gap, inv_num, po_num in gaps[-10:]:
    print(f"  {gap:4d} days: {inv_num} before {po_num}")

# Check arithmetic error tax parse quality
print("\n=== ARITHMETIC ERROR ANALYSIS ===")
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
def dec(val):
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    s = str(val).strip()
    s = re.sub(r'^[I₹$€£\s]+', '', s)
    s = s.replace(',', '')
    if s.startswith('(') and s.endswith(')'):
        s = '-' + s[1:-1]
    if s.startswith('-I') or s.startswith('-₹'):
        s = '-' + s[2:]
    s = re.sub(r'^[I₹$€£\s]+', '', s)
    if not s or s == '-':
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None

# Count line-item arithmetic errors vs tax-summary errors
line_item_errors = 0
tax_errors = 0
for inv in data['invoices']:
    for li in inv.get('line_items', []):
        qty = dec(li.get('quantity'))
        rate = dec(li.get('unit_rate'))
        amount = dec(li.get('amount'))
        if qty and rate and amount and qty > 0 and rate > 0:
            expected = (qty * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            diff = abs(expected - amount)
            if diff > Decimal("1.00") and diff / expected > Decimal("0.001"):
                line_item_errors += 1

print(f"Line item qty*rate errors (>1Rs & >0.1%): {line_item_errors}")

# Check how many PO line items have matching invoice line items by HSN
print("\n=== QUANTITY ACCUMULATION: HSN vs DESC MATCHING ===")
po_invoices = defaultdict(list)
for inv in data['invoices']:
    po_ref = inv.get('po_number', '').strip()
    if po_ref:
        po_invoices[normalize_ref(po_ref)].append(inv)

hsn_matches = 0
desc_only_matches = 0
for po_ref, inv_list in po_invoices.items():
    if len(inv_list) < 2:
        continue
    po = po_lookup.get(po_ref)
    if not po:
        continue
    for po_li in po.get('line_items', []):
        po_hsn = str(po_li.get('hsn_sac', '')).strip()
        po_desc = str(po_li.get('description', '')).strip().lower()
        for inv in inv_list:
            for inv_li in inv.get('line_items', []):
                inv_hsn = str(inv_li.get('hsn_sac', '')).strip()
                inv_desc = str(inv_li.get('description', '')).strip().lower()
                if po_hsn and inv_hsn and po_hsn == inv_hsn:
                    hsn_matches += 1
                else:
                    inv_words = set(inv_desc.split())
                    po_words = set(po_desc.split())
                    if len(inv_words) >= 2 and len(po_words) >= 2:
                        overlap = len(inv_words & po_words) / max(len(inv_words), len(po_words))
                        if overlap >= 0.6:
                            desc_only_matches += 1

print(f"HSN matches: {hsn_matches}")
print(f"Desc-only matches: {desc_only_matches}")

# Expense report hotel analysis
print("\n=== EXPENSE REPORT ANALYSIS ===")
for er in data['expense_reports'][:3]:
    print(f"\nReport {er.get('report_id')}: employee={er.get('employee_name')} ({er.get('employee_id')})")
    print(f"  hotel_name={er.get('hotel_name')}")
    for el in er.get('expense_lines', [])[:3]:
        print(f"  line: {el.get('description')} = {el.get('amount')}")

# Vendor name typo analysis
print("\n=== VENDOR NAME ANALYSIS ===")
from difflib import SequenceMatcher
vendor_names = set(v['canonical_name'].lower() for v in vendors)
vendor_names.update(v['raw_name'].lower() for v in vendors)

typo_candidates = []
for inv in data['invoices']:
    vname = inv.get('vendor_name_raw', '').strip()
    if not vname:
        continue
    vl = vname.lower()
    if vl in vendor_names:
        continue
    best_score = 0
    best_match = ''
    for vn in vendor_names:
        score = SequenceMatcher(None, vl, vn).ratio()
        if score > best_score:
            best_score = score
            best_match = vn
    if 0.65 <= best_score < 1.0:
        typo_candidates.append((best_score, vname, best_match, inv.get('invoice_number')))

typo_candidates.sort(reverse=True)
print(f"Vendor name mismatch candidates: {len(typo_candidates)}")
for score, vname, match, inv_num in typo_candidates[:20]:
    category = "TYPO" if 0.70 <= score < 0.98 else "FAKE?" if score < 0.70 else "CLOSE"
    print(f"  {score:.3f} [{category}] '{vname}' -> '{match}' ({inv_num})")
