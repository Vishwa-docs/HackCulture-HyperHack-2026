"""Duplicate expense detector: same expense in two different reports."""
import json
from decimal import Decimal
from collections import defaultdict
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...normalization.money import parse_money, format_money

log = get_logger(__name__)


class DuplicateExpenseDetector(BaseDetector):
    category = Category.DUPLICATE_EXPENSE
    name = "duplicate_expense"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        reports = store.query("SELECT * FROM expense_reports")

        # Collect all expense lines across reports
        all_expenses = []
        for rpt in reports:
            lines = json.loads(rpt.get("expense_lines_json", "[]"))
            for line in lines:
                line["_report_id"] = rpt.get("report_id", "")
                line["_employee_name"] = rpt.get("employee_name", "")
                line["_employee_id"] = rpt.get("employee_id", "")
                line["_source_pages"] = json.loads(rpt.get("source_pages", "[]"))
            all_expenses.extend(lines)

        # Group by employee_id + merchant + amount + date
        groups = defaultdict(list)
        for exp in all_expenses:
            emp_id = str(exp.get("_employee_id", "")).strip().upper()
            merchant = str(exp.get("merchant", "")).strip().upper()
            amount = str(exp.get("amount", ""))
            date = str(exp.get("date", "")).strip()
            key = f"{emp_id}|{merchant}|{amount}|{date}"
            groups[key].append(exp)

        for key, expenses in groups.items():
            if len(expenses) < 2:
                continue
            # Must be from different reports
            report_ids = set(e.get("_report_id", "") for e in expenses)
            if len(report_ids) < 2:
                continue

            amount = parse_money(expenses[0].get("amount"))
            merchant = expenses[0].get("merchant", "unknown")
            pages = []
            for e in expenses:
                pages.extend(e.get("_source_pages", []))

            findings.append(self.make_finding(
                pages=sorted(set(pages)),
                document_refs=sorted(report_ids),
                description=f"Expense of {format_money(amount)} at '{merchant}' claimed in {len(report_ids)} different reports: {', '.join(sorted(report_ids))}",
                reported_value=f"{len(report_ids)} claims",
                correct_value="1 claim",
                confidence=0.83,
            ))

        log.info(f"DuplicateExpense: found {len(findings)} candidates")
        return findings
