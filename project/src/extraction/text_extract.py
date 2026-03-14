"""Fast regex-based extraction for structured documents.

Parses the well-formatted gauntlet PDF text directly without LLM calls.
Falls back to LLM only when regex extraction fails.
"""
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from ..core.logging import get_logger
from ..core.models import (
    InvoiceRecord, PurchaseOrderRecord, BankStatement, BankStatementTxn,
    ExpenseReportRecord, CreditDebitNoteRecord, LineItem, ExpenseLine,
)
from ..core.enums import DocType
from ..core.utils import safe_decimal

log = get_logger(__name__)


def _clean_amount(s: str) -> Optional[Decimal]:
    """Parse amount from text like 'I1,55,208.88' or '₹ 1,55,208.88' or '-I8,561.19'."""
    if not s or s.strip() in ("", "-", "None", "null"):
        return None
    s = s.strip()
    # Preserve leading negative sign
    negative = False
    if s.startswith('-'):
        negative = True
        s = s[1:]
    # Remove currency symbols and leading I (Indian Rupee OCR artefact)
    s = re.sub(r'^[I₹$€£\s]+', '', s)
    s = re.sub(r'[,\s]', '', s)  # remove commas and spaces
    # Handle parenthesis for negatives
    if s.startswith('(') and s.endswith(')'):
        negative = True
        s = s[1:-1]
    if negative:
        s = '-' + s
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _find_field(text: str, *patterns: str) -> str:
    """Find the value for a field using multiple regex patterns.
    Also handles the newline-separated pattern: 'Label:\\nValue'
    """
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()
    return ""


def _find_field_newline(text: str, label: str) -> str:
    """Find a field where the value is on the next line after the label.
    Handles patterns like:
    PO Number:
    PO-2025-00015
    """
    pattern = re.compile(
        rf'{re.escape(label)}\s*[:#]?\s*\n\s*(.+?)(?:\n|$)',
        re.IGNORECASE | re.MULTILINE,
    )
    m = pattern.search(text)
    if m:
        return m.group(1).strip()
    # Also try same-line
    pattern2 = re.compile(
        rf'{re.escape(label)}\s*[:#]?\s*(.+?)(?:\n|$)',
        re.IGNORECASE | re.MULTILINE,
    )
    m = pattern2.search(text)
    if m:
        val = m.group(1).strip()
        if val and val != label:
            return val
    return ""


def extract_invoice_from_text(text: str, source_pages: list[int], doc_id: str = "") -> Optional[InvoiceRecord]:
    """Extract invoice data from text using regex."""
    inv_num = _find_field(text,
        r'Invoice\s*No\s*[:#]?\s*\n?\s*(INV[-\s]?\d{4}[-\s]?\d+)',
        r'Invoice\s*Number\s*[:#]?\s*\n?\s*(INV[-\s]?\d{4}[-\s]?\d+)',
    )
    if not inv_num:
        return None

    inv_date = _find_field_newline(text, "Date")
    due_date = _find_field(text,
        r'Due\s*Date\s*[:#]?\s*\n?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    )
    po_ref = _find_field(text,
        r'(?:PO|P\.O\.?)\s*(?:Reference|Ref|No|Number)?\s*[:#]?\s*\n?\s*(PO[-\s]?\d{4}[-\s]?\d+)',
    )
    vendor_name = _find_field_newline(text, "Name")
    gstin_vendor = _find_field(text,
        r'GSTIN\s*[:#]?\s*\n?\s*(\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d][A-Z])',
    )
    # Also get buyer GSTIN (usually second occurrence)
    gstin_matches = re.findall(r'GSTIN\s*[:#]?\s*\n?\s*(\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d][A-Z])', text)
    gstin_buyer = gstin_matches[1] if len(gstin_matches) > 1 else ""

    bank_ifsc = _find_field(text,
        r'IFSC\s*[:#]?\s*\n?\s*([A-Z]{4}0[A-Z0-9]{6})',
    )
    bank_account = _find_field(text,
        r'(?:Account|A/c)\s*(?:No|Number)?\s*[:#]?\s*\n?\s*(\d{9,18})',
    )

    # Extract line items
    line_items = _extract_invoice_line_items(text)

    # Extract totals — handle newline separation
    subtotal = _clean_amount(_find_field(text,
        r'(?:Sub\s*[- ]?\s*total|Subtotal)\s*[:#]?\s*\n?\s*([I₹]?[\d,]+\.?\d*)',
    ))

    # Tax: look for GST / IGST pattern with percentage
    tax_match = re.search(
        r'(?:GST|IGST|CGST\s*\+\s*SGST|Tax)\s*\(\s*(\d+(?:\.\d+)?)\s*%\s*\)\s*[:#]?\s*\n?\s*([I₹]?[\d,]+\.?\d*)',
        text, re.I)
    tax_rate = safe_decimal(tax_match.group(1)) if tax_match else None
    tax_amount = _clean_amount(tax_match.group(2)) if tax_match else None

    if not tax_amount:
        tax_amount = _clean_amount(_find_field(text,
            r'(?:Total\s+)?(?:GST|IGST|CGST\s*\+\s*SGST)\s*(?:Amount)?\s*[:#]?\s*\n?\s*([I₹]?[\d,]+\.?\d*)',
        ))

    grand_total = _clean_amount(_find_field(text,
        r'(?:Grand\s+Total|Total\s+Amount|Amount\s+Payable|Net\s+Amount)\s*[:#]?\s*\n?\s*([I₹]?[\d,]+\.?\d*)',
    ))

    return InvoiceRecord(
        invoice_number=inv_num.replace(" ", ""),
        vendor_name_raw=vendor_name,
        invoice_date=inv_date,
        due_date=due_date,
        po_number=po_ref.replace(" ", "") if po_ref else "",
        gstin_vendor=gstin_vendor,
        gstin_buyer=gstin_buyer,
        bank_ifsc=bank_ifsc,
        bank_account=bank_account,
        line_items=line_items,
        subtotal=subtotal,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        grand_total=grand_total,
        source_pages=source_pages,
        doc_id=doc_id,
        raw_text=text,
    )


def _extract_invoice_line_items(text: str) -> list[LineItem]:
    """Extract line items from invoice text.
    The PDF text has each table cell on a new line:
    1
    Professional Consulting Services
    998412
    0.45
    Hrs
    I8,209.47
    I3,694.26
    """
    items = []
    # Find the LINE ITEMS or ORDER ITEMS section
    li_start = re.search(r'(?:LINE|ORDER)\s+ITEMS\s*\n', text, re.I)
    if not li_start:
        return items
    section = text[li_start.end():]

    # Skip header line (# Description HSN Qty Unit Rate Amount)
    header_end = re.search(r'Amount\s*\n', section, re.I)
    if header_end:
        section = section[header_end.end():]

    lines = section.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Look for a line number (1, 2, 3, etc.)
        if re.match(r'^\d+$', line) and int(line) < 100:
            line_num = int(line)
            # Next lines should be: description, HSN, qty, unit, rate, amount
            try:
                # Collect next non-empty lines
                fields = []
                j = i + 1
                while j < len(lines) and len(fields) < 6:
                    val = lines[j].strip()
                    if val:
                        fields.append(val)
                    j += 1
                    # Stop if we hit the next line number or a section boundary
                    if j < len(lines) and re.match(r'^\d+$', lines[j].strip()):
                        next_num = int(lines[j].strip())
                        if next_num == line_num + 1 and next_num < 100:
                            break

                if len(fields) >= 4:  # at minimum: desc, hsn, qty, rate/amount
                    desc = fields[0]
                    hsn = fields[1] if re.match(r'^\d{4,8}$', fields[1]) else ""
                    offset = 2 if hsn else 1
                    qty = safe_decimal(fields[offset]) if offset < len(fields) else None
                    unit = fields[offset + 1] if offset + 1 < len(fields) and not fields[offset + 1].startswith('I') else ""
                    rate_idx = offset + (2 if unit else 1)
                    rate = _clean_amount(fields[rate_idx]) if rate_idx < len(fields) else None
                    amt_idx = rate_idx + 1
                    amt = _clean_amount(fields[amt_idx]) if amt_idx < len(fields) else None

                    items.append(LineItem(
                        line_num=line_num,
                        description=desc,
                        hsn_sac=hsn,
                        quantity=qty,
                        unit=unit,
                        unit_rate=rate,
                        amount=amt,
                    ))
                i = j
                continue
            except Exception:
                pass
        # Stop at boilerplate text
        if 'This invoice has been' in line or 'accordance with' in line:
            break
        i += 1

    return items


def extract_po_from_text(text: str, source_pages: list[int], doc_id: str = "") -> Optional[PurchaseOrderRecord]:
    """Extract PO data from text."""
    po_num = _find_field(text,
        r'(?:PO\s*Number|P\.?O\.?\s*(?:No|Number|#)|Purchase\s+Order\s*(?:No|Number|#)?)\s*[:#]?\s*\n?\s*(PO[-\s]?\d{4}[-\s]?\d+)',
    )
    if not po_num:
        return None

    po_date = _find_field_newline(text, "Date")
    delivery_date = _find_field(text,
        r'(?:Delivery|Expected)\s*Date\s*[:#]?\s*\n?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    )
    vendor_name = _find_field_newline(text, "Name")
    gstin_vendor = _find_field(text,
        r'GSTIN\s*[:#]?\s*\n?\s*(\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d][A-Z])',
    )

    # Extract line items (same newline format as invoices)
    line_items = _extract_invoice_line_items(text)

    subtotal = _clean_amount(_find_field(text,
        r'(?:Sub\s*[- ]?\s*total|Subtotal)\s*[:#]?\s*\n?\s*([I₹]?[\d,]+\.?\d*)',
    ))
    grand_total = _clean_amount(_find_field(text,
        r'(?:Grand\s+Total|Total\s+Amount|Total)\s*[:#]?\s*\n?\s*([I₹]?[\d,]+\.?\d*)',
    ))

    return PurchaseOrderRecord(
        po_number=po_num.replace(" ", ""),
        vendor_name_raw=vendor_name,
        po_date=po_date,
        delivery_date=delivery_date,
        gstin_vendor=gstin_vendor,
        line_items=line_items,
        subtotal=subtotal,
        grand_total=grand_total,
        source_pages=source_pages,
        doc_id=doc_id,
        raw_text=text,
    )


def extract_bank_statement_from_text(text: str, source_pages: list[int], doc_id: str = "") -> Optional[BankStatement]:
    """Extract bank statement data from text."""
    stmt_id = _find_field(text, r'(BS-\d{4}-\d+)')
    if not stmt_id:
        return None

    stmt_month = _find_field(text,
        r'(?:Statement\s+(?:Period|Month|For))\s*[:#]?\s*(.+?)(?:\n|$)',
        r'(?:Period|Month)\s*[:#]?\s*(.+?)(?:\n|$)',
    )
    account_num = _find_field(text,
        r'(?:Account|A/c)\s*(?:No|Number)?\s*[:#]?\s*([\dX*]+)',
    )
    # Handle newline-separated format: "Opening Balance:\nI5,23,884.40" and negative "-I8,561.19"
    opening_str = _find_field(text,
        r'Opening\s+Balance\s*[:#]?\s*(-?[I₹]?[\d,]+\.?\d*)',
    )
    if not opening_str:
        opening_str = _find_field_newline(text, "Opening Balance")
    opening_bal = _clean_amount(opening_str)
    closing_str = _find_field(text,
        r'Closing\s+Balance\s*[:#]?\s*(-?[I₹]?[\d,]+\.?\d*)',
    )
    if not closing_str:
        closing_str = _find_field_newline(text, "Closing Balance")
    closing_bal = _clean_amount(closing_str)

    # Extract transactions
    txns = _extract_bank_transactions(text, source_pages, doc_id)

    return BankStatement(
        statement_id=stmt_id,
        statement_month=stmt_month,
        account_number_masked=account_num,
        opening_balance=opening_bal,
        closing_balance=closing_bal,
        transactions=txns,
        source_pages=source_pages,
        doc_id=doc_id,
        raw_text=text,
    )


def _extract_bank_transactions(text: str, source_pages: list[int], doc_id: str) -> list[BankStatementTxn]:
    """Extract bank statement transactions.
    Format is newline-separated:
    01/01/2025
    Receipt from Reliance Industri
    CASH
    CASH934156
    -
    I84,385.36
    I6,08,269.76
    """
    txns = []
    # Find TRANSACTIONS section
    txn_start = re.search(r'TRANSACTIONS\s*\n', text, re.I)
    if not txn_start:
        return txns
    section = text[txn_start.end():]

    # Skip header (Date Description Type Ref Debit Credit Balance)
    header_end = re.search(r'Balance\s*\n', section, re.I)
    if header_end:
        section = section[header_end.end():]

    lines = section.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Look for a date pattern (dd/mm/yyyy)
        date_match = re.match(r'^(\d{1,2}/\d{1,2}/\d{4})$', line)
        if date_match:
            txn_date = date_match.group(1)
            # Collect next fields: description, type, reference, debit, credit, balance
            fields = []
            j = i + 1
            while j < len(lines) and len(fields) < 6:
                val = lines[j].strip()
                if val:
                    # Stop if we hit the next date
                    if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', val):
                        break
                    # Stop if we hit closing balance or end markers
                    if 'Closing Balance' in val or 'closing_balance' in val.lower():
                        break
                    fields.append(val)
                j += 1

            if len(fields) >= 4:
                desc = fields[0]
                txn_type = fields[1] if len(fields) > 1 else ""
                reference = fields[2] if len(fields) > 2 else ""
                debit_str = fields[3] if len(fields) > 3 else "-"
                credit_str = fields[4] if len(fields) > 4 else "-"
                balance_str = fields[5] if len(fields) > 5 else ""

                debit = None if debit_str == '-' else _clean_amount(debit_str)
                credit = None if credit_str == '-' else _clean_amount(credit_str)
                balance = _clean_amount(balance_str) if balance_str else None

                txns.append(BankStatementTxn(
                    txn_date=txn_date,
                    description=desc,
                    reference=reference,
                    debit=debit,
                    credit=credit,
                    balance=balance,
                    source_pages=source_pages,
                    doc_id=doc_id,
                ))
            i = j
            continue
        # Stop at closing balance section
        if 'Closing Balance' in line:
            break
        i += 1
    return txns


def extract_expense_report_from_text(text: str, source_pages: list[int], doc_id: str = "") -> Optional[ExpenseReportRecord]:
    """Extract expense report data from text."""
    report_id = _find_field(text,
        r'(?:Report\s*(?:ID|No|Number|#))\s*[:#]?\s*\n?\s*(EXP[-\s]?\d{4}[-\s]?\d+)',
    )
    if not report_id:
        return None

    employee_name = _find_field_newline(text, "Employee")
    employee_id = _find_field(text,
        r'Employee\s*ID\s*[:#]?\s*\n?\s*(EMP[-\s]?\d+)',
    )
    department = _find_field_newline(text, "Department")
    purpose = _find_field_newline(text, "Purpose")
    city = _find_field_newline(text, "City")

    # Hotel info
    hotel_name = _find_field(text,
        r'(?:Hotel|Accommodation)\s*[:#]?\s*\n?\s*(.+?)(?:\n|$)',
    )
    # Look for hotel in expense entries (e.g., "Hotel Accommodatio")
    hotel_match = re.search(r'Hotel\s+Accommodatio\w*\s*\n(.+?)(?:\s*-\s*\d+\s*night|\n)', text)
    if hotel_match:
        hotel_name = hotel_match.group(1).strip()

    stay_start = _find_field(text,
        r'(?:Check[\s-]*in|Stay\s+From|From)\s*[:#]?\s*\n?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    )
    stay_end = _find_field(text,
        r'(?:Check[\s-]*out|Stay\s+To|To)\s*[:#]?\s*\n?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    )
    total_amount = _clean_amount(_find_field(text,
        r'(?:TOTAL\s+CLAIMED|Total\s+Amount|Grand\s+Total)\s*[:#]?\s*\n?\s*([I₹]?[\d,]+\.?\d*)',
    ))

    # Extract expense lines
    lines = _extract_expense_lines(text)

    return ExpenseReportRecord(
        report_id=report_id.replace(" ", ""),
        employee_name=employee_name,
        employee_id=employee_id.replace(" ", "") if employee_id else "",
        department=department,
        expense_lines=lines,
        hotel_name=hotel_name,
        stay_start=stay_start,
        stay_end=stay_end,
        total_amount=total_amount,
        source_pages=source_pages,
        doc_id=doc_id,
        raw_text=text,
    )


def _extract_expense_lines(text: str) -> list[ExpenseLine]:
    """Extract expense report line items.
    Format is newline-separated:
    1
    12/12/2025
    Software License
    Software License - Pune
    Pune
    I6,444.60
    """
    lines = []
    # Find EXPENSE ENTRIES section
    section_start = re.search(r'EXPENSE\s+ENTRIES\s*\n', text, re.I)
    if not section_start:
        return lines
    section = text[section_start.end():]

    # Skip header (# Date Category Description City Amount)
    header_end = re.search(r'Amount\s*\n', section, re.I)
    if header_end:
        section = section[header_end.end():]

    text_lines = section.split('\n')
    i = 0
    while i < len(text_lines):
        line = text_lines[i].strip()
        # Look for a line number
        if re.match(r'^\d+$', line) and int(line) < 100:
            line_num = int(line)
            # Next fields: date, category, description, city, amount
            fields = []
            j = i + 1
            while j < len(text_lines) and len(fields) < 5:
                val = text_lines[j].strip()
                if val:
                    # Stop if we hit the next line number
                    if re.match(r'^\d+$', val) and int(val) < 100:
                        break
                    # Stop at TOTAL
                    if 'TOTAL' in val.upper():
                        break
                    fields.append(val)
                j += 1

            if len(fields) >= 3:
                date = fields[0] if re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', fields[0]) else ""
                offset = 1 if date else 0
                category = fields[offset] if offset < len(fields) else ""
                description = fields[offset + 1] if offset + 1 < len(fields) else ""
                # Find the amount (starts with I or ₹ or is a decimal number)
                amount = None
                merchant = ""
                city = ""
                for f in fields[offset + 2:]:
                    if re.match(r'^[I₹]?[\d,]+\.?\d*$', f.replace(',', '')):
                        amount = _clean_amount(f)
                    elif not merchant:
                        # Could be city or merchant
                        merchant = f

                # Extract hotel name from description
                hotel = ""
                hotel_match = re.search(r'(.+?)\s*-\s*(\d+)\s*night', description)
                if hotel_match:
                    hotel = hotel_match.group(1).strip()

                lines.append(ExpenseLine(
                    line_num=line_num,
                    date=date,
                    description=description,
                    category=category,
                    merchant=merchant or description,
                    amount=amount,
                ))
            i = j
            continue
        if 'TOTAL' in line.upper():
            break
        i += 1
    return lines


def extract_credit_debit_note_from_text(text: str, source_pages: list[int], doc_id: str = "") -> Optional[CreditDebitNoteRecord]:
    """Extract credit/debit note data from text."""
    cn_num = _find_field(text, r'CREDIT\s+NOTE\s*(?:No|Number|#)\s*[:#]?\s*(CN[-\s]?\d{4}[-\s]?\d+)')
    dn_num = _find_field(text, r'DEBIT\s+NOTE\s*(?:No|Number|#)\s*[:#]?\s*(DN[-\s]?\d{4}[-\s]?\d+)')

    note_number = cn_num or dn_num
    if not note_number:
        return None

    note_type = "credit" if cn_num else "debit"

    # Find referenced documents
    referenced_doc = _find_field(text,
        r'(?:Original\s+Invoice|Reference|Against)\s*[:#]?\s*((?:INV|CN|DN)-\d{4}-\d+)',
    )
    reason = _find_field(text,
        r'Reason\s*[:#]?\s*(.+?)(?:\n|$)',
    )
    amount = _clean_amount(_find_field(text,
        r'Amount\s*[:#]?\s*([I₹]?[\d,]+\.?\d*)',
    ))
    vendor_name = _find_field(text,
        r'Vendor\s*[:#]?\s*(.+?)(?:\n|$)',
    )
    gstin = _find_field(text,
        r'GSTIN\s*[:#]?\s*(\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d][A-Z])',
    )

    # Linked documents (all refs in text)
    all_refs = re.findall(r'\b((?:INV|CN|DN|PO)-\d{4}-\d+)\b', text)
    linked = [r for r in all_refs if r != note_number]

    return CreditDebitNoteRecord(
        note_number=note_number.replace(" ", ""),
        note_type=note_type,
        vendor_name_raw=vendor_name,
        gstin_vendor=gstin,
        referenced_doc=referenced_doc or "",
        target_doc=linked[0] if linked else "",
        reason=reason,
        amount=amount,
        linked_documents=linked,
        source_pages=source_pages,
        doc_id=doc_id,
        raw_text=text,
    )


def extract_from_text(text: str, doc_type: DocType, source_pages: list[int],
                      doc_id: str = ""):
    """Route extraction to appropriate regex-based extractor."""
    if doc_type == DocType.INVOICE:
        return extract_invoice_from_text(text, source_pages, doc_id)
    elif doc_type == DocType.PURCHASE_ORDER:
        return extract_po_from_text(text, source_pages, doc_id)
    elif doc_type == DocType.BANK_STATEMENT:
        return extract_bank_statement_from_text(text, source_pages, doc_id)
    elif doc_type == DocType.EXPENSE_REPORT:
        return extract_expense_report_from_text(text, source_pages, doc_id)
    elif doc_type in (DocType.CREDIT_NOTE, DocType.DEBIT_NOTE):
        return extract_credit_debit_note_from_text(text, source_pages, doc_id)
    return None
