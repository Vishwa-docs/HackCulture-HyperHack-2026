"""GSTIN state mismatch detector: first 2 digits of GSTIN vs vendor state."""
import json
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...core.config import Settings
from ...core.utils import extract_gstin_state_code
from ...normalization.vendors import find_best_vendor_match, match_vendor_by_gstin

log = get_logger(__name__)


class GSTINStateMismatchDetector(BaseDetector):
    category = Category.GSTIN_STATE_MISMATCH
    name = "gstin_state_mismatch"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        if not vendors:
            return findings

        gst_config = Settings.gst()
        state_codes = gst_config.get("state_codes", {})
        state_aliases = gst_config.get("state_aliases", {})

        # Build reverse mapping: state name -> expected code
        state_to_code = {}
        for code, state_name in state_codes.items():
            state_to_code[state_name.lower()] = code
            # Add aliases
            for canonical, aliases in state_aliases.items():
                if canonical.lower() == state_name.lower():
                    for alias in aliases:
                        state_to_code[alias.lower()] = code

        # Check vendor master itself
        for vendor in vendors:
            if vendor.gstin and vendor.state:
                gstin_code = extract_gstin_state_code(vendor.gstin)
                expected_code = state_to_code.get(vendor.state.lower())

                if gstin_code and expected_code and gstin_code != expected_code:
                    expected_state = state_codes.get(gstin_code, "unknown")
                    findings.append(self.make_finding(
                        pages=vendor.source_pages,
                        document_refs=[vendor.vendor_id],
                        description=f"Vendor '{vendor.canonical_name}': GSTIN state code '{gstin_code}' ({expected_state}) doesn't match registered state '{vendor.state}' (expected code '{expected_code}')",
                        reported_value=f"GSTIN state code: {gstin_code}",
                        correct_value=f"Expected state code: {expected_code} for {vendor.state}",
                        confidence=0.90,
                    ))

        # Also check invoices
        invoices = store.query("SELECT * FROM invoices WHERE gstin_vendor IS NOT NULL AND gstin_vendor != ''")
        for inv in invoices:
            gstin = inv.get("gstin_vendor", "")
            inv_num = inv["invoice_number"]
            vendor_raw = inv.get("vendor_name_raw", "")
            pages = json.loads(inv.get("source_pages", "[]"))

            if not gstin:
                continue

            # Find vendor from master
            vendor = match_vendor_by_gstin(gstin, vendors)
            if not vendor:
                vendor, _ = find_best_vendor_match(vendor_raw, vendors, threshold=75)

            if vendor and vendor.state:
                gstin_code = extract_gstin_state_code(gstin)
                expected_code = state_to_code.get(vendor.state.lower())

                if gstin_code and expected_code and gstin_code != expected_code:
                    expected_state = state_codes.get(gstin_code, "unknown")
                    # Don't duplicate findings already from vendor master check
                    already = any(
                        f.reported_value == f"GSTIN state code: {gstin_code}"
                        and vendor.vendor_id in f.document_refs
                        for f in findings
                    )
                    if not already:
                        findings.append(self.make_finding(
                            pages=pages,
                            document_refs=[inv_num],
                            description=f"Invoice GSTIN '{gstin}' state code '{gstin_code}' ({expected_state}) doesn't match vendor '{vendor.canonical_name}' state '{vendor.state}'",
                            reported_value=f"GSTIN state code: {gstin_code}",
                            correct_value=f"Expected: {expected_code} for {vendor.state}",
                            confidence=0.88,
                        ))

        log.info(f"GSTINStateMismatch: found {len(findings)} candidates")
        return findings
