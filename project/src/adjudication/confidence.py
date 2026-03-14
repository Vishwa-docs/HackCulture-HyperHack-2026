"""Confidence scoring, deduplication, and false positive control."""
from collections import defaultdict
from ..core.models import FindingCandidate
from ..core.config import Settings
from ..core.logging import get_logger

log = get_logger(__name__)


def apply_thresholds(candidates: list[FindingCandidate]) -> tuple[list[FindingCandidate], list[FindingCandidate]]:
    """Filter candidates by category-specific confidence thresholds."""
    thresholds = Settings.thresholds()
    accepted = []
    rejected = []

    for c in candidates:
        threshold = thresholds.get(c.category, 0.7)
        if c.confidence >= threshold:
            c.status = "accepted"
            accepted.append(c)
        else:
            c.status = "rejected"
            c.rejection_reason = f"Confidence {c.confidence:.2f} < threshold {threshold:.2f}"
            rejected.append(c)

    log.info(f"Threshold filter: {len(accepted)} accepted, {len(rejected)} rejected")
    return accepted, rejected


def deduplicate(candidates: list[FindingCandidate]) -> list[FindingCandidate]:
    """Remove duplicate findings for the same issue."""
    seen = {}
    unique = []

    for c in candidates:
        # Key: category + document_refs + reported_value
        key = f"{c.category}|{'|'.join(sorted(c.document_refs))}|{c.reported_value}"
        if key not in seen or c.confidence > seen[key].confidence:
            seen[key] = c

    unique = list(seen.values())
    removed = len(candidates) - len(unique)
    if removed > 0:
        log.info(f"Dedup removed {removed} duplicate findings")
    return unique


def cross_category_check(candidates: list[FindingCandidate]) -> list[FindingCandidate]:
    """
    Prevent conflicting findings:
    - fake_vendor and vendor_name_typo can't both fire for same invoice
    - duplicate_expense and triple_expense_claim can override
    """
    by_doc = defaultdict(list)
    for c in candidates:
        for ref in c.document_refs:
            by_doc[ref].append(c)

    to_remove = set()

    for ref, findings in by_doc.items():
        cats = {f.category for f in findings}

        # If both fake_vendor and vendor_name_typo fire for same doc, keep the higher confidence one
        if "fake_vendor" in cats and "vendor_name_typo" in cats:
            fake = [f for f in findings if f.category == "fake_vendor"]
            typo = [f for f in findings if f.category == "vendor_name_typo"]
            # If typo has higher confidence, remove fake; otherwise keep fake
            for f in fake:
                for t in typo:
                    if t.confidence > f.confidence:
                        to_remove.add(id(f))
                    else:
                        to_remove.add(id(t))

        # duplicate_expense with 3+ reports → upgrade to triple_expense_claim
        if "duplicate_expense" in cats and "triple_expense_claim" in cats:
            for f in findings:
                if f.category == "duplicate_expense":
                    to_remove.add(id(f))

    result = [c for c in candidates if id(c) not in to_remove]
    removed = len(candidates) - len(result)
    if removed > 0:
        log.info(f"Cross-category check removed {removed} conflicting findings")
    return result


def assign_finding_ids(candidates: list[FindingCandidate]) -> list[FindingCandidate]:
    """Assign deterministic finding IDs."""
    # Sort for determinism
    candidates.sort(key=lambda c: (c.category, c.pages[0] if c.pages else 0, c.reported_value))
    for i, c in enumerate(candidates, 1):
        c.finding_id = f"F-{i:03d}"
    return candidates


def finalize_findings(candidates: list[FindingCandidate]) -> tuple[list[FindingCandidate], list[FindingCandidate]]:
    """Full finalization pipeline."""
    log.info(f"Finalizing {len(candidates)} candidates")

    # 1. Deduplicate
    candidates = deduplicate(candidates)

    # 2. Cross-category conflict resolution
    candidates = cross_category_check(candidates)

    # 3. Apply thresholds
    accepted, rejected = apply_thresholds(candidates)

    # 4. Assign IDs
    accepted = assign_finding_ids(accepted)

    log.info(f"Final: {len(accepted)} findings accepted, {len(rejected)} rejected")
    return accepted, rejected
