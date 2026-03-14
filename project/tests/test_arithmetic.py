"""Tests for arithmetic error detector."""
import pytest
import json
from decimal import Decimal
from unittest.mock import MagicMock


class MockStore:
    """Mock DuckDB store for testing."""
    def __init__(self, invoices=None):
        self._invoices = invoices or []

    def query(self, sql, params=None):
        if "invoices" in sql:
            return self._invoices
        return []


def test_arithmetic_qty_times_rate():
    """Test detection of qty * rate != amount."""
    from src.detectors.easy.arithmetic_error import ArithmeticErrorDetector

    invoices = [{
        "invoice_number": "INV-2025-0001",
        "source_pages": "[10]",
        "line_items_json": json.dumps([{
            "line_num": 1,
            "description": "Test item",
            "quantity": "10",
            "unit_rate": "100.00",
            "amount": "1100.00",  # Should be 1000.00
        }]),
        "subtotal": None,
        "tax_amount": None,
        "tax_rate": None,
        "grand_total": None,
    }]

    store = MockStore(invoices)
    detector = ArithmeticErrorDetector()
    findings = detector.detect(store)

    assert len(findings) == 1
    assert findings[0].category == "arithmetic_error"
    assert findings[0].correct_value == "1000.00"
    assert findings[0].reported_value == "1100.00"


def test_arithmetic_subtotal_mismatch():
    """Test detection of subtotal != sum(line items)."""
    from src.detectors.easy.arithmetic_error import ArithmeticErrorDetector

    invoices = [{
        "invoice_number": "INV-2025-0002",
        "source_pages": "[20]",
        "line_items_json": json.dumps([
            {"line_num": 1, "quantity": "5", "unit_rate": "100", "amount": "500"},
            {"line_num": 2, "quantity": "3", "unit_rate": "200", "amount": "600"},
        ]),
        "subtotal": "1200.00",  # Should be 1100.00
        "tax_amount": None,
        "tax_rate": None,
        "grand_total": None,
    }]

    store = MockStore(invoices)
    detector = ArithmeticErrorDetector()
    findings = detector.detect(store)

    # Should find subtotal mismatch
    subtotal_findings = [f for f in findings if "Subtotal" in f.description]
    assert len(subtotal_findings) == 1
    assert subtotal_findings[0].correct_value == "1100.00"


def test_no_false_positive():
    """Test that correct invoice produces no findings."""
    from src.detectors.easy.arithmetic_error import ArithmeticErrorDetector

    invoices = [{
        "invoice_number": "INV-2025-0003",
        "source_pages": "[30]",
        "line_items_json": json.dumps([
            {"line_num": 1, "quantity": "10", "unit_rate": "100", "amount": "1000"},
        ]),
        "subtotal": "1000.00",
        "tax_amount": "180.00",
        "tax_rate": "18",
        "grand_total": "1180.00",
    }]

    store = MockStore(invoices)
    detector = ArithmeticErrorDetector()
    findings = detector.detect(store)
    assert len(findings) == 0
