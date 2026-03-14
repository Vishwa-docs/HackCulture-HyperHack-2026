"""Fake vendor detector: invoice vendor not in Vendor Master."""
import json
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...normalization.vendors import (
    find_best_vendor_match, match_vendor_by_gstin, match_vendor_by_ifsc
)

log = get_logger(__name__)


class FakeVendorDetector(BaseDetector):
    category = Category.FAKE_VENDOR
    name = "fake_vendor"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        if not vendors:
            return findings

        invoices = store.query("SELECT * FROM invoices")
        for inv in invoices:
            inv_num = inv["invoice_number"]
            vendor_raw = inv.get("vendor_name_raw", "")
            gstin = inv.get("gstin_vendor", "")
            ifsc = inv.get("bank_ifsc", "")
            pages = json.loads(inv.get("source_pages", "[]"))

            if not vendor_raw:
                continue

            # Try all matching methods
            match_found = False

            # 1. GSTIN match
            if gstin:
                v = match_vendor_by_gstin(gstin, vendors)
                if v:
                    match_found = True

            # 2. IFSC match
            if not match_found and ifsc:
                v = match_vendor_by_ifsc(ifsc, vendors)
                if v:
                    match_found = True

            # 3. Name match (fuzzy)
            if not match_found:
                v, score = find_best_vendor_match(vendor_raw, vendors, threshold=60)
                if v and score >= 0.60:
                    match_found = True

            if not match_found:
                findings.append(self.make_finding(
                    pages=pages,
                    document_refs=[inv_num],
                    description=f"Vendor '{vendor_raw}' not found in Vendor Master (no name/GSTIN/IFSC match)",
                    reported_value=vendor_raw,
                    correct_value="Should be a registered vendor",
                    confidence=0.72,
                ))

        log.info(f"FakeVendor: found {len(findings)} candidates")
        return findings
