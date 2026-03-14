#!/usr/bin/env python3
"""Quick diagnostic of FP-prone categories."""
import json, re
from collections import defaultdict, Counter
from decimal import Decimal, InvalidOperation

d = json.load(open('data/extracted/all_extracted.json'))
vm = json.load(open('data/extracted/vendor_master.json'))

def dec(val):
    if val is None: return None
    s = str(val).strip()
    s = re.sub(r'^[I₹$€£\s]+', '', s)
    s = s.replace(',', '')
    if s.startswith('-I') or s.startswith('-₹'): s = '-' + s[2:]
    s = re.sub(r'^[I₹$€£\s]+', '', s)
    if not s or s == '-': return None
    try: return Decimal(s)
    except: return None

# 1. PO PARSING: Why do 70 POs fail?
print("=== PO LINE ITEM PARSING ANALYSIS ===")
success = fail = 0
fail_samples = []
for po in d['pos']:
    raw = po.get('raw_text', '')
    has_items = bool(po.get('line_items'))
    has_order_items = 'ORDER ITEMS' in raw.upper() if raw else False
    
    if has_order_items and not has_items:
        fail += 1
        if len(fail_samples) < 3:
            fail_samples.append(po)
    elif has_order_items and has_items:
        success += 1

print(f"POs with ORDER ITEMS header: success={success}, fail={fail}")
print(f"POs without ORDER ITEMS header: {135 - success - fail}")

# Show a failing PO's raw text around ORDER ITEMS
if fail_samples:
    raw = fail_samples[0].get('raw_text', '')
    idx = raw.upper().find('ORDER ITEMS')
    print(f"\nFailing PO {fail_samples[0].get('po_number','')} raw text around ORDER ITEMS:")
    section = raw[idx:idx+600]
    for i, line in enumerate(section.split('\n')[:25]):
        print(f"  [{i}] '{line.rstrip()}'")

# 2. DUPLICATE LINE ITEM: Why only 1 found?
print("\n=== DUPLICATE LINE ITEM ANALYSIS ===")
dup_count = 0
near_dup_count = 0
for inv in d['invoices']:
    lis = inv.get('line_items', [])
    if len(lis) < 2: continue
    
    # Exact desc+amount
    sigs = defaultdict(list)
    for li in lis:
        desc = str(li.get('description', '')).strip().lower()
        amt = str(li.get('amount', ''))
        sigs[f"{desc}|{amt}"].append(li)
    
    for sig, items in sigs.items():
        if len(items) > 1:
            dup_count += 1
    
    # Near duplicates: same desc only
    desc_groups = defaultdict(list)
    for li in lis:
        desc = str(li.get('description', '')).strip().lower()
        desc_groups[desc].append(li)
    
    for desc, items in desc_groups.items():
        if len(items) > 1 and desc:
            near_dup_count += 1
            if near_dup_count <= 5:
                inv_num = inv.get('invoice_number', '')
                print(f"  Near-dup in {inv_num}: desc='{desc}', amounts={[li.get('amount') for li in items]}")

print(f"Exact duplicates (desc+amount): {dup_count}")
print(f"Near duplicates (desc only): {near_dup_count}")

# 3. ARITHMETIC ERROR: Check for false positives from OCR
print("\n=== ARITHMETIC ERROR FP ANALYSIS ===")
# Look at the raw text to verify amounts
arith_fps = 0
arith_tps = 0
for inv in d['invoices'][:50]:
    for li in inv.get('line_items', []):
        qty = dec(li.get('quantity'))
        rate = dec(li.get('unit_rate'))
        amount = dec(li.get('amount'))
        if qty and rate and amount and qty > 0 and rate > 0:
            expected = (qty * rate).quantize(Decimal("0.01"))
            diff = abs(expected - amount)
            if diff > Decimal("1.00") and diff / expected > Decimal("0.001"):
                # Check if this is a real error or extraction artifact
                desc = li.get('description', '')[:40]
                pct = float(diff / expected * 100)
                if pct > 10:
                    arith_fps += 1  # Likely extraction error, not real doc error
                else:
                    arith_tps += 1
                if arith_fps + arith_tps <= 10:
                    print(f"  qty={qty} rate={rate} expected={expected} actual={amount} diff={diff} ({pct:.1f}%)")

# 4. Check PO parsing - alternative format
print("\n=== PO FORMAT CHECK ===")
# Check if some POs use different header
for po in d['pos'][:5]:
    raw = po.get('raw_text', '')
    if not raw: continue
    headers = []
    for line in raw.split('\n'):
        l = line.strip().upper()
        if any(w in l for w in ['ITEMS', 'LINE', 'DESCRIPTION', 'QTY', 'QUANTITY', 'RATE', 'AMOUNT', 'HSN', 'SAC']):
            headers.append(line.strip())
    if headers:
        print(f"  {po.get('po_number','')}: {headers[:5]}")

# 5. Check page number accuracy  
print("\n=== PAGE NUMBER SAMPLES ===")
for inv in d['invoices'][:5]:
    print(f"  {inv.get('invoice_number','')}: pages={inv.get('source_pages',[])} raw_text[:60]={inv.get('raw_text','')[:60]}")
    # Check if page number appears in raw text
    raw = inv.get('raw_text', '')
    page_refs = re.findall(r'Page\s+(\d+)', raw)
    if page_refs:
        print(f"    Page refs in text: {page_refs}")
