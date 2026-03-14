"""Vendor name normalization and matching."""
import re
from typing import Optional, Tuple
from rapidfuzz import fuzz, process

from ..core.models import VendorRecord


def normalize_vendor_name(name: str) -> str:
    """Create canonical form of vendor name for matching."""
    s = name.strip()
    # Normalize case
    s = s.title()
    # Normalize legal suffixes
    replacements = [
        (r'\bPvt\.?\s*Ltd\.?\b', 'Pvt Ltd'),
        (r'\bPrivate\s+Limited\b', 'Pvt Ltd'),
        (r'\bLimited\b', 'Ltd'),
        (r'\bLLP\b', 'LLP'),
        (r'\bInc\.?\b', 'Inc'),
        (r'\bCorp(oration)?\.?\b', 'Corp'),
    ]
    for pat, repl in replacements:
        s = re.sub(pat, repl, s, flags=re.IGNORECASE)
    # Normalize whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def make_matching_key(name: str) -> str:
    """Create a simplified key for matching (removes punctuation, lowercases)."""
    s = name.lower()
    s = re.sub(r'[^a-z0-9\s]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def find_best_vendor_match(
    name: str,
    vendors: list[VendorRecord],
    threshold: int = 80,
) -> Tuple[Optional[VendorRecord], float]:
    """Find best matching vendor from master list using fuzzy matching."""
    if not name or not vendors:
        return None, 0.0

    query_key = make_matching_key(name)
    choices = {v.vendor_id: make_matching_key(v.canonical_name) for v in vendors}

    if not choices:
        return None, 0.0

    result = process.extractOne(
        query_key,
        choices,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=threshold,
    )

    if result:
        match_key, score, vid = result
        vendor = next((v for v in vendors if v.vendor_id == vid), None)
        return vendor, score / 100.0
    return None, 0.0


def match_vendor_by_gstin(gstin: str, vendors: list[VendorRecord]) -> Optional[VendorRecord]:
    """Find vendor by exact GSTIN match."""
    gstin = gstin.strip().upper()
    for v in vendors:
        if v.gstin and v.gstin.upper() == gstin:
            return v
    return None


def match_vendor_by_ifsc(ifsc: str, vendors: list[VendorRecord]) -> Optional[VendorRecord]:
    """Find vendor by exact IFSC match."""
    ifsc = ifsc.strip().upper()
    for v in vendors:
        if v.ifsc and v.ifsc.upper() == ifsc:
            return v
    return None
