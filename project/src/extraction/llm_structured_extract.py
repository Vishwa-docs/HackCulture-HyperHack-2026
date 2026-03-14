"""LLM-based structured extraction for all document types."""
import json
import re
from decimal import Decimal
from typing import Optional

from ..core.logging import get_logger
from ..core.models import (
    InvoiceRecord, PurchaseOrderRecord, BankStatement, BankStatementTxn,
    ExpenseReportRecord, CreditDebitNoteRecord, LineItem, ExpenseLine,
)
from ..core.enums import DocType
from ..core.utils import safe_decimal

log = get_logger(__name__)


INVOICE_PROMPT = """Extract structured data from this invoice document. Return valid JSON only.

Required fields:
{{
  "invoice_number": "",
  "vendor_name": "",
  "invoice_date": "",
  "due_date": "",
  "po_number": "",
  "gstin_vendor": "",
  "gstin_buyer": "",
  "bank_ifsc": "",
  "bank_account": "",
  "line_items": [
    {{
      "line_num": 1,
      "description": "",
      "hsn_sac": "",
      "quantity": null,
      "unit": "",
      "unit_rate": null,
      "amount": null,
      "tax_rate": null,
      "tax_amount": null
    }}
  ],
  "subtotal": null,
  "tax_rate": null,
  "tax_amount": null,
  "grand_total": null
}}

IMPORTANT:
- Extract EXACT values as written in the document
- Do NOT compute or correct any values
- Numbers should be plain numbers (no commas, no currency symbols)
- Dates should be in the format shown in document
- If a field is not present, use null or empty string

DOCUMENT TEXT:
{text}

Return JSON:"""

PO_PROMPT = """Extract structured data from this Purchase Order. Return valid JSON only.

Required fields:
{{
  "po_number": "",
  "vendor_name": "",
  "po_date": "",
  "delivery_date": "",
  "line_items": [
    {{
      "line_num": 1,
      "description": "",
      "quantity": null,
      "unit": "",
      "unit_rate": null,
      "amount": null
    }}
  ],
  "subtotal": null,
  "tax_amount": null,
  "grand_total": null
}}

IMPORTANT: Extract EXACT values as written. Do NOT compute or correct.

DOCUMENT TEXT:
{text}

Return JSON:"""

BANK_STATEMENT_PROMPT = """Extract structured data from this bank statement. Return valid JSON only.

Required fields:
{{
  "statement_month": "",
  "account_number": "",
  "opening_balance": null,
  "closing_balance": null,
  "transactions": [
    {{
      "txn_date": "",
      "reference": "",
      "description": "",
      "debit": null,
      "credit": null,
      "balance": null
    }}
  ]
}}

IMPORTANT: Extract EXACT values as written. Do NOT compute or correct.

DOCUMENT TEXT:
{text}

Return JSON:"""

EXPENSE_REPORT_PROMPT = """Extract structured data from this expense report. Return valid JSON only.

Required fields:
{{
  "report_id": "",
  "employee_name": "",
  "employee_id": "",
  "department": "",
  "expense_lines": [
    {{
      "line_num": 1,
      "date": "",
      "description": "",
      "category": "",
      "merchant": "",
      "amount": null,
      "receipt_ref": ""
    }}
  ],
  "hotel_name": "",
  "stay_start": "",
  "stay_end": "",
  "total_amount": null
}}

IMPORTANT: Extract EXACT values. Do NOT correct or compute.

DOCUMENT TEXT:
{text}

Return JSON:"""

CREDIT_DEBIT_NOTE_PROMPT = """Extract structured data from this credit/debit note. Return valid JSON only.

Required fields:
{{
  "note_number": "",
  "note_type": "credit" or "debit",
  "referenced_doc": "",
  "target_doc": "",
  "reason": "",
  "amount": null
}}

IMPORTANT: Extract EXACT values as written.

DOCUMENT TEXT:
{text}

Return JSON:"""


def extract_with_llm(text: str, doc_type: DocType, bedrock_client, source_pages: list[int] = None, doc_id: str = ""):
    """Route extraction to appropriate prompt based on doc type."""
    source_pages = source_pages or []

    if doc_type == DocType.INVOICE:
        return _extract_invoice(text, bedrock_client, source_pages, doc_id)
    elif doc_type == DocType.PURCHASE_ORDER:
        return _extract_po(text, bedrock_client, source_pages, doc_id)
    elif doc_type == DocType.BANK_STATEMENT:
        return _extract_bank_statement(text, bedrock_client, source_pages, doc_id)
    elif doc_type == DocType.EXPENSE_REPORT:
        return _extract_expense_report(text, bedrock_client, source_pages, doc_id)
    elif doc_type in (DocType.CREDIT_NOTE, DocType.DEBIT_NOTE):
        return _extract_credit_debit_note(text, bedrock_client, source_pages, doc_id)
    else:
        return None


def _extract_invoice(text: str, bedrock, pages: list[int], doc_id: str) -> Optional[InvoiceRecord]:
    prompt = INVOICE_PROMPT.format(text=text[:6000])
    data = bedrock.extract_json(prompt)
    if not data:
        return None
    try:
        items = []
        for li in data.get("line_items", []):
            items.append(LineItem(
                line_num=li.get("line_num", 0),
                description=str(li.get("description", "")),
                hsn_sac=str(li.get("hsn_sac", "")),
                quantity=safe_decimal(li.get("quantity")),
                unit=str(li.get("unit", "")),
                unit_rate=safe_decimal(li.get("unit_rate")),
                amount=safe_decimal(li.get("amount")),
                tax_rate=safe_decimal(li.get("tax_rate")),
                tax_amount=safe_decimal(li.get("tax_amount")),
            ))
        return InvoiceRecord(
            invoice_number=str(data.get("invoice_number", "")),
            vendor_name_raw=str(data.get("vendor_name", "")),
            invoice_date=str(data.get("invoice_date", "")),
            due_date=str(data.get("due_date", "")),
            po_number=str(data.get("po_number", "")),
            gstin_vendor=str(data.get("gstin_vendor", "")),
            gstin_buyer=str(data.get("gstin_buyer", "")),
            bank_ifsc=str(data.get("bank_ifsc", "")),
            bank_account=str(data.get("bank_account", "")),
            line_items=items,
            subtotal=safe_decimal(data.get("subtotal")),
            tax_rate=safe_decimal(data.get("tax_rate")),
            tax_amount=safe_decimal(data.get("tax_amount")),
            grand_total=safe_decimal(data.get("grand_total")),
            source_pages=pages,
            doc_id=doc_id,
            raw_text=text,
        )
    except Exception as e:
        log.error(f"Invoice extraction failed: {e}")
        return None


def _extract_po(text: str, bedrock, pages: list[int], doc_id: str) -> Optional[PurchaseOrderRecord]:
    prompt = PO_PROMPT.format(text=text[:6000])
    data = bedrock.extract_json(prompt)
    if not data:
        return None
    try:
        items = []
        for li in data.get("line_items", []):
            items.append(LineItem(
                line_num=li.get("line_num", 0),
                description=str(li.get("description", "")),
                quantity=safe_decimal(li.get("quantity")),
                unit=str(li.get("unit", "")),
                unit_rate=safe_decimal(li.get("unit_rate")),
                amount=safe_decimal(li.get("amount")),
            ))
        return PurchaseOrderRecord(
            po_number=str(data.get("po_number", "")),
            vendor_name_raw=str(data.get("vendor_name", "")),
            po_date=str(data.get("po_date", "")),
            delivery_date=str(data.get("delivery_date", "")),
            line_items=items,
            subtotal=safe_decimal(data.get("subtotal")),
            tax_amount=safe_decimal(data.get("tax_amount")),
            grand_total=safe_decimal(data.get("grand_total")),
            source_pages=pages,
            doc_id=doc_id,
            raw_text=text,
        )
    except Exception as e:
        log.error(f"PO extraction failed: {e}")
        return None


def _extract_bank_statement(text: str, bedrock, pages: list[int], doc_id: str) -> Optional[BankStatement]:
    prompt = BANK_STATEMENT_PROMPT.format(text=text[:6000])
    data = bedrock.extract_json(prompt)
    if not data:
        return None
    try:
        txns = []
        for t in data.get("transactions", []):
            txns.append(BankStatementTxn(
                txn_date=str(t.get("txn_date", "")),
                reference=str(t.get("reference", "")),
                description=str(t.get("description", "")),
                debit=safe_decimal(t.get("debit")),
                credit=safe_decimal(t.get("credit")),
                balance=safe_decimal(t.get("balance")),
                source_pages=pages,
                doc_id=doc_id,
            ))
        return BankStatement(
            statement_month=str(data.get("statement_month", "")),
            account_number_masked=str(data.get("account_number", "")),
            opening_balance=safe_decimal(data.get("opening_balance")),
            closing_balance=safe_decimal(data.get("closing_balance")),
            transactions=txns,
            source_pages=pages,
            doc_id=doc_id,
            raw_text=text,
        )
    except Exception as e:
        log.error(f"Bank statement extraction failed: {e}")
        return None


def _extract_expense_report(text: str, bedrock, pages: list[int], doc_id: str) -> Optional[ExpenseReportRecord]:
    prompt = EXPENSE_REPORT_PROMPT.format(text=text[:6000])
    data = bedrock.extract_json(prompt)
    if not data:
        return None
    try:
        lines = []
        for el in data.get("expense_lines", []):
            lines.append(ExpenseLine(
                line_num=el.get("line_num", 0),
                date=str(el.get("date", "")),
                description=str(el.get("description", "")),
                category=str(el.get("category", "")),
                merchant=str(el.get("merchant", "")),
                amount=safe_decimal(el.get("amount")),
                receipt_ref=str(el.get("receipt_ref", "")),
            ))
        return ExpenseReportRecord(
            report_id=str(data.get("report_id", "")),
            employee_name=str(data.get("employee_name", "")),
            employee_id=str(data.get("employee_id", "")),
            department=str(data.get("department", "")),
            expense_lines=lines,
            hotel_name=str(data.get("hotel_name", "")),
            stay_start=str(data.get("stay_start", "")),
            stay_end=str(data.get("stay_end", "")),
            total_amount=safe_decimal(data.get("total_amount")),
            source_pages=pages,
            doc_id=doc_id,
            raw_text=text,
        )
    except Exception as e:
        log.error(f"Expense report extraction failed: {e}")
        return None


def _extract_credit_debit_note(text: str, bedrock, pages: list[int], doc_id: str) -> Optional[CreditDebitNoteRecord]:
    prompt = CREDIT_DEBIT_NOTE_PROMPT.format(text=text[:6000])
    data = bedrock.extract_json(prompt)
    if not data:
        return None
    try:
        return CreditDebitNoteRecord(
            note_number=str(data.get("note_number", "")),
            note_type=str(data.get("note_type", "")),
            referenced_doc=str(data.get("referenced_doc", "")),
            target_doc=str(data.get("target_doc", "")),
            reason=str(data.get("reason", "")),
            amount=safe_decimal(data.get("amount")),
            source_pages=pages,
            doc_id=doc_id,
            raw_text=text,
        )
    except Exception as e:
        log.error(f"Credit/debit note extraction failed: {e}")
        return None
