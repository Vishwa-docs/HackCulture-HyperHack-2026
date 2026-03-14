"""PO-Invoice mismatch detector: qty or rate differs from linked PO."""
import json
from decimal import Decimal
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...normalization.money import parse_money, format_money, money_equal
from ...normalization.ids import normalize_po_number

log = get_logger(__name__)


class POInvoiceMismatchDetector(BaseDetector):
    category = Category.PO_INVOICE_MISMATCH
    name = "po_invoice_mismatch"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        invoices = store.query("SELECT * FROM invoices WHERE po_number IS NOT NULL AND po_number != ''")
        pos = store.query("SELECT * FROM purchase_orders")

        # Build PO lookup
        po_lookup = {}
        for po in pos:
            po_num = normalize_po_number(po["po_number"])
            po_lookup[po_num] = po
            # Also store unnormalized
            po_lookup[po["po_number"]] = po

        for inv in invoices:
            inv_num = inv["invoice_number"]
            po_ref = inv.get("po_number", "")
            if not po_ref:
                continue

            po_norm = normalize_po_number(po_ref)
            po = po_lookup.get(po_norm) or po_lookup.get(po_ref)
            if not po:
                continue

            inv_pages = json.loads(inv.get("source_pages", "[]"))
            po_pages = json.loads(po.get("source_pages", "[]"))
            inv_items = json.loads(inv.get("line_items_json", "[]"))
            po_items = json.loads(po.get("line_items_json", "[]"))

            # Compare line items by description matching
            for inv_li in inv_items:
                inv_desc = str(inv_li.get("description", "")).strip().lower()
                inv_qty = parse_money(inv_li.get("quantity"))
                inv_rate = parse_money(inv_li.get("unit_rate"))

                for po_li in po_items:
                    po_desc = str(po_li.get("description", "")).strip().lower()
                    if not inv_desc or not po_desc:
                        continue

                    # Simple description matching
                    if inv_desc == po_desc or (len(inv_desc) > 10 and inv_desc in po_desc) or (len(po_desc) > 10 and po_desc in inv_desc):
                        po_qty = parse_money(po_li.get("quantity"))
                        po_rate = parse_money(po_li.get("unit_rate"))

                        # Check qty mismatch
                        if inv_qty is not None and po_qty is not None and not money_equal(inv_qty, po_qty):
                            findings.append(self.make_finding(
                                pages=inv_pages,
                                document_refs=[inv_num, po["po_number"]],
                                description=f"Invoice qty ({inv_qty}) differs from PO qty ({po_qty}) for '{inv_li.get('description', '')}'",
                                reported_value=str(inv_qty),
                                correct_value=str(po_qty),
                                confidence=0.82,
                            ))

                        # Check rate mismatch
                        if inv_rate is not None and po_rate is not None and not money_equal(inv_rate, po_rate):
                            findings.append(self.make_finding(
                                pages=inv_pages,
                                document_refs=[inv_num, po["po_number"]],
                                description=f"Invoice rate ({format_money(inv_rate)}) differs from PO rate ({format_money(po_rate)}) for '{inv_li.get('description', '')}'",
                                reported_value=format_money(inv_rate),
                                correct_value=format_money(po_rate),
                                confidence=0.82,
                            ))

        log.info(f"POInvoiceMismatch: found {len(findings)} candidates")
        return findings
