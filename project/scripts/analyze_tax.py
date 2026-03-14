#!/usr/bin/env python3
"""Analyze tax parsing to fix wrong_tax_rate."""
import json, re
from decimal import Decimal

d = json.load(open('data/extracted/all_extracted.json'))

# Check first few invoices' raw text tax section carefully
for inv in d['invoices'][:5]:
    raw = inv.get('raw_text', '')
    inv_num = inv.get('invoice_number', '')
    lines = raw.split('\n')
    
    print(f"\n=== {inv_num} ===")
    # Find the section around Subtotal
    for i, line in enumerate(lines):
        if 'Subtotal' in line or 'CGST' in line or 'SGST' in line or 'GRAND TOTAL' in line:
            # Show context: line before and after
            start = max(0, i-1)
            end = min(len(lines), i+2)
            for j in range(start, end):
                print(f"  [{j:3d}] '{lines[j].rstrip()}'")
            print()

# So the pattern is:
# Line N:   I9,00,279.52     <- this is the SUBTOTAL value
# Line N+1: Subtotal:        <- label
# Line N+2: I66,207.07       <- this is the CGST value  
# Line N+3: CGST:            <- label
# Line N+4: I66,207.07       <- this is the SGST value
# Line N+5: SGST:            <- label
# Line N+6: I10,32,693.67    <- this is the GRAND TOTAL value
# Line N+7: GRAND TOTAL:     <- label

# Verify: subtotal + cgst + sgst should equal grand total
print("\n=== VERIFY PATTERN ===")
amount_re = re.compile(r'I[\d,]+\.\d{2}')

for inv in d['invoices'][:10]:
    raw = inv.get('raw_text', '')
    inv_num = inv.get('invoice_number', '')
    lines = raw.split('\n')
    
    subtotal = cgst = sgst = grand_total = None
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped in ('Subtotal:', 'SUBTOTAL:'):
            # Value is line BEFORE
            if i > 0:
                m = amount_re.search(lines[i-1])
                if m:
                    subtotal = Decimal(m.group().replace('I','').replace(',',''))
            # CGST value is line AFTER
            if i+1 < len(lines):
                m = amount_re.search(lines[i+1])
                if m:
                    cgst = Decimal(m.group().replace('I','').replace(',',''))
        elif stripped in ('CGST:',):
            # SGST value is line AFTER
            if i+1 < len(lines):
                m = amount_re.search(lines[i+1])
                if m:
                    sgst = Decimal(m.group().replace('I','').replace(',',''))
        elif stripped in ('SGST:',):
            # Grand total value is line AFTER
            if i+1 < len(lines):
                m = amount_re.search(lines[i+1])
                if m:
                    grand_total = Decimal(m.group().replace('I','').replace(',',''))
    
    if subtotal and cgst and sgst and grand_total:
        computed_total = subtotal + cgst + sgst
        tax_rate = ((cgst + sgst) / subtotal * 100).quantize(Decimal("0.1"))
        match = "OK" if abs(computed_total - grand_total) < 1 else "MISMATCH"
        print(f"  {inv_num}: sub={subtotal}, cgst={cgst}, sgst={sgst}, total={grand_total}, computed={computed_total} [{match}], rate={tax_rate}%")
    else:
        print(f"  {inv_num}: MISSING - sub={subtotal}, cgst={cgst}, sgst={sgst}, gt={grand_total}")
