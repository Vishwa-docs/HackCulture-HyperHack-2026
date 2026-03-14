"""Quantity accumulation detector: cumulative invoiced qty exceeds PO qty by >20%."""
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


class QuantityAccumulationDetector(BaseDetector):
    category = Category.QUANTITY_ACCUMULATION
    name = "quantity_accumulation"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        invoices = store.query("SELECT * FROM invoices WHERE po_number IS NOT NULL AND po_number != ''")
        pos = store.query("SELECT * FROM purchase_orders")

        # Build PO item lookup: po_number -> description -> quantity
        po_items = {}
        po_lookup = {}
        for po in pos:
            po_num = normalize_po_number(po["po_number"])
            po_lookup[po_num] = po
            po_li = json.loads(po.get("line_items_json", "[]"))
            for li in po_li:
                desc = str(li.get("description", "")).strip().lower()
                qty = parse_money(li.get("quantity"))
                if desc and qty:
                    po_items.setdefault(po_num, {})[desc] = qty

        # Group invoices by PO and accumulate quantities
        inv_by_po = defaultdict(list)
        for inv in invoices:
            po_ref = normalize_po_number(inv.get("po_number", ""))
            inv_by_po[po_ref].append(inv)

        for po_num, inv_list in inv_by_po.items():
            if po_num not in po_items:
                continue
            if len(inv_list) < 2:
                continue

            # Accumulate quantities per line item description
            accum = defaultdict(lambda: {"total_qty": Decimal("0"), "invoices": [], "pages": []})

            for inv in inv_list:
                inv_num = inv["invoice_number"]
                inv_pages = json.loads(inv.get("source_pages", "[]"))
                inv_li = json.loads(inv.get("line_items_json", "[]"))

                for li in inv_li:
                    desc = str(li.get("description", "")).strip().lower()
                    qty = parse_money(li.get("quantity"))
                    if desc and qty:
                        accum[desc]["total_qty"] += qty
                        accum[desc]["invoices"].append(inv_num)
                        accum[desc]["pages"].extend(inv_pages)

            # Compare accumulated qty vs PO qty
            for desc, data in accum.items():
                po_qty = po_items.get(po_num, {}).get(desc)
                if po_qty is None:
                    # Try fuzzy match on descriptions
                    for po_desc, pq in po_items.get(po_num, {}).items():
                        if desc in po_desc or po_desc in desc:
                            po_qty = pq
                            break

                if po_qty and po_qty > 0:
                    ratio = data["total_qty"] / po_qty
                    if ratio > Decimal("1.20"):  # >20% over
                        invoice_refs = sorted(set(data["invoices"]))
                        po_data = po_lookup.get(po_num, {})
                        po_pages = json.loads(po_data.get("source_pages", "[]"))
                        all_pages = sorted(set(data["pages"] + po_pages))

                        findings.append(self.make_finding(
                            pages=all_pages,
                            document_refs=invoice_refs + [po_data.get("po_number", po_num)],
                            description=f"Cumulative qty ({data['total_qty']}) across {len(invoice_refs)} invoices exceeds PO qty ({po_qty}) by {(ratio-1)*100:.0f}% for item '{desc[:60]}'",
                            reported_value=str(data["total_qty"]),
                            correct_value=str(po_qty),
                            confidence=0.75,
                        ))

        log.info(f"QuantityAccumulation: found {len(findings)} candidates")
        return findings
