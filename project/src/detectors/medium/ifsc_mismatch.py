"""IFSC mismatch detector: invoice bank IFSC differs from Vendor Master."""
import json
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...normalization.vendors import find_best_vendor_match, match_vendor_by_gstin

log = get_logger(__name__)


class IFSCMismatchDetector(BaseDetector):
    category = Category.IFSC_MISMATCH
    name = "ifsc_mismatch"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        if not vendors:
            return findings

        invoices = store.query("SELECT * FROM invoices WHERE bank_ifsc IS NOT NULL AND bank_ifsc != ''")
        for inv in invoices:
            inv_num = inv["invoice_number"]
            inv_ifsc = inv.get("bank_ifsc", "").strip().upper()
            vendor_raw = inv.get("vendor_name_raw", "")
            gstin = inv.get("gstin_vendor", "")
            pages = json.loads(inv.get("source_pages", "[]"))

            if not inv_ifsc:
                continue

            # Find the vendor
            vendor = None
            if gstin:
                vendor = match_vendor_by_gstin(gstin, vendors)
            if not vendor:
                vendor, _ = find_best_vendor_match(vendor_raw, vendors, threshold=75)

            if vendor and vendor.ifsc:
                master_ifsc = vendor.ifsc.strip().upper()
                # Normalize both to standard 11-char IFSC for comparison
                inv_ifsc_norm = inv_ifsc[:11]
                master_ifsc_norm = master_ifsc[:11]
                if inv_ifsc_norm != master_ifsc_norm:
                    findings.append(self.make_finding(
                        pages=pages,
                        document_refs=[inv_num],
                        description=f"Invoice IFSC '{inv_ifsc}' does not match Vendor Master IFSC '{master_ifsc_norm}' for vendor '{vendor.canonical_name}'",
                        reported_value=inv_ifsc,
                        correct_value=master_ifsc_norm,
                        confidence=0.88,
                    ))

        log.info(f"IFSCMismatch: found {len(findings)} candidates")
        return findings
