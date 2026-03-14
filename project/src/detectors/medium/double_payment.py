"""Double payment detector: same payment in bank statements months apart."""
import json
from decimal import Decimal
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from ...normalization.money import parse_money, format_money

log = get_logger(__name__)


class DoublePaymentDetector(BaseDetector):
    category = Category.DOUBLE_PAYMENT
    name = "double_payment"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        statements = store.query("SELECT * FROM bank_statements")

        # Collect all transactions across statements
        all_txns = []
        for stmt in statements:
            txns = json.loads(stmt.get("transactions_json", "[]"))
            for txn in txns:
                txn["_statement_month"] = stmt.get("statement_month", "")
                txn["_statement_id"] = stmt.get("statement_id", "")
                txn["_source_pages"] = json.loads(stmt.get("source_pages", "[]"))
            all_txns.extend(txns)

        # Group by amount + reference pattern
        from collections import defaultdict
        groups = defaultdict(list)
        for txn in all_txns:
            debit = parse_money(txn.get("debit"))
            if debit is None or debit <= 0:
                continue
            ref = str(txn.get("reference", "")).strip().upper()
            desc = str(txn.get("description", "")).strip().upper()
            # Key: amount + reference (if meaningful)
            key = f"{debit}|{ref}" if ref else f"{debit}|{desc[:30]}"
            groups[key].append(txn)

        for key, txns in groups.items():
            if len(txns) < 2:
                continue
            # Check they're from different months
            months = set(t.get("_statement_month", "") for t in txns)
            if len(months) < 2:
                continue

            amount = parse_money(txns[0].get("debit"))
            ref = txns[0].get("reference", "")
            pages = []
            stmt_refs = []
            for t in txns:
                pages.extend(t.get("_source_pages", []))
                stmt_refs.append(t.get("_statement_id", ""))

            findings.append(self.make_finding(
                pages=sorted(set(pages)),
                document_refs=list(set(stmt_refs)),
                description=f"Payment of {format_money(amount)} (ref: {ref}) appears in {len(months)} different statement months: {', '.join(sorted(months))}",
                reported_value=f"Payment of {format_money(amount)} x {len(txns)}",
                correct_value=f"Payment of {format_money(amount)} x 1",
                confidence=0.80,
            ))

        log.info(f"DoublePayment: found {len(findings)} candidates")
        return findings
