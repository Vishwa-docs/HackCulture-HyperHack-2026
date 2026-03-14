"""Tests for quantity accumulation detection."""
import json


def test_quantity_accumulation():
    """Test detection of cumulative qty exceeding PO qty by >20%."""
    from src.detectors.evil.quantity_accumulation import QuantityAccumulationDetector

    class MockStore:
        def query(self, sql, params=None):
            if "purchase_orders" in sql:
                return [{
                    "po_number": "PO-2025-0001",
                    "source_pages": "[5]",
                    "line_items_json": json.dumps([{
                        "description": "Widget A",
                        "quantity": "100",
                        "unit_rate": "50.00",
                        "amount": "5000.00"
                    }])
                }]
            elif "invoices" in sql:
                invoices = []
                for i in range(4):
                    invoices.append({
                        "invoice_number": f"INV-2025-{i+1:04d}",
                        "po_number": "PO-2025-0001",
                        "source_pages": f"[{10+i*5}]",
                        "line_items_json": json.dumps([{
                            "description": "Widget A",
                            "quantity": "35",  # 4 x 35 = 140, which is 140% of 100
                            "unit_rate": "50.00",
                            "amount": "1750.00"
                        }])
                    })
                return invoices
            return []

    detector = QuantityAccumulationDetector()
    findings = detector.detect(MockStore())

    assert len(findings) == 1
    assert findings[0].category == "quantity_accumulation"
    assert "140" in findings[0].reported_value or "140" in findings[0].description
