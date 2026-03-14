#!/usr/bin/env python3
import json, re
from collections import defaultdict

d = json.load(open('data/extracted/all_extracted.json'))

# Check actual GST pattern in raw text
print("=== RAW TEXT GST PATTERNS ===")
for inv in d['invoices'][:5]:
    raw = inv.get('raw_text', '')
    inv_num = inv.get('invoice_number', '')
    
    # Find all lines after "TAX SUMMARY" or "CGST" or "SGST"
    lines = raw.split('\n')
    for i, line in enumerate(lines):
        if any(w in line.upper() for w in ['CGST', 'SGST', 'IGST', 'TAX SUMMARY', 'TAX BREAKUP', 'SUBTOT', 'TOTAL', 'GRAND']):
            context = lines[max(0,i-1):min(len(lines),i+3)]
            print(f"  {inv_num} line {i}: {' | '.join(l.strip() for l in context if l.strip())}")

print("\n=== FULL TAX SECTION OF FIRST INVOICE ===")
raw = d['invoices'][0].get('raw_text', '')
lines = raw.split('\n')
capture = False
for i, line in enumerate(lines):
    if 'Subtotal' in line or 'SUBTOTAL' in line or 'Sub Total' in line:
        capture = True
    if capture:
        print(f"  {i}: {line.rstrip()}")
    if capture and ('Authorized' in line or 'Notes' in line or i > 300):
        break

# Check multiple invoices for CGST/SGST values and rates
print("\n=== CGST/SGST RATES FROM RAW TEXT ===")
rate_counts = defaultdict(int)
for inv in d['invoices'][:50]:
    raw = inv.get('raw_text', '')
    # Look for CGST @9% or CGST (9%) or CGST: 9% patterns
    for m in re.finditer(r'(CGST|SGST|IGST)\s*(?:[@(]\s*)?(\d+(?:\.\d+)?)\s*%', raw, re.IGNORECASE):
        tax_type = m.group(1).upper()
        rate = m.group(2)
        rate_counts[f"{tax_type}@{rate}%"] += 1
        
    # Alternative: look for percentage in tax lines
    for m in re.finditer(r'(\d+(?:\.\d+)?)\s*%', raw):
        rate = m.group(1)
        # Get surrounding context
        start = max(0, m.start() - 50)
        context = raw[start:m.end()+10].replace('\n', ' ')
        if any(w in context.upper() for w in ['CGST', 'SGST', 'IGST', 'GST']):
            rate_counts[f"GST@{rate}%"] += 1

print(f"  Rate patterns found: {dict(rate_counts)}")

# Let me also look at the format of subtotal->tax->total section
print("\n=== SUBTOTAL/TAX/TOTAL PATTERN ===")
for inv in d['invoices'][:3]:
    raw = inv.get('raw_text', '')
    inv_num = inv.get('invoice_number', '')
    print(f"\n  --- {inv_num} ---")
    print(f"  Extracted: subtotal={inv.get('subtotal')}, tax={inv.get('tax_amount')}, total={inv.get('grand_total')}")
    
    lines = raw.split('\n')
    in_summary = False
    for i, line in enumerate(lines):
        l = line.strip().upper()
        if 'SUBTOTAL' in l or 'SUB TOTAL' in l or 'LINE TOTAL' in l:
            in_summary = True
        if in_summary:
            print(f"    {line.strip()}")
        if in_summary and ('AUTHORIZED' in l or 'NOTE' in l or 'PLACE OF SUPPLY' in l or 'COMPLIANCE' in l):
            break
