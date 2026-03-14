"""Test PO line item extraction after fix."""
import fitz, json, sys, re, os
from decimal import Decimal, InvalidOperation
from typing import Optional

# Inline the minimal extraction logic to test independently
def _clean_amount(s):
    if not s or s.strip() in ("", "-", "None", "null"):
        return None
    s = s.strip()
    negative = s.startswith('-')
    if negative:
        s = s[1:]
    s = re.sub(r'^[I₹$€£\s]+', '', s)
    s = re.sub(r'[,\s]', '', s)
    if s.startswith('(') and s.endswith(')'):
        negative = True
        s = s[1:-1]
    if negative:
        s = '-' + s
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None

def safe_decimal(s):
    try:
        return Decimal(str(s).replace(',',''))
    except:
        return None

def extract_po_line_items(text):
    """Extract PO line items from ORDER ITEMS section."""
    items = []
    li_start = re.search(r'(?:LINE|ORDER)\s+ITEMS\s*\n', text, re.I)
    if not li_start:
        return items
    section = text[li_start.end():]
    header_end = re.search(r'Amount\s*\n', section, re.I)
    if header_end:
        section = section[header_end.end():]
    lines = section.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if re.match(r'^\d+$', line) and int(line) < 100:
            line_num = int(line)
            fields = []
            j = i + 1
            while j < len(lines) and len(fields) < 6:
                val = lines[j].strip()
                if val:
                    if re.match(r'^\d+$', val) and int(val) < 100:
                        next_num = int(val)
                        if next_num == line_num + 1:
                            break
                    fields.append(val)
                j += 1
                if j < len(lines) and re.match(r'^\d+$', lines[j].strip()):
                    try:
                        next_num = int(lines[j].strip())
                        if next_num == line_num + 1 and next_num < 100:
                            break
                    except ValueError:
                        pass

            if len(fields) >= 4:
                desc = fields[0]
                hsn = fields[1] if re.match(r'^\d{4,8}$', fields[1]) else ""
                offset = 2 if hsn else 1
                qty = safe_decimal(fields[offset]) if offset < len(fields) else None
                unit = fields[offset + 1] if offset + 1 < len(fields) and not fields[offset + 1].startswith('I') else ""
                rate_idx = offset + (2 if unit else 1)
                rate = _clean_amount(fields[rate_idx]) if rate_idx < len(fields) else None
                amt_idx = rate_idx + 1
                amt = _clean_amount(fields[amt_idx]) if amt_idx < len(fields) else None

                items.append({
                    'line_num': line_num,
                    'description': desc,
                    'hsn_sac': hsn,
                    'quantity': qty,
                    'unit': unit,
                    'unit_rate': rate,
                    'amount': amt,
                })
            i = j
            continue
        if 'Subtotal' in line or 'This invoice has been' in line or 'accordance with' in line:
            break
        i += 1
    return items


with open('data/split_docs/document_splits.json') as f:
    docs = json.load(f)

pdf = fitz.open('data/input/gauntlet.pdf')
po_docs = [d for d in docs if d['doc_type'] == 'purchase_order']

total_items = 0
po_with_items = 0
po_no_items = 0
for d in po_docs:
    ps, pe = d['page_start'], d['page_end']
    text = ''
    for p in range(ps-1, pe):
        text += pdf[p].get_text() + '\n'
    
    # Check for PO number
    po_match = re.search(r'(PO-\d{4}-\d+)', text)
    if not po_match:
        continue
    
    po_num = po_match.group(1)
    items = extract_po_line_items(text)
    
    if items:
        total_items += len(items)
        po_with_items += 1
        if po_with_items <= 3:
            print(f'{po_num}: {len(items)} items')
            for li in items:
                print(f'  #{li["line_num"]} {li["description"]} qty={li["quantity"]} rate={li["unit_rate"]} amt={li["amount"]} hsn={li["hsn_sac"]}')
    else:
        po_no_items += 1
        if po_no_items <= 5:
            # Debug: show what the text looks like
            idx = text.find('ORDER ITEMS')
            if idx == -1:
                idx = text.find('LINE ITEMS')
            if idx >= 0:
                print(f'{po_num}: 0 items, section text: {repr(text[idx:idx+200])}')
            else:
                print(f'{po_num}: 0 items, no ORDER/LINE ITEMS section found')

print(f'\nPOs with items: {po_with_items}/{len(po_docs)}, total items: {total_items}')
print(f'POs without items: {po_no_items}')
pdf.close()
