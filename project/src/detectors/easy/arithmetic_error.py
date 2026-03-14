"""Arithmetic error detector: qty*rate!=amount, subtotal!=sum(items), etc."""
import json
from decimal import Decimal
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...normalization.money import parse_money, money_equal, format_money

log = get_logger(__name__)


class ArithmeticErrorDetector(BaseDetector):
    category = Category.ARITHMETIC_ERROR
    name = "arithmetic_error"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        invoices = store.query("SELECT * FROM invoices")

        for inv in invoices:
            inv_num = inv["invoice_number"]
            pages = json.loads(inv.get("source_pages", "[]"))
            line_items = json.loads(inv.get("line_items_json", "[]"))

            # Check 1: qty * rate = amount for each line item
            for li in line_items:
                qty = parse_money(li.get("quantity"))
                rate = parse_money(li.get("unit_rate"))
                amount = parse_money(li.get("amount"))
                if qty is not None and rate is not None and amount is not None:
                    expected = qty * rate
                    if not money_equal(expected, amount):
                        findings.append(self.make_finding(
                            pages=pages,
                            document_refs=[inv_num],
                            description=f"Line item {li.get('line_num', '?')}: qty({qty}) × rate({rate}) = {format_money(expected)}, but document shows {format_money(amount)}",
                            reported_value=format_money(amount),
                            correct_value=format_money(expected),
                            confidence=0.95,
                        ))

            # Check 2: subtotal = sum of line item amounts
            # Only flag if the difference is small (likely a real error, not missing items)
            subtotal = parse_money(inv.get("subtotal"))
            if subtotal is not None and line_items and subtotal > 0:
                amounts = [parse_money(li.get("amount")) for li in line_items]
                amounts = [a for a in amounts if a is not None]
                if amounts:
                    expected_subtotal = sum(amounts, Decimal("0"))
                    diff = abs(expected_subtotal - subtotal)
                    # Only flag if sum is close to subtotal (within 20% of subtotal)
                    # Large differences suggest incomplete extraction, not errors
                    if diff > Decimal("0.01") and diff < subtotal * Decimal("0.20"):
                        if not money_equal(expected_subtotal, subtotal):
                            findings.append(self.make_finding(
                                pages=pages,
                                document_refs=[inv_num],
                                description=f"Subtotal should be {format_money(expected_subtotal)} (sum of line items), but document shows {format_money(subtotal)}",
                                reported_value=format_money(subtotal),
                                correct_value=format_money(expected_subtotal),
                                confidence=0.93,
                            ))

            # Check 3: tax = subtotal * tax_rate
            tax_amount = parse_money(inv.get("tax_amount"))
            tax_rate = parse_money(inv.get("tax_rate"))
            if subtotal is not None and tax_amount is not None and tax_rate is not None and tax_rate > 0:
                expected_tax = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"))
                if not money_equal(expected_tax, tax_amount, Decimal("0.50")):
                    findings.append(self.make_finding(
                        pages=pages,
                        document_refs=[inv_num],
                        description=f"Tax amount should be {format_money(expected_tax)} ({tax_rate}% of {format_money(subtotal)}), but document shows {format_money(tax_amount)}",
                        reported_value=format_money(tax_amount),
                        correct_value=format_money(expected_tax),
                        confidence=0.90,
                    ))

            # Check 4: grand_total = subtotal + tax
            grand_total = parse_money(inv.get("grand_total"))
            if subtotal is not None and tax_amount is not None and grand_total is not None:
                expected_grand = subtotal + tax_amount
                if not money_equal(expected_grand, grand_total):
                    findings.append(self.make_finding(
                        pages=pages,
                        document_refs=[inv_num],
                        description=f"Grand total should be {format_money(expected_grand)} (subtotal + tax), but document shows {format_money(grand_total)}",
                        reported_value=format_money(grand_total),
                        correct_value=format_money(expected_grand),
                        confidence=0.94,
                    ))

        log.info(f"ArithmeticError: found {len(findings)} candidates")
        return findings
