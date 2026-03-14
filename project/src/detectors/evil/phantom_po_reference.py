"""Phantom PO reference detector: invoice cites a PO that doesn't exist."""
import json
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...normalization.ids import normalize_po_number
from rapidfuzz import fuzz

log = get_logger(__name__)


class PhantomPOReferenceDetector(BaseDetector):
    category = Category.PHANTOM_PO_REFERENCE
    name = "phantom_po_reference"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []

        # Build authoritative PO index
        pos = store.query("SELECT po_number FROM purchase_orders")
        po_set = set()
        po_norm_set = set()
        for po in pos:
            po_num = po["po_number"]
            po_set.add(po_num)
            po_norm_set.add(normalize_po_number(po_num))

        # Check all invoice PO references
        invoices = store.query("SELECT * FROM invoices WHERE po_number IS NOT NULL AND po_number != ''")
        for inv in invoices:
            inv_num = inv["invoice_number"]
            po_ref = inv.get("po_number", "")
            pages = json.loads(inv.get("source_pages", "[]"))

            if not po_ref:
                continue

            po_norm = normalize_po_number(po_ref)

            # Exact match
            if po_ref in po_set or po_norm in po_norm_set:
                continue

            # Fuzzy sanity check - maybe OCR error on a valid PO
            is_near_match = False
            for valid_po in po_norm_set:
                if fuzz.ratio(po_norm, valid_po) > 90:
                    is_near_match = True
                    break

            if not is_near_match:
                findings.append(self.make_finding(
                    pages=pages,
                    document_refs=[inv_num],
                    description=f"Invoice references PO '{po_ref}' which does not exist in any Purchase Order document",
                    reported_value=po_ref,
                    correct_value="PO number not found in corpus",
                    confidence=0.78,
                ))

        log.info(f"PhantomPOReference: found {len(findings)} candidates")
        return findings
