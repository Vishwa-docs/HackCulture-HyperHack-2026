#!/usr/bin/env python3
"""Check POs that don't have ORDER ITEMS header."""
import json, re

d = json.load(open('data/extracted/all_extracted.json'))

# Check POs without ORDER ITEMS
no_header = []
for po in d['pos']:
    raw = po.get('raw_text', '')
    if not raw or 'ORDER ITEMS' not in raw.upper():
        no_header.append(po)

print(f"POs without ORDER ITEMS: {len(no_header)}")

# Check what they look like
for po in no_header[:5]:
    pn = po.get('po_number', '')
    raw = po.get('raw_text', '')[:400] if po.get('raw_text') else 'NO RAW TEXT'
    existing_li = po.get('line_items', [])
    print(f"\n--- {pn} (existing line_items: {len(existing_li)}) ---")
    print(raw[:400])
    print("...")

# Check if any have line item data from the original extraction
has_li = sum(1 for po in no_header if po.get('line_items'))
print(f"\nPOs without ORDER ITEMS but WITH line_items: {has_li}")

# Check if any POs reference a different format
print("\n=== ALTERNATIVE PO FORMATS ===")
for po in no_header[:3]:
    raw = po.get('raw_text', '')
    if not raw: continue
    pn = po.get('po_number', '')
    # Look for table-like patterns
    for line in raw.split('\n'):
        l = line.strip().upper()
        if any(w in l for w in ['#', 'ITEM', 'QTY', 'RATE', 'AMOUNT', 'DESCRIPTION']):
            print(f"  {pn}: '{line.strip()}'")

# Check the complete line item structure for a working PO  
print("\n=== WORKING PO LINE ITEMS ===")
for po in d['pos']:
    raw = po.get('raw_text', '')
    if 'ORDER ITEMS' in (raw or '').upper():
        pn = po.get('po_number', '')
        # Parse with the existing logic
        idx = raw.upper().find('ORDER ITEMS')
        section = raw[idx:]
        lines = section.split('\n')
        print(f"\nPO {pn} - first 30 lines after ORDER ITEMS:")
        for i, line in enumerate(lines[:30]):
            print(f"  [{i:2d}] '{line.rstrip()}'")
        break

# Check subtotal pattern in POs  
print("\n=== PO SUBTOTAL PATTERN ===")
for po in d['pos'][:5]:
    raw = po.get('raw_text', '')
    if not raw: continue
    pn = po.get('po_number', '')
    for i, line in enumerate(raw.split('\n')):
        if 'Subtotal' in line or 'TOTAL' in line or 'GST' in line:
            lines = raw.split('\n')
            start = max(0, i-1)
            end = min(len(lines), i+2) 
            for j in range(start, end):
                print(f"  {pn} [{j}] '{lines[j].rstrip()}'")
            print()
            break
