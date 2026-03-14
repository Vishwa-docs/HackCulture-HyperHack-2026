"""LangChain tools wrapping each detection category.

Each tool encapsulates the rule-based detection logic from run_detection.py
and returns structured JSON results that the detection agents consume.
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from ..core.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Shared data store – set by the orchestrator before agents run
# ---------------------------------------------------------------------------
_data_store: dict[str, Any] = {}


def set_data_store(
    invoices: list,
    pos: list,
    bank_stmts: list,
    expense_reports: list,
    credit_debit_notes: list,
    vendors: list,
):
    """Populate the shared data store so tools can access extracted data."""
    _data_store["invoices"] = invoices
    _data_store["pos"] = pos
    _data_store["bank_stmts"] = bank_stmts
    _data_store["expense_reports"] = expense_reports
    _data_store["credit_debit_notes"] = credit_debit_notes
    _data_store["vendors"] = vendors


def _get(key: str):
    return _data_store.get(key, [])


# ---------------------------------------------------------------------------
# We dynamically import the detector functions from run_detection at runtime
# to avoid circular imports & keep this module thin.
# ---------------------------------------------------------------------------
_detector_module = None


def _get_detector_module():
    """Lazy-import the run_detection module (standalone script)."""
    global _detector_module
    if _detector_module is None:
        import importlib.util, pathlib
        spec = importlib.util.spec_from_file_location(
            "run_detection",
            pathlib.Path(__file__).parent.parent.parent / "scripts" / "run_detection.py",
        )
        _detector_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_detector_module)
    return _detector_module


def _run_detector(fn_name: str, *args) -> str:
    """Run a detector function by name and return JSON results."""
    mod = _get_detector_module()
    fn = getattr(mod, fn_name)
    results = fn(*args)
    return json.dumps(results, indent=2, default=str)


# ---- Easy-tier tools ----

@tool
def detect_arithmetic_errors(query: str = "") -> str:
    """Scan all invoices for arithmetic errors: qty×rate≠amount, subtotal≠sum(items), grand-total mismatches.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_arithmetic_error", _get("invoices"))


@tool
def detect_billing_typos(query: str = "") -> str:
    """Scan all invoices for billing typos: transposed digits, misspelled vendor names on invoices.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_billing_typo", _get("invoices"))


@tool
def detect_duplicate_line_items(query: str = "") -> str:
    """Scan invoices for duplicate line items within a single invoice.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_duplicate_line_item", _get("invoices"))


@tool
def detect_invalid_dates(query: str = "") -> str:
    """Scan all documents for impossible or invalid dates (e.g. Feb 30, month>12).
    Returns JSON list of candidate findings."""
    return _run_detector("detect_invalid_date", _get("invoices"), _get("pos"), _get("expense_reports"))


@tool
def detect_wrong_tax_rates(query: str = "") -> str:
    """Scan invoices for tax-rate errors by validating against HSN/SAC standard rates.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_wrong_tax_rate", _get("invoices"))


# ---- Medium-tier tools ----

@tool
def detect_po_invoice_mismatches(query: str = "") -> str:
    """Cross-reference invoices against their purchase orders using HSN codes.
    Flags qty, rate, or description mismatches.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_po_invoice_mismatch", _get("invoices"), _get("pos"))


@tool
def detect_vendor_name_typos(query: str = "") -> str:
    """Compare invoice vendor names against the vendor master using fuzzy matching.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_vendor_name_typo", _get("invoices"), _get("vendors"))


@tool
def detect_double_payments(query: str = "") -> str:
    """Scan bank statements for duplicate payment entries (same amount, beneficiary, close dates).
    Returns JSON list of candidate findings."""
    return _run_detector("detect_double_payment", _get("bank_stmts"))


@tool
def detect_ifsc_mismatches(query: str = "") -> str:
    """Detect IFSC code anomalies using per-vendor outlier analysis.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_ifsc_mismatch", _get("invoices"), _get("vendors"))


@tool
def detect_duplicate_expenses(query: str = "") -> str:
    """Find duplicate entries in expense reports.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_duplicate_expense", _get("expense_reports"))


@tool
def detect_date_cascades(query: str = "") -> str:
    """Detect date cascade anomalies: invoice dates preceding PO dates.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_date_cascade", _get("invoices"), _get("pos"))


@tool
def detect_gstin_state_mismatches(query: str = "") -> str:
    """Validate GSTIN state codes against vendor master addresses.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_gstin_state_mismatch", _get("invoices"), _get("vendors"))


# ---- Evil-tier tools ----

@tool
def detect_quantity_accumulations(query: str = "") -> str:
    """Cross-check cumulative quantities invoiced vs PO quantities using HSN matching.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_quantity_accumulation", _get("invoices"), _get("pos"))


@tool
def detect_price_escalations(query: str = "") -> str:
    """Detect price escalations where invoice rates exceed PO-agreed rates.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_price_escalation", _get("invoices"), _get("pos"))


@tool
def detect_balance_drifts(query: str = "") -> str:
    """Analyze bank statement sequences for balance continuity errors.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_balance_drift", _get("bank_stmts"))


@tool
def detect_circular_references(query: str = "") -> str:
    """Find circular reference chains among credit/debit notes.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_circular_reference", _get("credit_debit_notes"))


@tool
def detect_triple_expense_claims(query: str = "") -> str:
    """Identify expenses claimed three or more times across reports.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_triple_expense_claim", _get("expense_reports"))


@tool
def detect_employee_id_collisions(query: str = "") -> str:
    """Find employee ID collisions in expense reports.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_employee_id_collision", _get("expense_reports"))


@tool
def detect_fake_vendors(query: str = "") -> str:
    """Identify potentially fake vendors using fuzzy name matching against vendor master.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_fake_vendor", _get("invoices"), _get("vendors"))


@tool
def detect_phantom_po_references(query: str = "") -> str:
    """Find invoices referencing PO numbers that don't exist.
    Returns JSON list of candidate findings."""
    return _run_detector("detect_phantom_po_reference", _get("invoices"), _get("pos"))


# ---------------------------------------------------------------------------
# Convenience: all tools grouped by tier
# ---------------------------------------------------------------------------
EASY_TOOLS = [
    detect_arithmetic_errors,
    detect_billing_typos,
    detect_duplicate_line_items,
    detect_invalid_dates,
    detect_wrong_tax_rates,
]

MEDIUM_TOOLS = [
    detect_po_invoice_mismatches,
    detect_vendor_name_typos,
    detect_double_payments,
    detect_ifsc_mismatches,
    detect_duplicate_expenses,
    detect_date_cascades,
    detect_gstin_state_mismatches,
]

EVIL_TOOLS = [
    detect_quantity_accumulations,
    detect_price_escalations,
    detect_balance_drifts,
    detect_circular_references,
    detect_triple_expense_claims,
    detect_employee_id_collisions,
    detect_fake_vendors,
    detect_phantom_po_references,
]

ALL_TOOLS = EASY_TOOLS + MEDIUM_TOOLS + EVIL_TOOLS
