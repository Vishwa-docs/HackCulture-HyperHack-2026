"""Duplicate line item detector: same item duplicated within one invoice."""
import json
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...normalization.money import parse_money, format_money

log = get_logger(__name__)


def _line_signature(li: dict) -> str:
    """Create a matching signature for a line item."""
    desc = str(li.get("description", "")).strip().lower()
    qty = str(li.get("quantity", ""))
    rate = str(li.get("unit_rate", ""))
    amount = str(li.get("amount", ""))
    return f"{desc}|{qty}|{rate}|{amount}"


class DuplicateLineItemDetector(BaseDetector):
    category = Category.DUPLICATE_LINE_ITEM
    name = "duplicate_line_item"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        invoices = store.query("SELECT * FROM invoices")

        for inv in invoices:
            inv_num = inv["invoice_number"]
            pages = json.loads(inv.get("source_pages", "[]"))
            line_items = json.loads(inv.get("line_items_json", "[]"))

            if len(line_items) < 2:
                continue

            # Build signatures
            sigs = {}
            for li in line_items:
                sig = _line_signature(li)
                if sig not in sigs:
                    sigs[sig] = []
                sigs[sig].append(li)

            # Find duplicates
            for sig, items in sigs.items():
                if len(items) > 1:
                    amount = parse_money(items[0].get("amount"))
                    dup_count = len(items) - 1
                    inflation = format_money(amount * dup_count) if amount else "unknown"
                    desc = items[0].get("description", "unknown item")

                    findings.append(self.make_finding(
                        pages=pages,
                        document_refs=[inv_num],
                        description=f"Line item '{desc}' appears {len(items)} times. {dup_count} duplicate(s) inflating total by {inflation}",
                        reported_value=f"{len(items)} occurrences",
                        correct_value="1 occurrence",
                        confidence=0.92,
                    ))

        log.info(f"DuplicateLineItem: found {len(findings)} candidates")
        return findings
