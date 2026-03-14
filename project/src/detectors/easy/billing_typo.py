"""Billing typo detector: time decimal confusion (0.15 = 15 min, not 0.15 hrs)."""
import json
from decimal import Decimal
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...normalization.money import parse_money, format_money

log = get_logger(__name__)

# Values that suggest HH.MM time format misinterpretation
SUSPICIOUS_DECIMALS = {
    Decimal("0.15"): Decimal("0.25"),    # 15 min = 0.25 hrs
    Decimal("0.30"): Decimal("0.50"),    # 30 min = 0.50 hrs
    Decimal("0.45"): Decimal("0.75"),    # 45 min = 0.75 hrs
    Decimal("1.15"): Decimal("1.25"),    # 1h15m = 1.25 hrs
    Decimal("1.30"): Decimal("1.50"),    # 1h30m = 1.50 hrs
    Decimal("1.45"): Decimal("1.75"),    # 1h45m = 1.75 hrs
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


class BillingTypoDetector(BaseDetector):
    category = Category.BILLING_TYPO
    name = "billing_typo"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        invoices = store.query("SELECT * FROM invoices")

        for inv in invoices:
            inv_num = inv["invoice_number"]
            pages = json.loads(inv.get("source_pages", "[]"))
            line_items = json.loads(inv.get("line_items_json", "[]"))

            for li in line_items:
                qty = parse_money(li.get("quantity"))
                rate = parse_money(li.get("unit_rate"))
                amount = parse_money(li.get("amount"))
                desc = str(li.get("description", "")).lower()

                if qty is None or rate is None or amount is None:
                    continue

                # Check if qty looks like a time value with HH.MM confusion
                if qty in SUSPICIOUS_DECIMALS:
                    correct_qty = SUSPICIOUS_DECIMALS[qty]
                    # The billed amount uses the wrong interpretation
                    wrong_amount = qty * rate
                    correct_amount = correct_qty * rate

                    # If the document amount matches the wrong calculation
                    if abs(amount - wrong_amount) < Decimal("0.02"):
                        findings.append(self.make_finding(
                            pages=pages,
                            document_refs=[inv_num],
                            description=f"Line {li.get('line_num', '?')}: quantity {qty} appears to be time in HH:MM format ({int(qty)}h{int((qty%1)*100)}m = {correct_qty} decimal hours). Billed {format_money(amount)} but should be {format_money(correct_amount)}",
                            reported_value=format_money(amount),
                            correct_value=format_money(correct_amount),
                            confidence=0.88,
                        ))

        log.info(f"BillingTypo: found {len(findings)} candidates")
        return findings
