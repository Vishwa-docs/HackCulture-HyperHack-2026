"""Utility functions."""
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional


def safe_decimal(val: Any) -> Optional[Decimal]:
    """Parse a value to Decimal, stripping currency symbols and commas."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    s = str(val).strip()
    # Remove currency symbols and commas
    s = re.sub(r'[₹$€£,\s]', '', s)
    # Handle parenthetical negatives
    if s.startswith('(') and s.endswith(')'):
        s = '-' + s[1:-1]
    if not s or s == '-':
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def normalize_doc_ref(ref: str) -> str:
    """Normalize document reference for matching."""
    s = ref.strip().upper()
    s = re.sub(r'\s+', '', s)
    return s


def normalize_whitespace(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()


def extract_gstin_state_code(gstin: str) -> Optional[str]:
    """Extract 2-digit state code from GSTIN."""
    gstin = gstin.strip()
    if len(gstin) >= 2 and gstin[:2].isdigit():
        return gstin[:2]
    return None


def validate_gstin_format(gstin: str) -> bool:
    """Basic GSTIN format validation: 2-digit state + 10-char PAN + 1 entity + 1 check."""
    pattern = r'^\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d][A-Z]$'
    return bool(re.match(pattern, gstin.strip().upper()))


def validate_ifsc_format(ifsc: str) -> bool:
    """Basic IFSC format validation: 4 alpha + 0 + 6 alphanumeric."""
    pattern = r'^[A-Z]{4}0[A-Z0-9]{6}$'
    return bool(re.match(pattern, ifsc.strip().upper()))


def file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def cache_key(*args: str) -> str:
    combined = "|".join(str(a) for a in args)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def load_json_cache(path: Path) -> Optional[dict]:
    if path.exists():
        return json.loads(path.read_text())
    return None


def save_json_cache(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))
