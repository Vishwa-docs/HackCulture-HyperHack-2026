"""Tests for balance drift detection."""
import json
from src.normalization.money import parse_money, money_equal
from decimal import Decimal


def test_balance_drift_detection():
    """Test that balance drift is detected between consecutive months."""
    from src.detectors.evil.balance_drift import BalanceDriftDetector

    class MockStore:
        def query(self, sql, params=None):
            return [
                {
                    "statement_id": "STMT-APR",
                    "statement_month": "2025-04",
                    "account_number": "ACCT001",
                    "opening_balance": "50000.00",
                    "closing_balance": "45000.00",
                    "source_pages": "[100, 101]",
                    "transactions_json": "[]"
                },
                {
                    "statement_id": "STMT-MAY",
                    "statement_month": "2025-05",
                    "account_number": "ACCT001",
                    "opening_balance": "45100.00",  # Drift of 100 from April closing
                    "closing_balance": "42000.00",
                    "source_pages": "[110, 111]",
                    "transactions_json": "[]"
                },
            ]

    detector = BalanceDriftDetector()
    findings = detector.detect(MockStore())

    assert len(findings) == 1
    assert findings[0].category == "balance_drift"
    assert "drift" in findings[0].description.lower() or "Drift" in findings[0].description


def test_no_drift():
    """Test that matching balances produce no findings."""
    from src.detectors.evil.balance_drift import BalanceDriftDetector

    class MockStore:
        def query(self, sql, params=None):
            return [
                {
                    "statement_id": "STMT-APR",
                    "statement_month": "2025-04",
                    "account_number": "ACCT001",
                    "opening_balance": "50000.00",
                    "closing_balance": "45000.00",
                    "source_pages": "[100]",
                    "transactions_json": "[]"
                },
                {
                    "statement_id": "STMT-MAY",
                    "statement_month": "2025-05",
                    "account_number": "ACCT001",
                    "opening_balance": "45000.00",
                    "closing_balance": "42000.00",
                    "source_pages": "[110]",
                    "transactions_json": "[]"
                },
            ]

    detector = BalanceDriftDetector()
    findings = detector.detect(MockStore())
    assert len(findings) == 0
