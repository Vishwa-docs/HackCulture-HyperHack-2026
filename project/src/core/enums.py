"""Category enums and constants."""
from enum import Enum


class Category(str, Enum):
    # Easy
    ARITHMETIC_ERROR = "arithmetic_error"
    BILLING_TYPO = "billing_typo"
    DUPLICATE_LINE_ITEM = "duplicate_line_item"
    INVALID_DATE = "invalid_date"
    WRONG_TAX_RATE = "wrong_tax_rate"
    # Medium
    PO_INVOICE_MISMATCH = "po_invoice_mismatch"
    VENDOR_NAME_TYPO = "vendor_name_typo"
    DOUBLE_PAYMENT = "double_payment"
    IFSC_MISMATCH = "ifsc_mismatch"
    DUPLICATE_EXPENSE = "duplicate_expense"
    DATE_CASCADE = "date_cascade"
    GSTIN_STATE_MISMATCH = "gstin_state_mismatch"
    # Evil
    QUANTITY_ACCUMULATION = "quantity_accumulation"
    PRICE_ESCALATION = "price_escalation"
    BALANCE_DRIFT = "balance_drift"
    CIRCULAR_REFERENCE = "circular_reference"
    TRIPLE_EXPENSE_CLAIM = "triple_expense_claim"
    EMPLOYEE_ID_COLLISION = "employee_id_collision"
    FAKE_VENDOR = "fake_vendor"
    PHANTOM_PO_REFERENCE = "phantom_po_reference"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    EVIL = "evil"


CATEGORY_DIFFICULTY = {
    Category.ARITHMETIC_ERROR: Difficulty.EASY,
    Category.BILLING_TYPO: Difficulty.EASY,
    Category.DUPLICATE_LINE_ITEM: Difficulty.EASY,
    Category.INVALID_DATE: Difficulty.EASY,
    Category.WRONG_TAX_RATE: Difficulty.EASY,
    Category.PO_INVOICE_MISMATCH: Difficulty.MEDIUM,
    Category.VENDOR_NAME_TYPO: Difficulty.MEDIUM,
    Category.DOUBLE_PAYMENT: Difficulty.MEDIUM,
    Category.IFSC_MISMATCH: Difficulty.MEDIUM,
    Category.DUPLICATE_EXPENSE: Difficulty.MEDIUM,
    Category.DATE_CASCADE: Difficulty.MEDIUM,
    Category.GSTIN_STATE_MISMATCH: Difficulty.MEDIUM,
    Category.QUANTITY_ACCUMULATION: Difficulty.EVIL,
    Category.PRICE_ESCALATION: Difficulty.EVIL,
    Category.BALANCE_DRIFT: Difficulty.EVIL,
    Category.CIRCULAR_REFERENCE: Difficulty.EVIL,
    Category.TRIPLE_EXPENSE_CLAIM: Difficulty.EVIL,
    Category.EMPLOYEE_ID_COLLISION: Difficulty.EVIL,
    Category.FAKE_VENDOR: Difficulty.EVIL,
    Category.PHANTOM_PO_REFERENCE: Difficulty.EVIL,
}


class DocType(str, Enum):
    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"
    BANK_STATEMENT = "bank_statement"
    EXPENSE_REPORT = "expense_report"
    CREDIT_NOTE = "credit_note"
    DEBIT_NOTE = "debit_note"
    RECEIPT = "receipt"
    QUOTATION = "quotation"
    DELIVERY_NOTE = "delivery_note"
    VENDOR_MASTER = "vendor_master"
    TERMS_CONDITIONS = "terms_conditions"
    FILLER = "filler"
    UNKNOWN = "unknown"
