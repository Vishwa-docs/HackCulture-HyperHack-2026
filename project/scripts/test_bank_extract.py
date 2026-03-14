"""Test bank statement extraction."""
import fitz, json, sys, re
from decimal import Decimal, InvalidOperation

def _clean_amount(s):
    if not s or s.strip() in ("", "-", "None", "null"):
        return None
    s = s.strip()
    negative = s.startswith('-')
    if negative:
        s = s[1:]
    s = re.sub(r'^[I₹$€£\s]+', '', s)
    s = re.sub(r'[,\s]', '', s)
    if negative:
        s = '-' + s
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None

def _find_field_newline(text, label):
    pattern = re.compile(rf'{re.escape(label)}\s*[:#]?\s*\n\s*(.+?)(?:\n|$)', re.I | re.MULTILINE)
    m = pattern.search(text)
    if m:
        return m.group(1).strip()
    pattern2 = re.compile(rf'{re.escape(label)}\s*[:#]?\s*(.+?)(?:\n|$)', re.I | re.MULTILINE)
    m = pattern2.search(text)
    if m:
        val = m.group(1).strip()
        if val and val != label:
            return val
    return ""

with open('data/split_docs/document_splits.json') as f:
    docs = json.load(f)

pdf = fitz.open('data/input/gauntlet.pdf')
bs_docs = [d for d in docs if d['doc_type'] == 'bank_statement']

bal_found = 0
bal_missing = 0
txn_counts = []
for d in bs_docs:
    ps, pe = d['page_start'], d['page_end']
    text = ''
    for p in range(ps-1, pe):
        text += pdf[p].get_text() + '\n'
    
    stmt_match = re.search(r'(BS-\d{4}-\d+)', text)
    stmt_id = stmt_match.group(1) if stmt_match else "?"
    
    # Try opening balance
    opening_str = re.search(r'Opening\s+Balance\s*[:#]?\s*(-?[I₹]?[\d,]+\.?\d*)', text, re.I)
    if not opening_str:
        opening_str2 = _find_field_newline(text, "Opening Balance")
        opening_bal = _clean_amount(opening_str2)
    else:
        opening_bal = _clean_amount(opening_str.group(1))
    
    # Try closing balance
    closing_str = re.search(r'Closing\s+Balance\s*[:#]?\s*(-?[I₹]?[\d,]+\.?\d*)', text, re.I)
    if not closing_str:
        closing_str2 = _find_field_newline(text, "Closing Balance")
        closing_bal = _clean_amount(closing_str2)
    else:
        closing_bal = _clean_amount(closing_str.group(1))
    
    # Count transactions
    txn_dates = re.findall(r'^\d{1,2}/\d{1,2}/\d{4}$', text, re.MULTILINE)
    
    if opening_bal is not None:
        bal_found += 1
    else:
        bal_missing += 1
        if bal_missing <= 5:
            # Show the area around "Opening" or "Balance"
            idx = text.find('Opening Balance')
            if idx >= 0:
                print(f'{stmt_id}: Opening Balance found but not parsed: {repr(text[idx:idx+100])}')
            else:
                print(f'{stmt_id}: No "Opening Balance" text found at all')
                # Show first 300 chars
                print(f'  First 300 chars: {text[:300]}')
    
    if bal_found <= 3:
        print(f'{stmt_id}: opening={opening_bal}, closing={closing_bal}, txn_dates={len(txn_dates)}')

print(f'\nBank statements with opening bal: {bal_found}/{len(bs_docs)}')
print(f'Missing: {bal_missing}')
pdf.close()
