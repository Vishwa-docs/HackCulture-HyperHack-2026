"""Invalid date detector: impossible calendar dates."""
import json
import re
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...normalization.dates import validate_date_string

log = get_logger(__name__)

DATE_FIELD_PATTERNS = [
    r'(?:Date|Dated?|Invoice\s*Date|PO\s*Date|Due\s*Date|Delivery\s*Date|Report\s*Date)\s*[:#]?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
    r'(?:Date|Dated?)\s*[:#]?\s*(\d{1,2}\s+\w+\s+\d{2,4})',
]


class InvalidDateDetector(BaseDetector):
    category = Category.INVALID_DATE
    name = "invalid_date"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []

        # Check invoice dates
        invoices = store.query("SELECT * FROM invoices")
        for inv in invoices:
            pages = json.loads(inv.get("source_pages", "[]"))
            inv_num = inv["invoice_number"]
            for field_name, field_val in [("invoice_date", inv.get("invoice_date", "")),
                                           ("due_date", inv.get("due_date", ""))]:
                if field_val:
                    is_valid, reason = validate_date_string(field_val)
                    if not is_valid:
                        findings.append(self.make_finding(
                            pages=pages,
                            document_refs=[inv_num],
                            description=f"Invalid {field_name}: '{field_val}' - {reason}",
                            reported_value=field_val,
                            correct_value="",
                            confidence=0.95,
                        ))

        # Check PO dates
        pos = store.query("SELECT * FROM purchase_orders")
        for po in pos:
            pages = json.loads(po.get("source_pages", "[]"))
            po_num = po["po_number"]
            for field_name, field_val in [("po_date", po.get("po_date", ""))]:
                if field_val:
                    is_valid, reason = validate_date_string(field_val)
                    if not is_valid:
                        findings.append(self.make_finding(
                            pages=pages,
                            document_refs=[po_num],
                            description=f"Invalid {field_name}: '{field_val}' - {reason}",
                            reported_value=field_val,
                            correct_value="",
                            confidence=0.95,
                        ))

        # Also scan raw page text for invalid dates
        pages_data = store.query("SELECT page_num, page_text FROM pages WHERE length(page_text) > 50")
        for page in pages_data:
            text = page["page_text"]
            page_num = page["page_num"]
            for pattern in DATE_FIELD_PATTERNS:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for date_str in matches:
                    is_valid, reason = validate_date_string(date_str)
                    if not is_valid:
                        # Check we haven't already found this from structured data
                        already_found = any(
                            f.reported_value == date_str and page_num in f.pages
                            for f in findings
                        )
                        if not already_found:
                            findings.append(self.make_finding(
                                pages=[page_num],
                                document_refs=[],
                                description=f"Invalid date found: '{date_str}' - {reason}",
                                reported_value=date_str,
                                correct_value="",
                                confidence=0.90,
                            ))

        log.info(f"InvalidDate: found {len(findings)} candidates")
        return findings
