"""Vendor name typo detector: invoice vendor name misspelled vs Vendor Master."""
import json
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...normalization.vendors import find_best_vendor_match, normalize_vendor_name, match_vendor_by_gstin

log = get_logger(__name__)


class VendorNameTypoDetector(BaseDetector):
    category = Category.VENDOR_NAME_TYPO
    name = "vendor_name_typo"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        if not vendors:
            return findings

        invoices = store.query("SELECT * FROM invoices")
        for inv in invoices:
            inv_num = inv["invoice_number"]
            vendor_raw = inv.get("vendor_name_raw", "")
            gstin_vendor = inv.get("gstin_vendor", "")
            pages = json.loads(inv.get("source_pages", "[]"))

            if not vendor_raw:
                continue

            # Try exact canonical match first
            norm = normalize_vendor_name(vendor_raw)
            exact_match = any(v.canonical_name.lower() == norm.lower() for v in vendors)
            if exact_match:
                continue

            # Try GSTIN match - if GSTIN matches but name doesn't, likely typo
            gstin_match = match_vendor_by_gstin(gstin_vendor, vendors) if gstin_vendor else None

            # Fuzzy match
            best_match, score = find_best_vendor_match(vendor_raw, vendors, threshold=60)

            if best_match and score < 0.98:
                # High similarity but not exact = likely typo
                if score >= 0.70:
                    confidence = 0.75 + (1.0 - score) * 0.3
                    # Boost confidence if GSTIN supports this match
                    if gstin_match and gstin_match.vendor_id == best_match.vendor_id:
                        confidence = min(confidence + 0.15, 0.98)

                    findings.append(self.make_finding(
                        pages=pages,
                        document_refs=[inv_num],
                        description=f"Vendor name '{vendor_raw}' appears to be a typo of '{best_match.canonical_name}' (match score: {score:.0%})",
                        reported_value=vendor_raw,
                        correct_value=best_match.canonical_name,
                        confidence=confidence,
                    ))

        log.info(f"VendorNameTypo: found {len(findings)} candidates")
        return findings
