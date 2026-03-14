#!/usr/bin/env python3
"""Diagnostic: IFSC patterns per vendor, PO line item HSN matching, arithmetic error breakdown."""
import json, re, sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

sys.path.insert(0, '.')
data = json.load(open('data/extracted/all_extracted.json'))
vendors = json.load(open('data/extracted/vendor_master.json'))

def dec(val):
    if val is None: return None
    if isinstance(val, Decimal): return val
    s = str(val).strip()
    s = re.sub(r'^[I₹$€£\s]+', '', s)
    s = s.replace(',', '')
    if s.startswith('(') and s.endswith(')'): s = '-' + s[1:-1]
    if s.startswith('-I') or s.startswith('-₹'): s = '-' + s[2:]
    s = re.sub(r'^[I₹$€£\s]+', '', s)
    if not s or s == '-': return None
    try: return Decimal(s)
    except: return None

def normalize_ref(ref):
    return re.sub(r'\s+', '', str(ref).strip().upper())

def extract_po_line_items(raw_text):
    items = []
    if not raw_text: return items
    start_idx = raw_text.upper().find('ORDER ITEMS')
    if start_idx == -1: return items
    section = raw_text[start_idx:]
    lines = section.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#') or line == 'Amount' or 'Description' in line:
            i += 1; continue
        if re.match(r'^\d+$', line): break
        i += 1
    while i < len(lines):
        line = lines[i].strip()
        if not line: i += 1; continue
        if line.startswith('Subtotal') or line.startswith('GST') or line.startswith('TOTAL') or line.startswith('Authorized'): break
        if re.match(r'^\d+$', line):
            line_num = int(line)
            fields = []
            i += 1
            while i < len(lines) and len(fields) < 6:
                f = lines[i].strip()
                if not f: i += 1; continue
                if f.startswith('Subtotal') or f.startswith('GST') or f.startswith('TOTAL'): break
                if re.match(r'^\d+$', f) and len(fields) >= 4: break
                fields.append(f); i += 1
            if len(fields) >= 5:
                desc = fields[0]
                hsn = fields[1] if re.match(r'^\d{4,8}$', fields[1]) else ""
                offset = 1 if hsn else 0
                try:
                    qty_val = dec(fields[offset + 1])
                    unit = fields[offset + 2]
                    rate_val = dec(fields[offset + 3])
                    amount_val = dec(fields[offset + 4]) if len(fields) > offset + 4 else None
                    items.append({
                        'line_num': line_num, 'description': desc,
                        'hsn_sac': hsn, 'quantity': str(qty_val) if qty_val else None,
                        'unit': unit, 'unit_rate': str(rate_val) if rate_val else None,
                        'amount': str(amount_val) if amount_val else None,
                    })
                except: pass
            continue
        i += 1
    return items

# Fix PO line items
pos = data['pos']
for po in pos:
    if not po.get('line_items') and po.get('raw_text'):
        li = extract_po_line_items(po['raw_text'])
        if li: po['line_items'] = li
real_pos = [po for po in pos if str(po.get('po_number', '')).startswith('PO-')]

# ===== IFSC ANALYSIS =====
print("=" * 60)
print("IFSC ANALYSIS: Per-vendor IFSC distribution")
print("=" * 60)

vendor_by_gstin = {}
vendor_by_name = {}
for v in vendors:
    if v.get('gstin'): vendor_by_gstin[v['gstin'].upper()] = v
    vendor_by_name[v['canonical_name'].lower()] = v
    vendor_by_name[v['raw_name'].lower()] = v

# Group IFSCs by vendor
vendor_ifsc_counts = defaultdict(lambda: defaultdict(list))  # vendor_id -> ifsc -> [inv_nums]
vendor_master_ifsc = {}
for v in vendors:
    vendor_master_ifsc[v.get('vendor_id', '')] = v.get('ifsc', '').upper()

for inv in data['invoices']:
    inv_ifsc = inv.get('bank_ifsc', '').strip().upper()
    if not inv_ifsc: continue
    
    gstin = inv.get('gstin_vendor', '').strip().upper()
    vendor_raw = inv.get('vendor_name_raw', '')
    
    vendor = None
    if gstin and gstin in vendor_by_gstin:
        vendor = vendor_by_gstin[gstin]
    elif vendor_raw and vendor_raw.lower() in vendor_by_name:
        vendor = vendor_by_name[vendor_raw.lower()]
    
    if vendor:
        vid = vendor.get('vendor_id', '')
        vendor_ifsc_counts[vid][inv_ifsc].append(inv.get('invoice_number', ''))

for vid in sorted(vendor_ifsc_counts.keys()):
    master = vendor_master_ifsc.get(vid, '?')
    ifsc_map = vendor_ifsc_counts[vid]
    if len(ifsc_map) > 1 or (len(ifsc_map) == 1 and list(ifsc_map.keys())[0] != master):
        total = sum(len(v) for v in ifsc_map.values())
        print(f"\n{vid} (master: {master}): {total} invoices, {len(ifsc_map)} distinct IFSCs")
        for ifsc, invs in sorted(ifsc_map.items(), key=lambda x: -len(x[1])):
            match = "MATCH" if ifsc == master else "MISMATCH"
            print(f"  {ifsc} [{match}]: {len(invs)} invoices -> {invs[:5]}{'...' if len(invs)>5 else ''}")

# ===== PO LINE ITEM HSN MATCHING =====
print("\n" + "=" * 60)
print("PO-INVOICE LINE ITEM HSN MATCHING")
print("=" * 60)

po_lookup = {}
for po in real_pos:
    pn = po.get('po_number', '').strip()
    if po.get('line_items'):
        po_lookup[normalize_ref(pn)] = po

po_invoices = defaultdict(list)
for inv in data['invoices']:
    po_ref = inv.get('po_number', '').strip()
    if po_ref:
        po_invoices[normalize_ref(po_ref)].append(inv)

hsn_match_total = 0
desc_match_total = 0
no_match_total = 0

for po_ref, inv_list in po_invoices.items():
    po = po_lookup.get(po_ref)
    if not po: continue
    po_items = po.get('line_items', [])
    po_hsns = set(str(li.get('hsn_sac', '')).strip() for li in po_items if li.get('hsn_sac'))
    
    for inv in inv_list:
        for inv_li in inv.get('line_items', []):
            inv_hsn = str(inv_li.get('hsn_sac', '')).strip()
            inv_desc = str(inv_li.get('description', '')).strip().lower()
            
            found_hsn = False
            found_desc = False
            
            if inv_hsn and inv_hsn in po_hsns:
                found_hsn = True
            
            if not found_hsn:
                for po_li in po_items:
                    po_desc = str(po_li.get('description', '')).strip().lower()
                    inv_words = set(inv_desc.split())
                    po_words = set(po_desc.split())
                    if len(inv_words) >= 2 and len(po_words) >= 2:
                        overlap = len(inv_words & po_words) / max(len(inv_words), len(po_words))
                        if overlap >= 0.5:
                            found_desc = True
                            break
            
            if found_hsn:
                hsn_match_total += 1
            elif found_desc:
                desc_match_total += 1
            else:
                no_match_total += 1

print(f"Total line items matched by HSN: {hsn_match_total}")
print(f"Total line items matched by desc only: {desc_match_total}")
print(f"Total line items with no match: {no_match_total}")

# ===== ARITHMETIC ERROR BREAKDOWN =====
print("\n" + "=" * 60)
print("ARITHMETIC ERROR CANDIDATES BREAKDOWN")
print("=" * 60)

amount_pattern = re.compile(r'-?I?[\d,]+\.\d{2}')

def parse_invoice_tax_summary(raw_text):
    if not raw_text: return None, None, None, None
    lines = raw_text.split('\n')
    subtotal_val = cgst_val = sgst_val = igst_val = grand_total_val = None
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.upper() in ('SUBTOTAL:', 'SUB TOTAL:', 'SUBTOTAL'):
            for j in range(i-1, max(0, i-5), -1):
                m = amount_pattern.search(lines[j].strip())
                if m: subtotal_val = dec(m.group()); break
            for j in range(i+1, min(len(lines), i+3)):
                m = amount_pattern.search(lines[j].strip())
                if m: cgst_val = dec(m.group()); break
        elif line.upper() in ('CGST:', 'CGST'):
            for j in range(i+1, min(len(lines), i+3)):
                m = amount_pattern.search(lines[j].strip())
                if m: sgst_val = dec(m.group()); break
        elif line.upper() in ('SGST:', 'SGST'):
            for j in range(i+1, min(len(lines), i+3)):
                m = amount_pattern.search(lines[j].strip())
                if m: grand_total_val = dec(m.group()); break
        elif line.upper() in ('IGST:', 'IGST'):
            for j in range(i+1, min(len(lines), i+3)):
                m = amount_pattern.search(lines[j].strip())
                if m: igst_val = dec(m.group()); break
        elif 'GRAND TOTAL' in line.upper():
            for j in range(i+1, min(len(lines), i+3)):
                m = amount_pattern.search(lines[j].strip())
                if m:
                    if grand_total_val is None: grand_total_val = dec(m.group())
                    break
        i += 1
    return subtotal_val, cgst_val, sgst_val or igst_val, grand_total_val

li_errors = []
sub_errors = []
gt_errors = []

for inv in data['invoices']:
    inv_num = inv.get('invoice_number', '')
    pages = inv.get('source_pages', [])
    line_items = inv.get('line_items', [])
    raw_text = inv.get('raw_text', '')
    
    for li in line_items:
        qty = dec(li.get('quantity'))
        rate = dec(li.get('unit_rate'))
        amount = dec(li.get('amount'))
        if qty and rate and amount and qty > 0 and rate > 0:
            expected = (qty * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            diff = abs(expected - amount)
            if diff > Decimal("1.00") and diff / expected > Decimal("0.001"):
                li_errors.append((float(diff), inv_num, f"L{li.get('line_num','?')}: {qty}x{rate}={expected} vs {amount}"))
    
    real_sub, real_cgst, real_sgst, real_gt = parse_invoice_tax_summary(raw_text)
    
    if real_sub and line_items:
        amounts = [dec(li.get('amount')) for li in line_items]
        amounts = [a for a in amounts if a is not None]
        if amounts:
            expected_sub = sum(amounts, Decimal("0"))
            diff = abs(expected_sub - real_sub)
            if diff > Decimal("1.00") and diff / real_sub > Decimal("0.001"):
                sub_errors.append((float(diff), inv_num, f"Sub: sum={expected_sub} vs parsed={real_sub}"))
    
    if real_sub and real_cgst and real_sgst and real_gt:
        expected_gt = real_sub + real_cgst + real_sgst
        diff = abs(expected_gt - real_gt)
        if diff > Decimal("1.00"):
            gt_errors.append((float(diff), inv_num, f"GT: {real_sub}+{real_cgst}+{real_sgst}={expected_gt} vs {real_gt}"))

print(f"Line-item errors (qty*rate): {len(li_errors)}")
for d, inv_num, desc in sorted(li_errors, reverse=True)[:15]:
    print(f"  diff={d:>12.2f}  {inv_num}: {desc}")

print(f"\nSubtotal errors (sum vs parsed): {len(sub_errors)}")
for d, inv_num, desc in sorted(sub_errors, reverse=True)[:15]:
    print(f"  diff={d:>12.2f}  {inv_num}: {desc}")

print(f"\nGrand total errors (sub+tax vs parsed): {len(gt_errors)}")
for d, inv_num, desc in sorted(gt_errors, reverse=True)[:15]:
    print(f"  diff={d:>12.2f}  {inv_num}: {desc}")
