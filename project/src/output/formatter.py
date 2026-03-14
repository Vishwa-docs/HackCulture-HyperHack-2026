"""Output formatting and JSON writing."""
import csv
import json
from pathlib import Path
from ..core.models import FindingCandidate
from ..core import paths
from ..core.logging import get_logger

log = get_logger(__name__)


def write_submission(team_id: str, findings: list[FindingCandidate], output_dir: Path = None):
    """Write final submission JSON and supporting files."""
    output_dir = output_dir or paths.OUTPUTS
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build submission
    submission = {
        "team_id": team_id,
        "findings": [
            {
                "finding_id": f.finding_id,
                "category": f.category,
                "pages": f.pages,
                "document_refs": f.document_refs,
                "description": f.description,
                "reported_value": f.reported_value,
                "correct_value": f.correct_value,
            }
            for f in findings
        ]
    }

    # Write compact JSON
    with open(output_dir / "submission.json", "w") as fh:
        json.dump(submission, fh, separators=(",", ":"))

    # Write pretty JSON
    with open(output_dir / "submission_pretty.json", "w") as fh:
        json.dump(submission, fh, indent=2)

    log.info(f"Wrote submission.json with {len(findings)} findings")


def write_all_candidates(candidates: list[FindingCandidate], output_dir: Path = None):
    """Write all candidates including rejected ones."""
    output_dir = output_dir or paths.OUTPUTS
    output_dir.mkdir(parents=True, exist_ok=True)

    data = [c.model_dump(mode="json") for c in candidates]
    with open(output_dir / "all_candidates.json", "w") as fh:
        json.dump(data, fh, indent=2, default=str)


def write_rejected(rejected: list[FindingCandidate], output_dir: Path = None):
    """Write rejected candidates."""
    output_dir = output_dir or paths.OUTPUTS
    output_dir.mkdir(parents=True, exist_ok=True)

    data = [c.model_dump(mode="json") for c in rejected]
    with open(output_dir / "rejected_candidates.json", "w") as fh:
        json.dump(data, fh, indent=2, default=str)


def write_findings_csv(findings: list[FindingCandidate], output_dir: Path = None):
    """Write findings as CSV for inspection."""
    output_dir = output_dir or paths.OUTPUTS
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "findings.csv", "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["finding_id", "category", "pages", "document_refs",
                         "description", "reported_value", "correct_value", "confidence"])
        for f in findings:
            writer.writerow([
                f.finding_id, f.category, str(f.pages), str(f.document_refs),
                f.description, f.reported_value, f.correct_value, f.confidence,
            ])


def write_analytics(findings: list[FindingCandidate], rejected: list[FindingCandidate],
                    output_dir: Path = None):
    """Write analytics summary."""
    output_dir = output_dir or paths.OUTPUTS
    output_dir.mkdir(parents=True, exist_ok=True)

    from collections import Counter
    cat_counts = Counter(f.category for f in findings)
    rej_counts = Counter(f.category for f in rejected)

    analytics = {
        "total_findings": len(findings),
        "total_rejected": len(rejected),
        "findings_by_category": dict(cat_counts),
        "rejected_by_category": dict(rej_counts),
        "avg_confidence": sum(f.confidence for f in findings) / len(findings) if findings else 0,
        "categories_with_zero_findings": [
            c.value for c in __import__("src.core.enums", fromlist=["Category"]).Category
            if c.value not in cat_counts
        ] if findings else [],
    }

    with open(output_dir / "analytics_summary.json", "w") as fh:
        json.dump(analytics, fh, indent=2)

    log.info(f"Analytics: {len(findings)} findings across {len(cat_counts)} categories")
