"""Pydantic data models for all entities in the pipeline."""
from __future__ import annotations
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field
from .enums import Category, DocType


class LineItem(BaseModel):
    line_num: int = 0
    description: str = ""
    hsn_sac: str = ""
    quantity: Optional[Decimal] = None
    unit: str = ""
    unit_rate: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    total: Optional[Decimal] = None


class PageRecord(BaseModel):
    page_num: int
    page_text: str = ""
    rendered_image_path: str = ""
    split_doc_id: str = ""
    parser_source: str = ""
    parse_confidence: float = 0.0


class DocumentRecord(BaseModel):
    doc_id: str
    doc_type: DocType = DocType.UNKNOWN
    page_start: int = 0
    page_end: int = 0
    doc_refs: list[str] = Field(default_factory=list)
    classification_confidence: float = 0.0
    raw_title: str = ""
    canonical_title: str = ""
    raw_text: str = ""


class VendorRecord(BaseModel):
    vendor_id: str = ""
    raw_name: str = ""
    canonical_name: str = ""
    gstin: str = ""
    ifsc: str = ""
    state: str = ""
    pan: str = ""
    bank_account: str = ""
    source_pages: list[int] = Field(default_factory=list)


class InvoiceRecord(BaseModel):
    invoice_number: str = ""
    vendor_name_raw: str = ""
    vendor_id: str = ""
    invoice_date: str = ""
    due_date: str = ""
    po_number: str = ""
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    grand_total: Optional[Decimal] = None
    gst_rate: Optional[Decimal] = None
    gstin_vendor: str = ""
    gstin_buyer: str = ""
    bank_ifsc: str = ""
    bank_account: str = ""
    currency: str = "INR"
    source_pages: list[int] = Field(default_factory=list)
    doc_id: str = ""
    raw_text: str = ""
    extraction_confidence: float = 0.0


class PurchaseOrderRecord(BaseModel):
    po_number: str = ""
    vendor_name_raw: str = ""
    vendor_id: str = ""
    po_date: str = ""
    delivery_date: str = ""
    gstin_vendor: str = ""
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    grand_total: Optional[Decimal] = None
    source_pages: list[int] = Field(default_factory=list)
    doc_id: str = ""
    raw_text: str = ""


class BankStatementTxn(BaseModel):
    statement_id: str = ""
    statement_month: str = ""
    account_number_masked: str = ""
    txn_date: str = ""
    reference: str = ""
    description: str = ""
    debit: Optional[Decimal] = None
    credit: Optional[Decimal] = None
    balance: Optional[Decimal] = None
    vendor_candidate: str = ""
    source_pages: list[int] = Field(default_factory=list)
    doc_id: str = ""


class BankStatement(BaseModel):
    statement_id: str = ""
    statement_month: str = ""
    account_number_masked: str = ""
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    transactions: list[BankStatementTxn] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    doc_id: str = ""
    raw_text: str = ""


class ExpenseLine(BaseModel):
    line_num: int = 0
    date: str = ""
    description: str = ""
    category: str = ""
    merchant: str = ""
    amount: Optional[Decimal] = None
    receipt_ref: str = ""


class ExpenseReportRecord(BaseModel):
    report_id: str = ""
    employee_name: str = ""
    employee_id: str = ""
    department: str = ""
    expense_lines: list[ExpenseLine] = Field(default_factory=list)
    hotel_name: str = ""
    stay_start: str = ""
    stay_end: str = ""
    total_amount: Optional[Decimal] = None
    source_pages: list[int] = Field(default_factory=list)
    doc_id: str = ""
    raw_text: str = ""


class CreditDebitNoteRecord(BaseModel):
    note_number: str = ""
    note_type: str = ""  # "credit" or "debit"
    vendor_name_raw: str = ""
    gstin_vendor: str = ""
    referenced_doc: str = ""
    target_doc: str = ""
    reason: str = ""
    amount: Optional[Decimal] = None
    linked_documents: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    doc_id: str = ""
    raw_text: str = ""


class FindingCandidate(BaseModel):
    finding_id: str = ""
    category: str = ""
    pages: list[int] = Field(default_factory=list)
    document_refs: list[str] = Field(default_factory=list)
    description: str = ""
    reported_value: str = ""
    correct_value: str = ""
    confidence: float = 0.0
    evidence_refs: list[str] = Field(default_factory=list)
    detector_name: str = ""
    status: str = "candidate"  # candidate, accepted, rejected
    rejection_reason: str = ""


class SubmissionOutput(BaseModel):
    team_id: str
    findings: list[FindingCandidate] = Field(default_factory=list)
