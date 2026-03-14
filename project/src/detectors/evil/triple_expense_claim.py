"""Triple expense claim detector: same hotel stay in 3+ expense reports."""
import json
from collections import defaultdict
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...normalization.money import parse_money, format_money

log = get_logger(__name__)


class TripleExpenseClaimDetector(BaseDetector):
    category = Category.TRIPLE_EXPENSE_CLAIM
    name = "triple_expense_claim"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        reports = store.query("SELECT * FROM expense_reports")

        # Group hotel stays by key: employee_id + hotel_name + stay_start + stay_end
        stays = defaultdict(list)
        for rpt in reports:
            report_id = rpt.get("report_id", "")
            emp_id = str(rpt.get("employee_id", "")).strip().upper()
            emp_name = rpt.get("employee_name", "")
            hotel = str(rpt.get("hotel_name", "")).strip().upper()
            start = str(rpt.get("stay_start", "")).strip()
            end = str(rpt.get("stay_end", "")).strip()
            amount = parse_money(rpt.get("total_amount"))
            pages = json.loads(rpt.get("source_pages", "[]"))

            if hotel and start:
                key = f"{emp_id}|{hotel}|{start}|{end}"
                stays[key].append({
                    "report_id": report_id,
                    "employee_name": emp_name,
                    "hotel": hotel,
                    "start": start,
                    "end": end,
                    "amount": amount,
                    "pages": pages,
                })

        # Also check expense_lines for hotel-type entries
        for rpt in reports:
            report_id = rpt.get("report_id", "")
            emp_id = str(rpt.get("employee_id", "")).strip().upper()
            lines = json.loads(rpt.get("expense_lines_json", "[]"))
            pages = json.loads(rpt.get("source_pages", "[]"))

            for line in lines:
                desc = str(line.get("description", "")).lower()
                merchant = str(line.get("merchant", "")).strip().upper()
                date = str(line.get("date", "")).strip()
                amount = parse_money(line.get("amount"))

                if any(kw in desc for kw in ["hotel", "accommodation", "lodging", "stay"]):
                    key = f"{emp_id}|{merchant}|{date}"
                    stays[key].append({
                        "report_id": report_id,
                        "employee_name": rpt.get("employee_name", ""),
                        "hotel": merchant,
                        "start": date,
                        "end": "",
                        "amount": amount,
                        "pages": pages,
                    })

        for key, claims in stays.items():
            report_ids = set(c["report_id"] for c in claims)
            if len(report_ids) >= 3:
                all_pages = []
                for c in claims:
                    all_pages.extend(c["pages"])

                hotel = claims[0]["hotel"]
                emp = claims[0]["employee_name"]
                start = claims[0]["start"]
                end = claims[0]["end"]

                findings.append(self.make_finding(
                    pages=sorted(set(all_pages)),
                    document_refs=sorted(report_ids),
                    description=f"Hotel stay at '{hotel}' ({start}-{end}) for employee '{emp}' claimed in {len(report_ids)} expense reports: {', '.join(sorted(report_ids))}",
                    reported_value=f"{len(report_ids)} claims",
                    correct_value="1 claim",
                    confidence=0.73,
                ))

        log.info(f"TripleExpenseClaim: found {len(findings)} candidates")
        return findings
