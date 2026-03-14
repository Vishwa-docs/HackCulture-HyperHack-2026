#!/usr/bin/env python3
"""
NEEDLE FINDER - Complete end-to-end detection pipeline.
Reads extracted data, runs all 20 detectors, outputs submission.json.
"""
import json
import re
import sys
from collections import defaultdict, Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent.parent
DATA = BASE / "data"

# Known category counts from challenge briefing
CATEGORY_COUNTS = {
    "arithmetic_error": 12,
    "billing_typo": 4,
    "duplicate_line_item": 4,
    "invalid_date": 10,
    "wrong_tax_rate": 10,
    "po_invoice_mismatch": 15,
    "vendor_name_typo": 10,
    "double_payment": 10,
    "ifsc_mismatch": 5,
    "duplicate_expense": 10,
    "date_cascade": 5,
    "gstin_state_mismatch": 5,
    "quantity_accumulation": 35,
    "price_escalation": 10,
    "balance_drift": 15,
    "circular_reference": 8,
    "triple_expense_claim": 10,
    "employee_id_collision": 7,
    "fake_vendor": 10,
    "phantom_po_reference": 5,
}

#####################################################################
# UTILITIES
#####################################################################

def dec(val):
    """Parse value to Decimal, handling Indian currency format."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    s = str(val).strip()
    # Remove currency symbols (I = ₹ in this dataset)
    s = re.sub(r'^[I₹$€£\s]+', '', s)
    s = s.replace(',', '')
    # Handle parenthetical negatives
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

def fmt(val, places=2):
    """Format Decimal to string."""
    if val is None:
        return ""
    q = '0.' + '0' * places
    return str(val.quantize(Decimal(q), rounding=ROUND_HALF_UP))

def money_eq(a, b, tol=Decimal("0.02")):
    if a is None or b is None:
        return False
    return abs(a - b) <= tol

def normalize_ref(ref):
    """Normalize a document reference."""
    return re.sub(r'\s+', '', str(ref).strip().upper())

def parse_date(s):
    """Parse date string to date object."""
    s = str(s).strip()
    if not s:
        return None
    for fmt_str in ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d",
                    "%d/%m/%y", "%d-%m-%y", "%d %b %Y", "%d %B %Y"]:
        try:
            return datetime.strptime(s, fmt_str).date()
        except ValueError:
            continue
    return None

def validate_date(s):
    """Check if date string represents an impossible date. Returns (is_valid, reason)."""
    s = str(s).strip()
    if not s:
        return True, None
    
    # Try dd/mm/yyyy or dd-mm-yyyy
    m = re.match(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})', s)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        if month < 1 or month > 12:
            return False, f"Invalid month {month}"
        if day < 1 or day == 0:
            return False, f"Invalid day {day}"
        
        days_in_month = {1:31, 2:28, 3:31, 4:30, 5:31, 6:30,
                         7:31, 8:31, 9:30, 10:31, 11:30, 12:31}
        if month == 2 and ((year % 4 == 0 and year % 100 != 0) or year % 400 == 0):
            max_day = 29
        else:
            max_day = days_in_month.get(month, 31)
        
        if day > max_day:
            return False, f"Day {day} exceeds max {max_day} for month {month}/{year}"
        return True, None
    
    # yyyy-mm-dd
    m = re.match(r'(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})', s)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if month < 1 or month > 12:
            return False, f"Invalid month {month}"
        if day < 1:
            return False, f"Invalid day {day}"
        days_in_month = {1:31, 2:28, 3:31, 4:30, 5:31, 6:30,
                         7:31, 8:31, 9:30, 10:31, 11:30, 12:31}
        if month == 2 and ((year % 4 == 0 and year % 100 != 0) or year % 400 == 0):
            max_day = 29
        else:
            max_day = days_in_month.get(month, 31)
        if day > max_day:
            return False, f"Day {day} exceeds max {max_day} for month {month}/{year}"
        return True, None
    
    return True, None

def extract_po_line_items(raw_text):
    """Extract line items from PO raw text."""
    items = []
    if not raw_text:
        return items
    
    text = raw_text
    # Find ORDER ITEMS section
    start_idx = text.upper().find('ORDER ITEMS')
    if start_idx == -1:
        return items
    
    section = text[start_idx:]
    lines = section.split('\n')
    
    i = 0
    # Skip header lines
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#') or line == 'Amount' or 'Description' in line:
            i += 1
            continue
        if re.match(r'^\d+$', line):
            break
        i += 1
    
    # Parse items: line_num, description, hsn, qty, unit, rate, amount
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith('Subtotal') or line.startswith('GST') or line.startswith('TOTAL') or line.startswith('Authorized'):
            break
        
        # Check if this is a line number
        if re.match(r'^\d+$', line):
            line_num = int(line)
            # Read next fields
            fields = []
            i += 1
            while i < len(lines) and len(fields) < 6:
                f = lines[i].strip()
                if not f:
                    i += 1
                    continue
                if f.startswith('Subtotal') or f.startswith('GST') or f.startswith('TOTAL'):
                    break
                if re.match(r'^\d+$', f) and len(fields) >= 4:
                    break
                fields.append(f)
                i += 1
            
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
                        'line_num': line_num,
                        'description': desc,
                        'hsn_sac': hsn,
                        'quantity': str(qty_val) if qty_val else None,
                        'unit': unit,
                        'unit_rate': str(rate_val) if rate_val else None,
                        'amount': str(amount_val) if amount_val else None,
                    })
                except (IndexError, TypeError):
                    pass
            continue
        i += 1
    
    return items

def extract_bank_opening_balance(raw_text):
    """Extract opening balance from bank statement raw text."""
    if not raw_text:
        return None
    m = re.search(r'Opening Balance:\s*\n?\s*(-?I?[₹I]?[\d,]+\.?\d*)', raw_text, re.IGNORECASE)
    if m:
        return dec(m.group(1))
    return None

def extract_bank_closing_balance(raw_text):
    """Extract closing balance from bank statement raw text."""
    if not raw_text:
        return None
    m = re.search(r'Closing Balance:\s*\n?\s*(-?I?[₹I]?[\d,]+\.?\d*)', raw_text, re.IGNORECASE)
    if m:
        return dec(m.group(1))
    return None


#####################################################################
# GST STATE CODE MAP
#####################################################################
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

# Reverse map: state name -> expected code(s)
STATE_TO_CODE = {}
for code, state in GST_STATE_CODES.items():
    state_lower = state.lower()
    if state_lower not in STATE_TO_CODE:
        STATE_TO_CODE[state_lower] = []
    STATE_TO_CODE[state_lower].append(code)
# Add aliases
STATE_TO_CODE["new delhi"] = ["07"]
STATE_TO_CODE["nct of delhi"] = ["07"]

# HSN/SAC to expected GST rate
HSN_GST_RATES = {
    # Freight/transport SAC codes
    "996511": 5, "996512": 5, "9965": 5,
    # IT services
    "998314": 18, "998313": 18, "9983": 18,
    # Consulting
    "998412": 18, "9984": 18,
    # Legal
    "998211": 18,
    # Training
    "998521": 18,
    # Hotel/accommodation
    "996311": 18,
    # Courier
    "996812": 18,
    # Printing
    "998912": 12,
    # Manpower
    "998512": 18,
    # Security
    "998513": 18,
    # Software
    "994036": 18, "85234920": 18,
}

#####################################################################
# LOAD DATA
#####################################################################

def load_data():
    """Load all extracted data."""
    with open(DATA / "extracted/all_extracted.json") as f:
        d = json.load(f)
    with open(DATA / "extracted/vendor_master.json") as f:
        vendors = json.load(f)
    
    invoices = d['invoices']
    pos = d['pos']
    bank_stmts = d['bank_statements']
    expense_reports = d['expense_reports']
    credit_debit_notes = d['credit_debit_notes']
    
    # Fix PO line items from raw text
    fixed_po_count = 0
    for po in pos:
        if not po.get('line_items') and po.get('raw_text'):
            li = extract_po_line_items(po['raw_text'])
            if li:
                po['line_items'] = li
                fixed_po_count += 1
    print(f"Fixed PO line items for {fixed_po_count} POs")
    
    # Filter out filler documents misclassified as POs (FIL-, TC- prefixes)
    real_pos = [po for po in pos if str(po.get('po_number', '')).startswith('PO-')]
    print(f"Filtered POs: {len(pos)} -> {len(real_pos)} (removed {len(pos) - len(real_pos)} filler docs)")
    pos = real_pos

    # Fix bank statement opening/closing balances from raw text
    fixed_bs_count = 0
    for bs in bank_stmts:
        if not bs.get('opening_balance') and bs.get('raw_text'):
            ob = extract_bank_opening_balance(bs['raw_text'])
            if ob is not None:
                bs['opening_balance'] = str(ob)
                fixed_bs_count += 1
        if not bs.get('closing_balance') and bs.get('raw_text'):
            cb = extract_bank_closing_balance(bs['raw_text'])
            if cb is not None:
                bs['closing_balance'] = str(cb)
    print(f"Fixed bank statement opening balances for {fixed_bs_count} statements")
    
    return invoices, pos, bank_stmts, expense_reports, credit_debit_notes, vendors

#####################################################################
# DETECTORS
#####################################################################

def detect_arithmetic_error(invoices):
    """Detect arithmetic errors in invoices."""
    findings = []
    for inv in invoices:
        inv_num = inv.get('invoice_number', '')
        pages = inv.get('source_pages', [])
        line_items = inv.get('line_items', [])
        
        # Check each line item: qty * rate = amount (HIGHEST CONFIDENCE)
        for li in line_items:
            qty = dec(li.get('quantity'))
            rate = dec(li.get('unit_rate'))
            amount = dec(li.get('amount'))
            
            if qty is not None and rate is not None and amount is not None and qty > 0 and rate > 0:
                expected = (qty * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                diff = abs(expected - amount)
                if diff > Decimal("1.00") and diff / expected > Decimal("0.001"):
                    findings.append({
                        'category': 'arithmetic_error',
                        'pages': pages,
                        'document_refs': [inv_num],
                        'description': f"Line {li.get('line_num','?')}: {qty} x {fmt(rate)} = {fmt(expected)}, but shows {fmt(amount)}",
                        'reported_value': fmt(amount),
                        'correct_value': fmt(expected),
                        'confidence': 0.97,
                    })
        
        # Check subtotal = sum of line item amounts
        raw_text = inv.get('raw_text', '')
        real_subtotal, real_cgst, real_sgst, real_grand_total = parse_invoice_tax_summary(raw_text)
        
        if real_subtotal is not None and line_items:
            amounts = [dec(li.get('amount')) for li in line_items]
            amounts = [a for a in amounts if a is not None]
            if amounts:
                expected_sub = sum(amounts, Decimal("0"))
                diff = abs(expected_sub - real_subtotal)
                # Cap diff to filter parse artifacts - planted errors are ~₹1000
                if Decimal("1.00") < diff < Decimal("50000") and diff / real_subtotal > Decimal("0.001"):
                    findings.append({
                        'category': 'arithmetic_error',
                        'pages': pages,
                        'document_refs': [inv_num],
                        'description': f"Subtotal should be {fmt(expected_sub)} (sum of line items), shows {fmt(real_subtotal)}",
                        'reported_value': fmt(real_subtotal),
                        'correct_value': fmt(expected_sub),
                        'confidence': 0.90 if diff < Decimal("5000") else 0.70,
                    })
        
        # Check grand_total = subtotal + cgst + sgst from raw text
        if real_subtotal and real_cgst and real_sgst and real_grand_total:
            expected_gt = real_subtotal + real_cgst + real_sgst
            diff = abs(expected_gt - real_grand_total)
            if Decimal("1.00") < diff < Decimal("50000"):
                findings.append({
                    'category': 'arithmetic_error',
                    'pages': pages,
                    'document_refs': [inv_num],
                    'description': f"Grand total should be {fmt(expected_gt)} (subtotal+CGST+SGST), shows {fmt(real_grand_total)}",
                    'reported_value': fmt(real_grand_total),
                    'correct_value': fmt(expected_gt),
                    'confidence': 0.91,
                })
    
    return findings


def detect_billing_typo(invoices):
    """Detect time-entry decimal confusion."""
    SUSPICIOUS = {
        Decimal("0.15"): Decimal("0.25"),
        Decimal("0.30"): Decimal("0.50"),
        Decimal("0.45"): Decimal("0.75"),
        Decimal("1.15"): Decimal("1.25"),
        Decimal("1.30"): Decimal("1.50"),
        Decimal("1.45"): Decimal("1.75"),
        Decimal("2.15"): Decimal("2.25"),
        Decimal("2.30"): Decimal("2.50"),
        Decimal("2.45"): Decimal("2.75"),
        Decimal("3.15"): Decimal("3.25"),
        Decimal("3.30"): Decimal("3.50"),
        Decimal("3.45"): Decimal("3.75"),
        Decimal("4.15"): Decimal("4.25"),
        Decimal("4.30"): Decimal("4.50"),
        Decimal("4.45"): Decimal("4.75"),
        Decimal("5.15"): Decimal("5.25"),
        Decimal("5.30"): Decimal("5.50"),
        Decimal("5.45"): Decimal("5.75"),
        Decimal("6.15"): Decimal("6.25"),
        Decimal("6.30"): Decimal("6.50"),
        Decimal("6.45"): Decimal("6.75"),
        Decimal("7.15"): Decimal("7.25"),
        Decimal("7.30"): Decimal("7.50"),
        Decimal("7.45"): Decimal("7.75"),
        Decimal("8.15"): Decimal("8.25"),
        Decimal("8.30"): Decimal("8.50"),
        Decimal("8.45"): Decimal("8.75"),
    }
    
    findings = []
    for inv in invoices:
        inv_num = inv.get('invoice_number', '')
        pages = inv.get('source_pages', [])
        
        for li in inv.get('line_items', []):
            qty = dec(li.get('quantity'))
            rate = dec(li.get('unit_rate'))
            amount = dec(li.get('amount'))
            unit = str(li.get('unit', '')).lower()
            
            if qty is None or rate is None or amount is None:
                continue
            
            if qty in SUSPICIOUS:
                correct_qty = SUSPICIOUS[qty]
                wrong_amount = (qty * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                correct_amount = (correct_qty * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                
                # Check if amount matches the WRONG interpretation
                if money_eq(amount, wrong_amount, Decimal("0.10")):
                    findings.append({
                        'category': 'billing_typo',
                        'pages': pages,
                        'document_refs': [inv_num],
                        'description': f"Line {li.get('line_num','?')}: qty {qty} looks like time HH:MM={correct_qty} decimal hrs. Amount {fmt(amount)} should be {fmt(correct_amount)}",
                        'reported_value': fmt(amount),
                        'correct_value': fmt(correct_amount),
                        'confidence': 0.88,
                    })
    
    return findings


def detect_duplicate_line_item(invoices):
    """Detect exact duplicate line items within same invoice."""
    findings = []
    for inv in invoices:
        inv_num = inv.get('invoice_number', '')
        pages = inv.get('source_pages', [])
        line_items = inv.get('line_items', [])
        
        if len(line_items) < 2:
            continue
        
        # Strategy 1: exact match on desc+amount+hsn
        sigs = defaultdict(list)
        for li in line_items:
            desc = str(li.get('description', '')).strip().lower()
            amount = str(li.get('amount', ''))
            hsn = str(li.get('hsn_sac', '')).strip()
            sig = f"{desc}|{amount}|{hsn}"
            sigs[sig].append(li)
        
        for sig, items in sigs.items():
            if len(items) > 1:
                amount = dec(items[0].get('amount'))
                dup_count = len(items) - 1
                desc = items[0].get('description', 'unknown')
                inflation = fmt(amount * dup_count) if amount else "unknown"
                
                findings.append({
                    'category': 'duplicate_line_item',
                    'pages': pages,
                    'document_refs': [inv_num],
                    'description': f"Line item '{desc}' duplicated {dup_count} time(s), inflating by {inflation}",
                    'reported_value': f"{len(items)} occurrences",
                    'correct_value': "1 occurrence",
                    'confidence': 0.93,
                })
        
        # Strategy 2: match on just description + amount (ignoring HSN)
        sigs2 = defaultdict(list)
        for li in line_items:
            desc = str(li.get('description', '')).strip().lower()
            amount = str(li.get('amount', ''))
            sig = f"{desc}|{amount}"
            sigs2[sig].append(li)
        
        for sig, items in sigs2.items():
            if len(items) > 1:
                # Check we haven't already reported this
                desc = str(items[0].get('description', '')).strip().lower()
                already_found = any(desc in f.get('description','').lower() for f in findings if f.get('document_refs') == [inv_num])
                if already_found:
                    continue
                
                amount = dec(items[0].get('amount'))
                dup_count = len(items) - 1
                inflation = fmt(amount * dup_count) if amount else "unknown"
                
                findings.append({
                    'category': 'duplicate_line_item',
                    'pages': pages,
                    'document_refs': [inv_num],
                    'description': f"Line item '{items[0].get('description', 'unknown')}' appears {len(items)} times, inflating by {inflation}",
                    'reported_value': f"{len(items)} occurrences",
                    'correct_value': "1 occurrence",
                    'confidence': 0.90,
                })
        
        # Strategy 3: match on desc+qty (amount may differ due to the error itself)
        sigs3 = defaultdict(list)
        for li in line_items:
            desc = str(li.get('description', '')).strip().lower()
            qty = str(li.get('quantity', ''))
            hsn = str(li.get('hsn_sac', '')).strip()
            if desc and qty and hsn and len(desc) > 10:
                sig = f"{desc}|{qty}|{hsn}"
                sigs3[sig].append(li)
        
        for sig, items in sigs3.items():
            if len(items) > 1:
                desc = str(items[0].get('description', '')).strip().lower()
                already_found = any(desc in f.get('description','').lower() for f in findings if f.get('document_refs') == [inv_num])
                if already_found:
                    continue
                
                amount = dec(items[0].get('amount'))
                dup_count = len(items) - 1
                inflation = fmt(amount * dup_count) if amount else "unknown"
                
                findings.append({
                    'category': 'duplicate_line_item',
                    'pages': pages,
                    'document_refs': [inv_num],
                    'description': f"Line item '{items[0].get('description', 'unknown')}' appears {len(items)} times with same qty+HSN, inflating by {inflation}",
                    'reported_value': f"{len(items)} occurrences",
                    'correct_value': "1 occurrence",
                    'confidence': 0.85,
                })
    
    return findings


def detect_invalid_date(invoices, pos, expense_reports):
    """Detect impossible dates."""
    findings = []
    seen = set()
    
    def check_date(date_str, doc_ref, pages, field_name):
        if not date_str or not str(date_str).strip():
            return
        key = f"{doc_ref}|{date_str}"
        if key in seen:
            return
        
        is_valid, reason = validate_date(date_str)
        if not is_valid:
            seen.add(key)
            findings.append({
                'category': 'invalid_date',
                'pages': pages,
                'document_refs': [doc_ref],
                'description': f"Invalid {field_name}: '{date_str}' - {reason}",
                'reported_value': str(date_str),
                'correct_value': "",
                'confidence': 0.95,
            })
    
    for inv in invoices:
        ref = inv.get('invoice_number', '')
        pages = inv.get('source_pages', [])
        check_date(inv.get('invoice_date'), ref, pages, 'invoice_date')
        check_date(inv.get('due_date'), ref, pages, 'due_date')
    
    for po in pos:
        ref = po.get('po_number', '')
        pages = po.get('source_pages', [])
        check_date(po.get('po_date'), ref, pages, 'po_date')
        check_date(po.get('delivery_date'), ref, pages, 'delivery_date')
    
    for er in expense_reports:
        ref = er.get('report_id', '')
        pages = er.get('source_pages', [])
        for el in er.get('expense_lines', []):
            check_date(el.get('date'), ref, pages, 'expense_date')
    
    return findings


def parse_invoice_tax_summary(raw_text):
    """Parse the subtotal/CGST/SGST/Grand Total from invoice raw text.
    
    The PDF layout interleaves: the number BEFORE 'Subtotal:' is the actual subtotal,
    the number BETWEEN 'Subtotal:' and 'CGST:' is CGST,
    the number BETWEEN 'CGST:' and 'SGST:' is SGST,
    the number BETWEEN 'SGST:' and 'GRAND TOTAL:' is the grand total.
    
    Alternatively: Subtotal is the sum of line item amounts shown before the summary.
    """
    if not raw_text:
        return None, None, None, None
    
    # Find all amounts in the summary section
    lines = raw_text.split('\n')
    
    # Find the summary section
    subtotal_val = None
    cgst_val = None
    sgst_val = None
    igst_val = None
    grand_total_val = None
    
    amount_pattern = re.compile(r'-?I?[\d,]+\.\d{2}')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Look for Subtotal label
        if line.upper() in ('SUBTOTAL:', 'SUB TOTAL:', 'SUBTOTAL'):
            # The amount BEFORE this label is the real subtotal
            # Look backwards for the previous number
            for j in range(i-1, max(0, i-5), -1):
                prev_line = lines[j].strip()
                m = amount_pattern.search(prev_line)
                if m:
                    subtotal_val = dec(m.group())
                    break
            
            # The number AFTER this label is CGST (in the interleaved layout)
            for j in range(i+1, min(len(lines), i+3)):
                next_line = lines[j].strip()
                m = amount_pattern.search(next_line)
                if m:
                    cgst_val = dec(m.group())
                    break
        
        elif line.upper() in ('CGST:', 'CGST'):
            for j in range(i+1, min(len(lines), i+3)):
                next_line = lines[j].strip()
                m = amount_pattern.search(next_line)
                if m:
                    sgst_val = dec(m.group())
                    break
        
        elif line.upper() in ('SGST:', 'SGST'):
            for j in range(i+1, min(len(lines), i+3)):
                next_line = lines[j].strip()
                m = amount_pattern.search(next_line)
                if m:
                    grand_total_val = dec(m.group())
                    break
        
        elif line.upper() in ('IGST:', 'IGST'):
            for j in range(i+1, min(len(lines), i+3)):
                next_line = lines[j].strip()
                m = amount_pattern.search(next_line)
                if m:
                    igst_val = dec(m.group())
                    break
        
        elif 'GRAND TOTAL' in line.upper():
            # If we already have grand_total from SGST section, verify
            for j in range(i+1, min(len(lines), i+3)):
                next_line = lines[j].strip()
                m = amount_pattern.search(next_line)
                if m:
                    if grand_total_val is None:
                        grand_total_val = dec(m.group())
                    break
        
        i += 1
    
    return subtotal_val, cgst_val, sgst_val or igst_val, grand_total_val


def detect_wrong_tax_rate(invoices):
    """Detect GST rate inconsistent with HSN/SAC code."""
    findings = []
    
    # Standard GST rates for common HSN/SAC
    HSN_EXPECTED_RATE = {
        # 5% items
        "996511": 5, "996512": 5, "9965": 5,
        # 12% items
        "998912": 12, "4820": 12,
        # 18% items (most services)
        "998314": 18, "998313": 18, "9983": 18,
        "998412": 18, "9984": 18,
        "998211": 18, "998521": 18,
        "996311": 18, "996812": 18,
        "998512": 18, "998513": 18,
        "994036": 18, "85234920": 18,
        "997212": 18, "997211": 18,
        "998399": 18,
    }
    
    for inv in invoices:
        inv_num = inv.get('invoice_number', '')
        pages = inv.get('source_pages', [])
        raw_text = inv.get('raw_text', '')
        
        # Parse actual tax summary from raw text
        real_subtotal, cgst, sgst, grand_total = parse_invoice_tax_summary(raw_text)
        
        if real_subtotal is None or real_subtotal <= 0:
            continue
        
        total_tax = Decimal("0")
        if cgst:
            total_tax += cgst
        if sgst:
            total_tax += sgst
        
        if total_tax > 0:
            effective_rate = (total_tax / real_subtotal * 100).quantize(Decimal("0.1"))
        else:
            continue
        
        # Check what rate the HSN codes expect
        line_items = inv.get('line_items', [])
        hsn_codes = set()
        for li in line_items:
            hsn = str(li.get('hsn_sac', '')).strip()
            if hsn:
                hsn_codes.add(hsn)
        
        # Determine expected rate from HSN codes
        expected_rates = set()
        for hsn in hsn_codes:
            if hsn in HSN_EXPECTED_RATE:
                expected_rates.add(HSN_EXPECTED_RATE[hsn])
            else:
                for prefix_len in [6, 4]:
                    prefix = hsn[:prefix_len]
                    if prefix in HSN_EXPECTED_RATE:
                        expected_rates.add(HSN_EXPECTED_RATE[prefix])
                        break
        
        if not expected_rates:
            continue
        
        # If all HSN codes point to the same expected rate
        if len(expected_rates) == 1:
            expected = Decimal(str(expected_rates.pop()))
            # Compare: effective_rate should differ by >3% to be a clear mismatch
            deviation = abs(effective_rate - expected)
            if deviation > Decimal("3"):
                findings.append({
                    'category': 'wrong_tax_rate',
                    'pages': pages,
                    'document_refs': [inv_num],
                    'description': f"GST rate is {effective_rate}% but HSN codes {hsn_codes} expect {expected}%",
                    'reported_value': f"{effective_rate}%",
                    'correct_value': f"{expected}%",
                    'confidence': min(0.95, 0.70 + float(deviation) / 30),
                })
    
    return findings


def detect_po_invoice_mismatch(invoices, pos):
    """Detect invoice qty or rate differing from linked PO.
    Uses HSN code as primary matching criterion (very reliable)."""
    findings = []
    
    # Build PO lookup
    po_lookup = {}
    for po in pos:
        pn = po.get('po_number', '').strip()
        if pn:
            po_lookup[normalize_ref(pn)] = po
            po_lookup[pn] = po
    
    for inv in invoices:
        inv_num = inv.get('invoice_number', '')
        po_ref = inv.get('po_number', '').strip()
        pages = inv.get('source_pages', [])
        
        if not po_ref:
            continue
        
        po = po_lookup.get(normalize_ref(po_ref)) or po_lookup.get(po_ref)
        if not po or not po.get('line_items'):
            continue
        
        inv_items = inv.get('line_items', [])
        po_items = po.get('line_items', [])
        
        for inv_li in inv_items:
            inv_desc = str(inv_li.get('description', '')).strip().lower()
            inv_hsn = str(inv_li.get('hsn_sac', '')).strip()
            inv_qty = dec(inv_li.get('quantity'))
            inv_rate = dec(inv_li.get('unit_rate'))
            
            if not inv_desc:
                continue
            
            # Find best matching PO line item - prefer HSN match
            best_po_li = None
            best_match_quality = 0  # 0=none, 1=desc, 2=hsn
            best_overlap = 0
            
            for po_li in po_items:
                po_hsn = str(po_li.get('hsn_sac', '')).strip()
                po_desc = str(po_li.get('description', '')).strip().lower()
                
                # HSN match (strongest signal)
                if inv_hsn and po_hsn and inv_hsn == po_hsn:
                    if best_match_quality < 2:
                        best_match_quality = 2
                        best_po_li = po_li
                        best_overlap = 1.0
                    continue
                
                # Description match (fallback)
                if not po_desc:
                    continue
                inv_words = set(inv_desc.split())
                po_words = set(po_desc.split())
                if len(inv_words) < 2 or len(po_words) < 2:
                    continue
                overlap = len(inv_words & po_words) / max(len(inv_words), len(po_words))
                if overlap >= 0.60 and best_match_quality < 2 and overlap > best_overlap:
                    best_match_quality = 1
                    best_po_li = po_li
                    best_overlap = overlap
            
            if best_po_li is None:
                continue
            
            po_qty = dec(best_po_li.get('quantity'))
            po_rate = dec(best_po_li.get('unit_rate'))
            
            # Confidence based on match quality
            base_conf = 0.85 if best_match_quality == 2 else 0.70
            
            # Check qty mismatch
            if inv_qty is not None and po_qty is not None and po_qty > 0:
                pct_diff = abs(inv_qty - po_qty) / po_qty
                if pct_diff > Decimal("0.05") and not money_eq(inv_qty, po_qty, Decimal("0.5")):
                    findings.append({
                        'category': 'po_invoice_mismatch',
                        'pages': pages,
                        'document_refs': [inv_num, po.get('po_number', '')],
                        'description': f"Qty mismatch for '{inv_li.get('description','')}': invoice={inv_qty}, PO={po_qty}",
                        'reported_value': str(inv_qty),
                        'correct_value': str(po_qty),
                        'confidence': min(0.95, base_conf + float(pct_diff) * 0.2),
                    })
            
            # Check rate mismatch
            if inv_rate is not None and po_rate is not None and po_rate > 0:
                pct_diff = abs(inv_rate - po_rate) / po_rate
                if pct_diff > Decimal("0.05") and not money_eq(inv_rate, po_rate, Decimal("1.00")):
                    findings.append({
                        'category': 'po_invoice_mismatch',
                        'pages': pages,
                        'document_refs': [inv_num, po.get('po_number', '')],
                        'description': f"Rate mismatch for '{inv_li.get('description','')}': invoice={fmt(inv_rate)}, PO={fmt(po_rate)}",
                        'reported_value': fmt(inv_rate),
                        'correct_value': fmt(po_rate),
                        'confidence': min(0.95, base_conf + float(pct_diff) * 0.2),
                    })
    
    return findings


def detect_vendor_name_typo(invoices, vendors):
    """Detect invoice vendor name misspelled vs Vendor Master."""
    from difflib import SequenceMatcher
    
    findings = []
    vendor_names = {v['canonical_name'].lower(): v for v in vendors}
    vendor_raw_names = {v['raw_name'].lower(): v for v in vendors}
    
    for inv in invoices:
        inv_num = inv.get('invoice_number', '')
        vendor_raw = inv.get('vendor_name_raw', '').strip()
        pages = inv.get('source_pages', [])
        
        if not vendor_raw:
            continue
        
        vname_lower = vendor_raw.lower()
        # Exact match - skip
        if vname_lower in vendor_names or vname_lower in vendor_raw_names:
            continue
        
        # Find best fuzzy match
        best_score = 0
        best_vendor = None
        for vn, v in vendor_names.items():
            score = SequenceMatcher(None, vname_lower, vn).ratio()
            if score > best_score:
                best_score = score
                best_vendor = v
        
        # Also check raw names
        for vn, v in vendor_raw_names.items():
            score = SequenceMatcher(None, vname_lower, vn).ratio()
            if score > best_score:
                best_score = score
                best_vendor = v
        
        if best_vendor and 0.70 <= best_score < 0.98:
            # This is a typo, not a fake vendor
            findings.append({
                'category': 'vendor_name_typo',
                'pages': pages,
                'document_refs': [inv_num],
                'description': f"Vendor '{vendor_raw}' is likely a typo of '{best_vendor['canonical_name']}' (similarity: {best_score:.0%})",
                'reported_value': vendor_raw,
                'correct_value': best_vendor['canonical_name'],
                'confidence': 0.70 + best_score * 0.25,
            })
    
    return findings


def detect_double_payment(bank_stmts):
    """Detect same payment in two different bank statement months."""
    findings = []
    
    all_txns = []
    for bs in bank_stmts:
        for txn in bs.get('transactions', []):
            txn_copy = dict(txn)
            txn_copy['_month'] = bs.get('statement_month', '')
            txn_copy['_stmt_id'] = bs.get('statement_id', '')
            txn_copy['_pages'] = bs.get('source_pages', [])
            all_txns.append(txn_copy)
    
    groups = defaultdict(list)
    for txn in all_txns:
        debit = dec(txn.get('debit'))
        if debit is None or debit <= 0:
            continue
        ref = str(txn.get('reference', '')).strip().upper()
        desc = str(txn.get('description', '')).strip().upper()[:40]
        has_ref = bool(ref)
        key = f"{debit}|{ref}" if ref else f"{debit}|{desc}"
        txn['_has_ref'] = has_ref
        groups[key].append(txn)
    
    for key, txns in groups.items():
        if len(txns) < 2:
            continue
        months = set(t['_month'] for t in txns)
        if len(months) < 2:
            continue
        
        amount = dec(txns[0].get('debit'))
        ref = txns[0].get('reference', '')
        has_ref = txns[0].get('_has_ref', False)
        pages = []
        stmt_refs = []
        for t in txns:
            pages.extend(t['_pages'])
            stmt_refs.append(t['_stmt_id'])
        
        # Higher confidence if matched by reference, lower if by description only
        conf = 0.88 if has_ref else 0.72
        
        findings.append({
            'category': 'double_payment',
            'pages': sorted(set(pages)),
            'document_refs': sorted(set(stmt_refs)),
            'description': f"Payment {fmt(amount)} (ref: {ref}) in {len(months)} different months",
            'reported_value': f"{fmt(amount)} x {len(txns)}",
            'correct_value': f"{fmt(amount)} x 1",
            'confidence': conf,
        })
    
    return findings


def detect_ifsc_mismatch(invoices, vendors):
    """Detect invoice bank IFSC differing from Vendor Master.
    
    Use outlier detection: find the majority IFSC per vendor across all invoices.
    Flag invoices whose IFSC differs from the vendor's majority IFSC AND the vendor master.
    """
    findings = []
    
    # Build vendor lookup by GSTIN and name
    vendor_by_gstin = {}
    vendor_by_name = {}
    for v in vendors:
        if v.get('gstin'):
            vendor_by_gstin[v['gstin'].upper()] = v
        vendor_by_name[v['canonical_name'].lower()] = v
        vendor_by_name[v['raw_name'].lower()] = v
    
    # First pass: build per-vendor IFSC frequency map
    vendor_ifsc_freq = defaultdict(lambda: defaultdict(list))  # vendor_id -> ifsc -> [inv_nums]
    
    for inv in invoices:
        inv_ifsc = inv.get('bank_ifsc', '').strip().upper()
        if not inv_ifsc:
            continue
        
        gstin = inv.get('gstin_vendor', '').strip().upper()
        vendor_raw = inv.get('vendor_name_raw', '')
        
        vendor = None
        if gstin and gstin in vendor_by_gstin:
            vendor = vendor_by_gstin[gstin]
        if not vendor and vendor_raw:
            vendor = vendor_by_name.get(vendor_raw.lower())
        
        if vendor:
            vid = vendor.get('vendor_id', '')
            vendor_ifsc_freq[vid][inv_ifsc].append(inv)
    
    # Second pass: find outlier IFSCs (different from majority)
    for vid, ifsc_map in vendor_ifsc_freq.items():
        if len(ifsc_map) < 2:
            continue  # All invoices have same IFSC - no outlier
        
        # Find majority IFSC
        majority_ifsc = max(ifsc_map.keys(), key=lambda k: len(ifsc_map[k]))
        majority_count = len(ifsc_map[majority_ifsc])
        
        # Find the vendor for reporting
        vendor = None
        for v in vendors:
            if v.get('vendor_id') == vid:
                vendor = v
                break
        if not vendor:
            continue
        
        master_ifsc = vendor.get('ifsc', '').strip().upper()
        
        # Flag invoices with minority IFSC (outliers)
        for ifsc, inv_list in ifsc_map.items():
            if ifsc == majority_ifsc:
                continue  # Skip the majority - these are normal
            
            # This is an outlier IFSC - likely a planted error
            for inv in inv_list:
                inv_num = inv.get('invoice_number', '')
                pages = inv.get('source_pages', [])
                
                # High confidence: different bank code AND outlier
                bank_code_diff = ifsc[:4] != majority_ifsc[:4]
                conf = 0.98 if bank_code_diff else 0.85
                
                findings.append({
                    'category': 'ifsc_mismatch',
                    'pages': pages,
                    'document_refs': [inv_num],
                    'description': f"IFSC '{ifsc}' is outlier for {vendor['canonical_name']} (normal: '{majority_ifsc}', master: '{master_ifsc}')",
                    'reported_value': ifsc,
                    'correct_value': master_ifsc,
                    'confidence': conf,
                })
    
    return findings


def detect_duplicate_expense(expense_reports):
    """Detect same expense claimed in two different reports."""
    findings = []
    seen_pairs = set()
    
    all_expenses = []
    for er in expense_reports:
        for el in er.get('expense_lines', []):
            el_copy = dict(el)
            el_copy['_report_id'] = er.get('report_id', '')
            el_copy['_employee_id'] = er.get('employee_id', '')
            el_copy['_employee_name'] = er.get('employee_name', '')
            el_copy['_pages'] = er.get('source_pages', [])
            all_expenses.append(el_copy)
    
    # Strategy 1: Same amount + same description across ANY reports
    groups = defaultdict(list)
    for exp in all_expenses:
        amount = str(exp.get('amount', ''))
        desc = str(exp.get('description', '')).strip()
        key = f"{amount}|{desc}"
        groups[key].append(exp)
    
    for key, expenses in groups.items():
        if len(expenses) < 2:
            continue
        report_ids = sorted(set(e['_report_id'] for e in expenses))
        if len(report_ids) < 2:
            continue
        
        pair_key = tuple(report_ids)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        
        amount = dec(expenses[0].get('amount'))
        desc = expenses[0].get('description', 'unknown')
        pages = []
        for e in expenses:
            pages.extend(e['_pages'])
        
        findings.append({
            'category': 'duplicate_expense',
            'pages': sorted(set(pages)),
            'document_refs': report_ids,
            'description': f"Expense '{desc}' ({fmt(amount)}) claimed in {len(report_ids)} reports",
            'reported_value': f"{len(report_ids)} claims",
            'correct_value': "1 claim",
            'confidence': 0.83,
        })
    
    return findings


def detect_date_cascade(invoices, pos):
    """Detect invoice date before its own PO date."""
    findings = []
    
    po_lookup = {}
    for po in pos:
        pn = po.get('po_number', '').strip()
        if pn:
            po_lookup[normalize_ref(pn)] = po
            po_lookup[pn] = po
    
    for inv in invoices:
        inv_num = inv.get('invoice_number', '')
        po_ref = inv.get('po_number', '').strip()
        inv_date_str = inv.get('invoice_date', '')
        pages = inv.get('source_pages', [])
        
        if not po_ref or not inv_date_str:
            continue
        
        po = po_lookup.get(normalize_ref(po_ref)) or po_lookup.get(po_ref)
        if not po:
            continue
        
        po_date_str = po.get('po_date', '')
        if not po_date_str:
            continue
        
        inv_date = parse_date(inv_date_str)
        po_date = parse_date(po_date_str)
        
        if inv_date and po_date and inv_date < po_date:
            gap_days = (po_date - inv_date).days
            # Confidence proportional to gap - larger gaps are more clearly wrong
            conf = min(0.95, 0.70 + gap_days / 100)
            findings.append({
                'category': 'date_cascade',
                'pages': pages,
                'document_refs': [inv_num, po.get('po_number', '')],
                'description': f"Invoice date ({inv_date_str}) is {gap_days} days before PO date ({po_date_str})",
                'reported_value': inv_date_str,
                'correct_value': f"Should be on or after {po_date_str}",
                'confidence': conf,
            })
    
    return findings


def detect_gstin_state_mismatch(invoices, vendors):
    """Detect GSTIN state code mismatch - both vendor master and invoice GSTINs."""
    findings = []
    seen = set()
    
    # Check 1: Vendor master GSTIN vs vendor state
    for v in vendors:
        gstin = v.get('gstin', '').strip()
        state = v.get('state', '').strip()
        
        if len(gstin) < 2 or not state:
            continue
        
        gstin_code = gstin[:2]
        expected_state = GST_STATE_CODES.get(gstin_code, '')
        
        if expected_state:
            state_lower = state.lower()
            expected_lower = expected_state.lower()
            
            if state_lower != expected_lower:
                expected_codes = STATE_TO_CODE.get(state_lower, [])
                if gstin_code not in expected_codes:
                    key = v.get('vendor_id', '')
                    seen.add(key)
                    findings.append({
                        'category': 'gstin_state_mismatch',
                        'pages': v.get('source_pages', [3, 4]),
                        'document_refs': [v.get('vendor_id', '')],
                        'description': f"Vendor '{v['canonical_name']}': GSTIN {gstin} (state code {gstin_code} = {expected_state}) but registered state is {state}",
                        'reported_value': f"{gstin_code} ({expected_state})",
                        'correct_value': state,
                        'confidence': 0.90,
                    })
    
    # Check 2: Invoice GSTIN differs from vendor master GSTIN (different state code)
    vendor_by_name = {}
    for v in vendors:
        vendor_by_name[v['canonical_name'].lower()] = v
        vendor_by_name[v['raw_name'].lower()] = v
    vendor_by_gstin = {v['gstin'].upper(): v for v in vendors if v.get('gstin')}
    
    for inv in invoices:
        inv_gstin = inv.get('gstin_vendor', '').strip().upper()
        if not inv_gstin or len(inv_gstin) < 2:
            continue
        
        # If invoice GSTIN matches vendor master exactly, skip
        if inv_gstin in vendor_by_gstin:
            continue
        
        # Find vendor by exact name or fuzzy name match
        vendor_raw = inv.get('vendor_name_raw', '').strip().lower()
        vendor = vendor_by_name.get(vendor_raw)
        if not vendor:
            # Try fuzzy match
            from difflib import SequenceMatcher
            best_score = 0
            for vn, v in vendor_by_name.items():
                score = SequenceMatcher(None, vendor_raw, vn).ratio()
                if score > best_score:
                    best_score = score
                    vendor = v if score > 0.70 else None
        
        if not vendor:
            continue
        
        master_gstin = vendor.get('gstin', '').upper()
        if not master_gstin:
            continue
        
        # Compare state codes
        inv_code = inv_gstin[:2]
        master_code = master_gstin[:2]
        if inv_code != master_code:
            inv_num = inv.get('invoice_number', '')
            inv_state = GST_STATE_CODES.get(inv_code, inv_code)
            master_state = GST_STATE_CODES.get(master_code, master_code)
            findings.append({
                'category': 'gstin_state_mismatch',
                'pages': inv.get('source_pages', []),
                'document_refs': [inv_num, vendor.get('vendor_id', '')],
                'description': f"Invoice {inv_num} GSTIN {inv_gstin} (state: {inv_state}) but vendor master has {master_gstin} (state: {master_state})",
                'reported_value': f"{inv_code} ({inv_state})",
                'correct_value': f"{master_code} ({master_state})",
                'confidence': 0.92,
            })
    
    # Check 3: Invoice GSTIN state code vs vendor's registered state field
    for inv in invoices:
        inv_gstin = inv.get('gstin_vendor', '').strip().upper()
        if not inv_gstin or len(inv_gstin) < 2:
            continue
        
        inv_code = inv_gstin[:2]
        inv_state = GST_STATE_CODES.get(inv_code, '')
        if not inv_state:
            continue
        
        # Find vendor
        vendor_raw = inv.get('vendor_name_raw', '').strip().lower()
        vendor = vendor_by_name.get(vendor_raw)
        if not vendor:
            from difflib import SequenceMatcher
            best_score_3 = 0
            for vn, v in vendor_by_name.items():
                score = SequenceMatcher(None, vendor_raw, vn).ratio()
                if score > best_score_3:
                    best_score_3 = score
                    vendor = v if score > 0.70 else None
        
        if not vendor:
            continue
        
        vendor_state = vendor.get('state', '').strip()
        if not vendor_state:
            continue
        
        # Check if invoice GSTIN state matches vendor's registered state
        inv_state_lower = inv_state.lower()
        vendor_state_lower = vendor_state.lower()
        if inv_state_lower != vendor_state_lower:
            expected_codes = STATE_TO_CODE.get(vendor_state_lower, [])
            if inv_code not in expected_codes:
                inv_num = inv.get('invoice_number', '')
                # Avoid duplicates with Check 2
                already = any(f['document_refs'][0] == inv_num for f in findings if f.get('category') == 'gstin_state_mismatch')
                if not already:
                    findings.append({
                        'category': 'gstin_state_mismatch',
                        'pages': inv.get('source_pages', []),
                        'document_refs': [inv_num, vendor.get('vendor_id', '')],
                        'description': f"Invoice {inv_num} GSTIN state code {inv_code} ({inv_state}) but vendor registered in {vendor_state}",
                        'reported_value': f"{inv_code} ({inv_state})",
                        'correct_value': vendor_state,
                        'confidence': 0.88,
                    })
    
    return findings


def detect_quantity_accumulation(invoices, pos):
    """Detect cumulative invoiced qty exceeding PO qty by >20%."""
    findings = []
    
    # Build PO lookup with line items
    po_lookup = {}
    for po in pos:
        pn = po.get('po_number', '').strip()
        if pn and po.get('line_items'):
            po_lookup[normalize_ref(pn)] = po
    
    # Group invoices by PO
    po_invoices = defaultdict(list)
    for inv in invoices:
        po_ref = inv.get('po_number', '').strip()
        if po_ref:
            po_invoices[normalize_ref(po_ref)].append(inv)
    
    for po_ref, inv_list in po_invoices.items():
        if len(inv_list) < 2:
            continue
        
        po = po_lookup.get(po_ref)
        if not po:
            continue
        
        po_items = po.get('line_items', [])
        
        for po_li in po_items:
            po_desc = str(po_li.get('description', '')).strip().lower()
            po_qty = dec(po_li.get('quantity'))
            
            if not po_desc or po_qty is None or po_qty <= 0:
                continue
            
            # Sum matching invoice line items - use HSN matching (primary)
            po_hsn = str(po_li.get('hsn_sac', '')).strip()
            total_inv_qty = Decimal("0")
            matching_invs = []
            
            for inv in inv_list:
                for inv_li in inv.get('line_items', []):
                    inv_hsn = str(inv_li.get('hsn_sac', '')).strip()
                    inv_desc = str(inv_li.get('description', '')).strip().lower()
                    inv_qty = dec(inv_li.get('quantity'))
                    
                    if inv_qty is None:
                        continue
                    
                    matched = False
                    # HSN match (strongest)
                    if po_hsn and inv_hsn and po_hsn == inv_hsn:
                        matched = True
                    else:
                        # Fallback: description overlap
                        inv_words = set(inv_desc.split())
                        po_words = set(po_desc.split())
                        if len(inv_words) >= 2 and len(po_words) >= 2:
                            overlap = len(inv_words & po_words) / max(len(inv_words), len(po_words))
                            if overlap >= 0.70:
                                matched = True
                    
                    if matched:
                        total_inv_qty += inv_qty
                        matching_invs.append(inv)
            
            if total_inv_qty > po_qty * Decimal("1.20") and len(matching_invs) >= 2:
                excess_pct = float((total_inv_qty - po_qty) / po_qty)
                all_refs = [po.get('po_number', '')] + [i.get('invoice_number', '') for i in matching_invs]
                all_pages = []
                for i in matching_invs:
                    all_pages.extend(i.get('source_pages', []))
                
                findings.append({
                    'category': 'quantity_accumulation',
                    'pages': sorted(set(all_pages)),
                    'document_refs': list(dict.fromkeys(all_refs)),
                    'description': f"Cumulative qty {total_inv_qty} across {len(matching_invs)} invoices exceeds PO qty {po_qty} for '{po_li.get('description','')}' (>{total_inv_qty/po_qty*100:.0f}%)",
                    'reported_value': str(total_inv_qty),
                    'correct_value': str(po_qty),
                    'confidence': min(0.95, 0.65 + excess_pct * 0.3),
                })
    
    return findings


def detect_price_escalation(invoices, pos):
    """Detect all invoices against a PO charging rates above PO contracted rate."""
    findings = []
    
    po_lookup = {}
    for po in pos:
        pn = po.get('po_number', '').strip()
        if pn and po.get('line_items'):
            po_lookup[normalize_ref(pn)] = po
    
    po_invoices = defaultdict(list)
    for inv in invoices:
        po_ref = inv.get('po_number', '').strip()
        if po_ref:
            po_invoices[normalize_ref(po_ref)].append(inv)
    
    for po_ref, inv_list in po_invoices.items():
        if len(inv_list) < 2:
            continue
        
        po = po_lookup.get(po_ref)
        if not po:
            continue
        
        for po_li in po.get('line_items', []):
            po_desc = str(po_li.get('description', '')).strip().lower()
            po_hsn = str(po_li.get('hsn_sac', '')).strip()
            po_rate = dec(po_li.get('unit_rate'))
            
            if not po_desc or po_rate is None:
                continue
            
            escalated_invs = []
            for inv in inv_list:
                for inv_li in inv.get('line_items', []):
                    inv_desc = str(inv_li.get('description', '')).strip().lower()
                    inv_hsn = str(inv_li.get('hsn_sac', '')).strip()
                    inv_rate = dec(inv_li.get('unit_rate'))
                    
                    if inv_rate is None:
                        continue
                    
                    # Match by HSN first, then description
                    matched = False
                    if po_hsn and inv_hsn and po_hsn == inv_hsn:
                        matched = True
                    else:
                        inv_words = set(inv_desc.split())
                        po_words = set(po_desc.split())
                        if len(inv_words) >= 2 and len(po_words) >= 2:
                            overlap = len(inv_words & po_words) / max(len(inv_words), len(po_words))
                            if overlap >= 0.6:
                                matched = True
                    
                    if matched and inv_rate > po_rate * Decimal("1.03"):
                        escalated_invs.append((inv, inv_rate))
                        break
            
            if len(escalated_invs) >= 3:  # Relaxed from 4 to catch more
                all_refs = [po.get('po_number', '')] + [i.get('invoice_number', '') for i, _ in escalated_invs]
                all_pages = []
                for i, _ in escalated_invs:
                    all_pages.extend(i.get('source_pages', []))
                
                avg_rate = sum(r for _, r in escalated_invs) / len(escalated_invs)
                findings.append({
                    'category': 'price_escalation',
                    'pages': sorted(set(all_pages)),
                    'document_refs': list(dict.fromkeys(all_refs)),
                    'description': f"All {len(escalated_invs)} invoices charge above PO rate {fmt(po_rate)} for '{po_li.get('description','')}' (avg: {fmt(avg_rate)})",
                    'reported_value': fmt(avg_rate),
                    'correct_value': fmt(po_rate),
                    'confidence': 0.72,
                })
    
    return findings


def detect_balance_drift(bank_stmts):
    """Detect bank statement opening balance != previous month closing balance."""
    findings = []
    
    # Group by account
    accounts = defaultdict(list)
    for bs in bank_stmts:
        acct = bs.get('account_number_masked', 'default')
        accounts[acct].append(bs)
    
    for acct, stmts in accounts.items():
        # Sort by month - parse the period start date
        def sort_key(bs):
            period = bs.get('statement_month', '')
            m = re.match(r'(\d{2})/(\d{2})/(\d{4})', period)
            if m:
                return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
            return period
        
        sorted_stmts = sorted(stmts, key=sort_key)
        
        for i in range(1, len(sorted_stmts)):
            prev = sorted_stmts[i-1]
            curr = sorted_stmts[i]
            
            prev_cb = dec(prev.get('closing_balance'))
            curr_ob = dec(curr.get('opening_balance'))
            
            if prev_cb is None or curr_ob is None:
                continue
            
            if not money_eq(prev_cb, curr_ob, Decimal("0.01")):
                findings.append({
                    'category': 'balance_drift',
                    'pages': sorted(set(
                        prev.get('source_pages', []) + curr.get('source_pages', [])
                    )),
                    'document_refs': [
                        prev.get('statement_id', ''),
                        curr.get('statement_id', '')
                    ],
                    'description': f"Opening balance {fmt(curr_ob)} != prev closing {fmt(prev_cb)} ({prev.get('statement_month','')} -> {curr.get('statement_month','')})",
                    'reported_value': fmt(curr_ob),
                    'correct_value': fmt(prev_cb),
                    'confidence': 0.88,
                })
    
    return findings


def detect_circular_reference(credit_debit_notes):
    """Detect credit/debit notes forming circular reference chains."""
    findings = []
    
    # Build bidirectional graph
    graph = defaultdict(set)
    note_lookup = {}
    all_note_ids = set()
    
    for note in credit_debit_notes:
        nn = note.get('note_number', '')
        note_lookup[nn] = note
        all_note_ids.add(nn)
        
        refs = note.get('linked_documents', [])
        ref = note.get('referenced_doc', '')
        target = note.get('target_doc', '')
        
        neighbors = set()
        if refs:
            neighbors.update(refs)
        if ref:
            neighbors.add(ref)
        if target:
            neighbors.add(target)
        neighbors.discard(nn)
        
        for n in neighbors:
            graph[nn].add(n)
            graph[n].add(nn)  # bidirectional
    
    # Find connected components
    visited = set()
    components = []
    
    def bfs(start):
        component = []
        queue = [start]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    queue.append(neighbor)
        return component
    
    for node in sorted(graph.keys()):
        if node not in visited:
            comp = bfs(node)
            if len(comp) >= 2:
                components.append(comp)
    
    # Each connected component of CN/DN notes that doesn't anchor to a real invoice is circular
    for comp in components:
        has_invoice = any(n.startswith('INV-') for n in comp)
        
        pages = []
        for nn in comp:
            if nn in note_lookup:
                pages.extend(note_lookup[nn].get('source_pages', []))
        
        # A component of only CN/DN notes referencing each other is circular
        if not has_invoice:
            findings.append({
                'category': 'circular_reference',
                'pages': sorted(set(pages)) if pages else [1],
                'document_refs': sorted(comp),
                'description': f"Circular reference chain among {len(comp)} notes: {', '.join(sorted(comp))} - no real invoice anchor",
                'reported_value': ', '.join(sorted(comp)),
                'correct_value': "Should trace to a real invoice",
                'confidence': 0.82,
            })
    
    return findings


def detect_triple_expense_claim(expense_reports):
    """Detect same hotel stay claimed in 3+ different expense reports."""
    findings = []
    seen = set()
    
    # Strategy 1: Same hotel_name in 3+ reports (any employees)
    hotel_groups = defaultdict(list)
    for er in expense_reports:
        hotel = er.get('hotel_name', '').strip().upper()
        if hotel:
            hotel_groups[hotel].append(er)
    
    for hotel, reports in hotel_groups.items():
        report_ids = sorted(set(r.get('report_id', '') for r in reports))
        if len(report_ids) >= 3:
            pages = []
            for r in reports:
                pages.extend(r.get('source_pages', []))
            
            key = tuple(report_ids)
            if key not in seen:
                seen.add(key)
                findings.append({
                    'category': 'triple_expense_claim',
                    'pages': sorted(set(pages)),
                    'document_refs': report_ids,
                    'description': f"Hotel '{hotel}' claimed in {len(report_ids)} expense reports",
                    'reported_value': f"{len(report_ids)} claims",
                    'correct_value': "1 claim",
                    'confidence': 0.82,
                })
    
    # Strategy 2: Same hotel expense line (amount+description) in 3+ reports
    hotel_lines = defaultdict(list)
    for er in expense_reports:
        for el in er.get('expense_lines', []):
            desc = str(el.get('description', '')).strip()
            desc_upper = desc.upper()
            if any(w in desc_upper for w in ['HOTEL', 'STAY', 'ACCOMMODATION', 'LODGE', 'RESORT', 'SHERATON', 'HILTON', 'WESTIN', 'RADISSON', 'TAJ', 'MARRIOTT', 'OBEROI', 'ITC']):
                amount = str(el.get('amount', ''))
                key = f"{amount}|{desc}"
                hotel_lines[key].append(er)
    
    for key, reports in hotel_lines.items():
        report_ids = sorted(set(r.get('report_id', '') for r in reports))
        if len(report_ids) >= 3:
            rkey = tuple(report_ids)
            if rkey not in seen:
                seen.add(rkey)
                pages = []
                for r in reports:
                    pages.extend(r.get('source_pages', []))
                
                amount, desc = key.split('|', 1)
                findings.append({
                    'category': 'triple_expense_claim',
                    'pages': sorted(set(pages)),
                    'document_refs': report_ids,
                    'description': f"Hotel expense '{desc}' ({amount}) claimed in {len(report_ids)} reports",
                    'reported_value': f"{len(report_ids)} claims",
                    'correct_value': "1 claim",
                    'confidence': 0.78,
                })
    
    return findings


def detect_employee_id_collision(expense_reports):
    """Detect same employee ID used by two different people."""
    findings = []
    
    emp_id_names = defaultdict(set)
    emp_id_reports = defaultdict(list)
    
    for er in expense_reports:
        emp_id = er.get('employee_id', '').strip()
        emp_name = er.get('employee_name', '').strip()
        
        if emp_id and emp_name:
            emp_id_names[emp_id].add(emp_name)
            emp_id_reports[emp_id].append(er)
    
    for emp_id, names in emp_id_names.items():
        if len(names) >= 2:
            # Verify they're truly different people (not just formatting differences)
            name_list = sorted(names)
            truly_different = True
            
            # Simple check: if names share first + last word, probably same person
            for i in range(len(name_list)):
                for j in range(i+1, len(name_list)):
                    n1_parts = name_list[i].lower().split()
                    n2_parts = name_list[j].lower().split()
                    if n1_parts and n2_parts:
                        if n1_parts[-1] == n2_parts[-1] and n1_parts[0][0] == n2_parts[0][0]:
                            # Could be same person (e.g. "A. Kumar" vs "Arun Kumar")
                            # But still flag if names differ enough
                            from difflib import SequenceMatcher
                            sim = SequenceMatcher(None, name_list[i].lower(), name_list[j].lower()).ratio()
                            if sim > 0.85:
                                truly_different = False
            
            if truly_different:
                reports = emp_id_reports[emp_id]
                pages = []
                report_ids = []
                for r in reports:
                    pages.extend(r.get('source_pages', []))
                    report_ids.append(r.get('report_id', ''))
                
                findings.append({
                    'category': 'employee_id_collision',
                    'pages': sorted(set(pages)),
                    'document_refs': sorted(set(report_ids)),
                    'description': f"Employee ID '{emp_id}' used by different people: {', '.join(sorted(names))}",
                    'reported_value': f"{emp_id} ({', '.join(sorted(names))})",
                    'correct_value': "Each person should have unique ID",
                    'confidence': 0.80,
                })
    
    return findings


def detect_fake_vendor(invoices, vendors):
    """Detect invoice from vendor not in Vendor Master."""
    from difflib import SequenceMatcher
    
    findings = []
    vendor_names_lower = set(v['canonical_name'].lower() for v in vendors)
    vendor_names_lower.update(v['raw_name'].lower() for v in vendors)
    vendor_gstins = set(v['gstin'].upper() for v in vendors if v.get('gstin'))
    
    for inv in invoices:
        inv_num = inv.get('invoice_number', '')
        vendor_raw = inv.get('vendor_name_raw', '').strip()
        gstin = inv.get('gstin_vendor', '').strip().upper()
        pages = inv.get('source_pages', [])
        
        if not vendor_raw:
            continue
        
        vname_lower = vendor_raw.lower()
        
        # Check exact match
        if vname_lower in vendor_names_lower:
            continue
        
        # Check GSTIN match
        if gstin and gstin in vendor_gstins:
            continue
        
        # Check fuzzy match - if best match is >85% it's a typo, not fake
        best_score = 0
        for vn in vendor_names_lower:
            score = SequenceMatcher(None, vname_lower, vn).ratio()
            if score > best_score:
                best_score = score
        
        if best_score < 0.68:
            # No close match - this is likely a fake vendor
            findings.append({
                'category': 'fake_vendor',
                'pages': pages,
                'document_refs': [inv_num],
                'description': f"Vendor '{vendor_raw}' not found in Vendor Master (best match: {best_score:.0%})",
                'reported_value': vendor_raw,
                'correct_value': "Not in Vendor Master",
                'confidence': 0.75,
            })
    
    return findings


def detect_phantom_po_reference(invoices, pos):
    """Detect invoice citing a PO number that doesn't exist."""
    findings = []
    
    # Build set of all known PO numbers
    known_pos = set()
    for po in pos:
        pn = po.get('po_number', '').strip()
        if pn:
            known_pos.add(normalize_ref(pn))
            known_pos.add(pn)
    
    for inv in invoices:
        inv_num = inv.get('invoice_number', '')
        po_ref = inv.get('po_number', '').strip()
        pages = inv.get('source_pages', [])
        
        if not po_ref:
            continue
        
        po_norm = normalize_ref(po_ref)
        if po_ref not in known_pos and po_norm not in known_pos:
            # Try fuzzy match to rule out OCR errors
            close_match = False
            for kp in known_pos:
                from difflib import SequenceMatcher
                if SequenceMatcher(None, po_norm, normalize_ref(kp)).ratio() > 0.85:
                    close_match = True
                    break
            
            if not close_match:
                findings.append({
                    'category': 'phantom_po_reference',
                    'pages': pages,
                    'document_refs': [inv_num],
                    'description': f"Invoice references PO '{po_ref}' which doesn't exist in the dataset",
                    'reported_value': po_ref,
                    'correct_value': "PO does not exist",
                    'confidence': 0.80,
                })
    
    return findings


#####################################################################
# MAIN PIPELINE
#####################################################################

def run_pipeline():
    print("=" * 60)
    print("NEEDLE FINDER - Financial Gauntlet Pipeline")
    print("=" * 60)
    
    # Load data
    print("\n[1/4] Loading extracted data...")
    invoices, pos, bank_stmts, expense_reports, credit_debit_notes, vendors = load_data()
    print(f"  Invoices: {len(invoices)}, POs: {len(pos)}, Bank Stmts: {len(bank_stmts)}")
    print(f"  Expense Reports: {len(expense_reports)}, Credit/Debit Notes: {len(credit_debit_notes)}")
    print(f"  Vendors: {len(vendors)}")
    
    pos_with_li = sum(1 for p in pos if p.get('line_items'))
    print(f"  POs with line items (after fix): {pos_with_li}")
    bs_with_ob = sum(1 for b in bank_stmts if b.get('opening_balance'))
    print(f"  Bank stmts with opening_balance (after fix): {bs_with_ob}")
    
    # Run all detectors
    print("\n[2/4] Running all 20 detectors...")
    all_findings = []
    
    detector_runs = [
        ("arithmetic_error", lambda: detect_arithmetic_error(invoices)),
        ("billing_typo", lambda: detect_billing_typo(invoices)),
        ("duplicate_line_item", lambda: detect_duplicate_line_item(invoices)),
        ("invalid_date", lambda: detect_invalid_date(invoices, pos, expense_reports)),
        ("wrong_tax_rate", lambda: detect_wrong_tax_rate(invoices)),
        ("po_invoice_mismatch", lambda: detect_po_invoice_mismatch(invoices, pos)),
        ("vendor_name_typo", lambda: detect_vendor_name_typo(invoices, vendors)),
        ("double_payment", lambda: detect_double_payment(bank_stmts)),
        ("ifsc_mismatch", lambda: detect_ifsc_mismatch(invoices, vendors)),
        ("duplicate_expense", lambda: detect_duplicate_expense(expense_reports)),
        ("date_cascade", lambda: detect_date_cascade(invoices, pos)),
        ("gstin_state_mismatch", lambda: detect_gstin_state_mismatch(invoices, vendors)),
        ("quantity_accumulation", lambda: detect_quantity_accumulation(invoices, pos)),
        ("price_escalation", lambda: detect_price_escalation(invoices, pos)),
        ("balance_drift", lambda: detect_balance_drift(bank_stmts)),
        ("circular_reference", lambda: detect_circular_reference(credit_debit_notes)),
        ("triple_expense_claim", lambda: detect_triple_expense_claim(expense_reports)),
        ("employee_id_collision", lambda: detect_employee_id_collision(expense_reports)),
        ("fake_vendor", lambda: detect_fake_vendor(invoices, vendors)),
        ("phantom_po_reference", lambda: detect_phantom_po_reference(invoices, pos)),
    ]
    
    category_findings = {}
    for cat_name, detector_fn in detector_runs:
        try:
            results = detector_fn()
            category_findings[cat_name] = results
            all_findings.extend(results)
            print(f"  {cat_name}: {len(results)} candidates (target: {CATEGORY_COUNTS.get(cat_name, '?')})")
        except Exception as e:
            print(f"  {cat_name}: ERROR - {e}")
            import traceback
            traceback.print_exc()
            category_findings[cat_name] = []
    
    # Select top-N per category based on known counts
    print("\n[3/4] Selecting top-N findings per category (confidence-ranked)...")
    final_findings = []
    finding_counter = 0
    
    for cat_name, target_count in CATEGORY_COUNTS.items():
        candidates = category_findings.get(cat_name, [])
        
        # Sort by confidence descending
        candidates.sort(key=lambda f: f.get('confidence', 0), reverse=True)
        
        # STRICT: take exactly target_count to minimize false positives
        selected = candidates[:target_count]
        
        for f in selected:
            finding_counter += 1
            f['finding_id'] = f"F-{finding_counter:03d}"
        
        final_findings.extend(selected)
        print(f"  {cat_name}: selected {len(selected)}/{len(candidates)} (target: {target_count})")
    
    # Build submission
    print("\n[4/4] Building submission JSON...")
    submission = {
        "team_id": "hackculture",
        "findings": []
    }
    
    for f in final_findings:
        submission["findings"].append({
            "finding_id": f.get('finding_id', ''),
            "category": f.get('category', ''),
            "pages": f.get('pages', []),
            "document_refs": f.get('document_refs', []),
            "description": f.get('description', ''),
            "reported_value": str(f.get('reported_value', '')),
            "correct_value": str(f.get('correct_value', '')),
        })
    
    # Write output files
    out_dir = DATA / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    submission_path = out_dir / "submission_v5.json"
    with open(submission_path, 'w') as fout:
        json.dump(submission, fout, indent=2, default=str)
    
    # Also write all candidates with confidence
    all_cands_path = out_dir / "all_candidates.json"
    with open(all_cands_path, 'w') as fout:
        json.dump(all_findings, fout, indent=2, default=str)
    
    # Summary stats
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    cat_counts = Counter(f['category'] for f in submission['findings'])
    total_pts = 0
    pt_weights = {
        'arithmetic_error': 1, 'billing_typo': 1, 'duplicate_line_item': 1,
        'invalid_date': 1, 'wrong_tax_rate': 1,
        'po_invoice_mismatch': 3, 'vendor_name_typo': 3, 'double_payment': 3,
        'ifsc_mismatch': 3, 'duplicate_expense': 3, 'date_cascade': 3,
        'gstin_state_mismatch': 3,
        'quantity_accumulation': 7, 'price_escalation': 7, 'balance_drift': 7,
        'circular_reference': 7, 'triple_expense_claim': 7,
        'employee_id_collision': 7, 'fake_vendor': 7, 'phantom_po_reference': 7,
    }
    
    for cat in sorted(CATEGORY_COUNTS.keys()):
        count = cat_counts.get(cat, 0)
        target = CATEGORY_COUNTS[cat]
        weight = pt_weights.get(cat, 1)
        max_pts = target * weight
        est_pts = count * weight  # Optimistic estimate
        total_pts += est_pts
        status = "OK" if count >= target * 0.6 else "LOW" if count > 0 else "MISSING"
        print(f"  {cat:30s}: {count:3d}/{target:3d}  (max={max_pts:4d}pts)  [{status}]")
    
    print(f"\n  Total findings submitted: {len(submission['findings'])}")
    print(f"  Estimated max points (if all correct): {total_pts}/{920}")
    print(f"\n  Submission file: {submission_path}")
    print(f"  All candidates: {all_cands_path}")
    
    return submission


def run_agent_pipeline():
    """Run the LangChain/LangGraph multi-agent pipeline instead of the
    direct rule-based pipeline.  Each of the 20 categories gets its own
    ReAct agent backed by Claude (Bedrock) that invokes the rule-based
    detector as a tool, reviews the results, and returns validated findings.
    A LangGraph orchestrator coordinates the agents in three tiers
    (easy → medium → evil) and performs final adjudication.
    """
    from dotenv import load_dotenv
    load_dotenv(BASE / ".env")

    print("=" * 60)
    print("NEEDLE FINDER - Multi-Agent LangGraph Pipeline")
    print("=" * 60)

    # Load data (same as direct pipeline)
    print("\n[1/3] Loading extracted data...")
    invoices, pos, bank_stmts, expense_reports, credit_debit_notes, vendors = load_data()
    print(f"  Invoices: {len(invoices)}, POs: {len(pos)}, Bank Stmts: {len(bank_stmts)}")
    print(f"  Expense Reports: {len(expense_reports)}, Credit/Debit Notes: {len(credit_debit_notes)}")
    print(f"  Vendors: {len(vendors)}")

    # Import and run the LangGraph orchestrator
    print("\n[2/3] Running LangGraph multi-agent orchestrator (20 agents)...")
    sys.path.insert(0, str(BASE / "src"))
    from agents.orchestrator import run_pipeline as agent_run_pipeline

    submission = agent_run_pipeline(
        invoices=invoices,
        pos=pos,
        bank_stmts=bank_stmts,
        expense_reports=expense_reports,
        credit_debit_notes=credit_debit_notes,
        vendors=vendors,
    )

    # Write output
    print("\n[3/3] Writing submission...")
    out_dir = DATA / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    submission_path = out_dir / "submission_agent.json"
    with open(submission_path, 'w') as fout:
        json.dump(submission, fout, indent=2, default=str)

    # Summary
    print("\n" + "=" * 60)
    print("AGENT PIPELINE RESULTS")
    print("=" * 60)
    cat_counts = Counter(f['category'] for f in submission.get('findings', []))
    for cat in sorted(CATEGORY_COUNTS.keys()):
        count = cat_counts.get(cat, 0)
        target = CATEGORY_COUNTS[cat]
        status = "OK" if count >= target * 0.6 else "LOW" if count > 0 else "MISSING"
        print(f"  {cat:30s}: {count:3d}/{target:3d}  [{status}]")
    print(f"\n  Total findings: {len(submission.get('findings', []))}")
    print(f"  Submission: {submission_path}")

    return submission


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "direct"
    if mode == "agent":
        run_agent_pipeline()
    else:
        run_pipeline()
