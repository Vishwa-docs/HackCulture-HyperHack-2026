"""Employee ID collision detector: same ID used by different people."""
import json
from collections import defaultdict
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger
from rapidfuzz import fuzz

log = get_logger(__name__)


def _normalize_name(name: str) -> str:
    """Normalize name for comparison."""
    import re
    s = name.strip().lower()
    s = re.sub(r'\s+', ' ', s)
    # Remove titles
    s = re.sub(r'^(mr|mrs|ms|dr|prof)\.?\s+', '', s)
    return s


class EmployeeIDCollisionDetector(BaseDetector):
    category = Category.EMPLOYEE_ID_COLLISION
    name = "employee_id_collision"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        reports = store.query("SELECT * FROM expense_reports WHERE employee_id IS NOT NULL AND employee_id != ''")

        # Group by employee_id
        by_id = defaultdict(list)
        for rpt in reports:
            emp_id = str(rpt.get("employee_id", "")).strip().upper()
            if emp_id:
                by_id[emp_id].append(rpt)

        for emp_id, rpts in by_id.items():
            if len(rpts) < 2:
                continue

            # Check for distinct names
            names = set()
            for rpt in rpts:
                name = _normalize_name(rpt.get("employee_name", ""))
                if name:
                    names.add(name)

            if len(names) < 2:
                continue

            # Verify names are truly different (not just "A. Kumar" vs "Arun Kumar")
            name_list = list(names)
            truly_different = False
            for i in range(len(name_list)):
                for j in range(i + 1, len(name_list)):
                    score = fuzz.token_sort_ratio(name_list[i], name_list[j])
                    if score < 70:  # Significantly different names
                        truly_different = True
                        break
                if truly_different:
                    break

            if truly_different:
                all_pages = []
                all_refs = []
                for rpt in rpts:
                    all_pages.extend(json.loads(rpt.get("source_pages", "[]")))
                    all_refs.append(rpt.get("report_id", ""))

                raw_names = [rpt.get("employee_name", "") for rpt in rpts]
                unique_names = sorted(set(raw_names))

                findings.append(self.make_finding(
                    pages=sorted(set(all_pages)),
                    document_refs=sorted(set(all_refs)),
                    description=f"Employee ID '{emp_id}' is used by different people: {', '.join(unique_names)}",
                    reported_value=f"ID '{emp_id}' used by: {', '.join(unique_names)}",
                    correct_value="Each employee should have a unique ID",
                    confidence=0.76,
                ))

        log.info(f"EmployeeIDCollision: found {len(findings)} candidates")
        return findings
