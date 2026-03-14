"""Balance drift detector: bank statement opening != prior month closing."""
import json
from decimal import Decimal
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...normalization.money import parse_money, format_money, money_equal

log = get_logger(__name__)


class BalanceDriftDetector(BaseDetector):
    category = Category.BALANCE_DRIFT
    name = "balance_drift"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        statements = store.query("SELECT * FROM bank_statements ORDER BY account_number, statement_month")

        # Group by account
        from collections import defaultdict
        by_account = defaultdict(list)
        for stmt in statements:
            acct = stmt.get("account_number", "default")
            by_account[acct].append(stmt)

        for acct, stmts in by_account.items():
            # Sort by month
            stmts.sort(key=lambda s: s.get("statement_month", ""))

            for i in range(1, len(stmts)):
                prev = stmts[i - 1]
                curr = stmts[i]

                prev_closing = parse_money(prev.get("closing_balance"))
                curr_opening = parse_money(curr.get("opening_balance"))

                if prev_closing is not None and curr_opening is not None:
                    if not money_equal(prev_closing, curr_opening, Decimal("0.01")):
                        prev_pages = json.loads(prev.get("source_pages", "[]"))
                        curr_pages = json.loads(curr.get("source_pages", "[]"))
                        drift = curr_opening - prev_closing

                        findings.append(self.make_finding(
                            pages=sorted(set(prev_pages + curr_pages)),
                            document_refs=[prev.get("statement_id", ""), curr.get("statement_id", "")],
                            description=f"Balance drift: {prev.get('statement_month', '?')} closing ({format_money(prev_closing)}) != {curr.get('statement_month', '?')} opening ({format_money(curr_opening)}). Drift: {format_money(drift)}",
                            reported_value=format_money(curr_opening),
                            correct_value=format_money(prev_closing),
                            confidence=0.85,
                        ))

        log.info(f"BalanceDrift: found {len(findings)} candidates")
        return findings
