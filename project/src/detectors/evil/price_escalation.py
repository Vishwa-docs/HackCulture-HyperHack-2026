"""Price escalation detector: all invoices against a PO charge above PO contracted rate."""
import json
from decimal import Decimal
from collections import defaultdict
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...normalization.money import parse_money, format_money
from ...normalization.ids import normalize_po_number

log = get_logger(__name__)


class PriceEscalationDetector(BaseDetector):
    category = Category.PRICE_ESCALATION
    name = "price_escalation"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        invoices = store.query("SELECT * FROM invoices WHERE po_number IS NOT NULL AND po_number != ''")
        pos = store.query("SELECT * FROM purchase_orders")

        # Build PO rate lookup
        po_rates = {}
        po_lookup = {}
        for po in pos:
            po_num = normalize_po_number(po["po_number"])
            po_lookup[po_num] = po
            po_li = json.loads(po.get("line_items_json", "[]"))
            for li in po_li:
                desc = str(li.get("description", "")).strip().lower()
                rate = parse_money(li.get("unit_rate"))
                if desc and rate:
                    po_rates.setdefault(po_num, {})[desc] = rate

        # Group invoices by PO
        inv_by_po = defaultdict(list)
        for inv in invoices:
            po_ref = normalize_po_number(inv.get("po_number", ""))
            inv_by_po[po_ref].append(inv)

        for po_num, inv_list in inv_by_po.items():
            if po_num not in po_rates:
                continue
            if len(inv_list) < 2:
                continue

            # Check each line item description
            for desc, po_rate in po_rates.get(po_num, {}).items():
                escalated_invoices = []
                escalated_rates = []
                all_pages = []

                for inv in inv_list:
                    inv_num = inv["invoice_number"]
                    inv_pages = json.loads(inv.get("source_pages", "[]"))
                    inv_li = json.loads(inv.get("line_items_json", "[]"))

                    for li in inv_li:
                        inv_desc = str(li.get("description", "")).strip().lower()
                        inv_rate = parse_money(li.get("unit_rate"))

                        if inv_rate and (inv_desc == desc or desc in inv_desc or inv_desc in desc):
                            if inv_rate > po_rate:
                                escalated_invoices.append(inv_num)
                                escalated_rates.append(inv_rate)
                                all_pages.extend(inv_pages)
                            break

                # Flag if ALL invoices are above PO rate (minimum 3-4 invoices)
                if len(escalated_invoices) >= 3 and len(escalated_invoices) == len(inv_list):
                    po_data = po_lookup.get(po_num, {})
                    po_pages = json.loads(po_data.get("source_pages", "[]"))
                    avg_rate = sum(escalated_rates) / len(escalated_rates)

                    findings.append(self.make_finding(
                        pages=sorted(set(all_pages + po_pages)),
                        document_refs=sorted(set(escalated_invoices)) + [po_data.get("po_number", po_num)],
                        description=f"All {len(escalated_invoices)} invoices charge above PO rate ({format_money(po_rate)}) for '{desc[:60]}'. Average invoice rate: {format_money(avg_rate)}",
                        reported_value=f"Rates: {', '.join(format_money(r) for r in escalated_rates)}",
                        correct_value=format_money(po_rate),
                        confidence=0.72,
                    ))

        log.info(f"PriceEscalation: found {len(findings)} candidates")
        return findings
