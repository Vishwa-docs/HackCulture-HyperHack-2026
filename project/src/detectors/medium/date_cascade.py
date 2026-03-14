"""Date cascade detector: invoice date before its own PO date."""
import json
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...normalization.dates import parse_date
from ...normalization.ids import normalize_po_number

log = get_logger(__name__)


class DateCascadeDetector(BaseDetector):
    category = Category.DATE_CASCADE
    name = "date_cascade"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        invoices = store.query("SELECT * FROM invoices WHERE po_number IS NOT NULL AND po_number != ''")
        pos = store.query("SELECT * FROM purchase_orders")

        po_lookup = {}
        for po in pos:
            po_lookup[normalize_po_number(po["po_number"])] = po
            po_lookup[po["po_number"]] = po

        for inv in invoices:
            inv_num = inv["invoice_number"]
            po_ref = inv.get("po_number", "")
            inv_date_str = inv.get("invoice_date", "")
            pages = json.loads(inv.get("source_pages", "[]"))

            if not po_ref or not inv_date_str:
                continue

            po = po_lookup.get(normalize_po_number(po_ref)) or po_lookup.get(po_ref)
            if not po:
                continue

            po_date_str = po.get("po_date", "")
            if not po_date_str:
                continue

            inv_date = parse_date(inv_date_str)
            po_date = parse_date(po_date_str)

            if inv_date and po_date and inv_date < po_date:
                findings.append(self.make_finding(
                    pages=pages,
                    document_refs=[inv_num, po["po_number"]],
                    description=f"Invoice date ({inv_date_str}) is before PO date ({po_date_str}). Invoice cannot precede its Purchase Order.",
                    reported_value=inv_date_str,
                    correct_value=f"Should be on or after {po_date_str}",
                    confidence=0.87,
                ))

        log.info(f"DateCascade: found {len(findings)} candidates")
        return findings
