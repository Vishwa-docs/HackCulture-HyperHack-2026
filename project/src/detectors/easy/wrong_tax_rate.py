"""Wrong tax rate detector: GST rate inconsistent with HSN/SAC."""
import json
from decimal import Decimal
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...core.config import Settings
from ...normalization.money import parse_money, format_money

log = get_logger(__name__)

# Standard GST rates
STANDARD_GST_RATES = {Decimal("0"), Decimal("5"), Decimal("12"), Decimal("18"), Decimal("28")}


class WrongTaxRateDetector(BaseDetector):
    category = Category.WRONG_TAX_RATE
    name = "wrong_tax_rate"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        gst_config = Settings.gst()
        invoices = store.query("SELECT * FROM invoices")

        for inv in invoices:
            inv_num = inv["invoice_number"]
            pages = json.loads(inv.get("source_pages", "[]"))
            line_items = json.loads(inv.get("line_items_json", "[]"))
            doc_tax_rate = parse_money(inv.get("tax_rate"))

            for li in line_items:
                tax_rate = parse_money(li.get("tax_rate"))
                if tax_rate is None:
                    continue

                hsn_sac = str(li.get("hsn_sac", "")).strip()
                desc = str(li.get("description", "")).lower()

                # Check if tax rate is a standard GST rate
                if tax_rate not in STANDARD_GST_RATES:
                    findings.append(self.make_finding(
                        pages=pages,
                        document_refs=[inv_num],
                        description=f"Line {li.get('line_num', '?')}: Tax rate {tax_rate}% is not a standard GST rate",
                        reported_value=f"{tax_rate}%",
                        correct_value="Standard GST rate (0/5/12/18/28%)",
                        confidence=0.82,
                    ))
                    continue

                # Check against known service types
                expected_rate = None
                for service_key, rate in gst_config.get("gst_rates", {}).items():
                    if service_key in desc:
                        expected_rate = Decimal(str(rate))
                        break

                if expected_rate is not None and tax_rate != expected_rate:
                    findings.append(self.make_finding(
                        pages=pages,
                        document_refs=[inv_num],
                        description=f"Line {li.get('line_num', '?')}: Tax rate {tax_rate}% applied, but expected {expected_rate}% for this service type",
                        reported_value=f"{tax_rate}%",
                        correct_value=f"{expected_rate}%",
                        confidence=0.80,
                    ))

        log.info(f"WrongTaxRate: found {len(findings)} candidates")
        return findings
