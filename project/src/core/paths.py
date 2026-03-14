"""Path constants for the project."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

# Data directories
DATA = PROJECT_ROOT / "data"
INPUT = DATA / "input"
RAW = DATA / "raw"
PARSED = DATA / "parsed"
RENDERED = DATA / "rendered_pages"
SPLIT_DOCS = DATA / "split_docs"
EXTRACTED = DATA / "extracted"
NORMALIZED = DATA / "normalized"
INDEXES = DATA / "indexes"
OUTPUTS = DATA / "outputs"
CACHE = DATA / "cache"
EVAL = DATA / "eval"

# Ensure all dirs exist
for d in [RAW, PARSED, RENDERED, SPLIT_DOCS, EXTRACTED, NORMALIZED, INDEXES, OUTPUTS, CACHE, EVAL]:
    d.mkdir(parents=True, exist_ok=True)

# Key files
GAUNTLET_PDF = INPUT / "gauntlet.pdf"
SUBMISSION_JSON = OUTPUTS / "submission.json"
ALL_CANDIDATES_JSON = OUTPUTS / "all_candidates.json"
REJECTED_JSON = OUTPUTS / "rejected_candidates.json"
FINDINGS_CSV = OUTPUTS / "findings.csv"
