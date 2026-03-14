"""Vendor Master extraction from pages 3-4."""
import re
import json
from decimal import Decimal
from typing import Optional

from ..core.logging import get_logger
from ..core.models import VendorRecord
from ..core import paths
from ..core.utils import normalize_whitespace

log = get_logger(__name__)


def _clean_field(val: str) -> str:
    return normalize_whitespace(val).strip()


def _normalize_vendor_name(name: str) -> str:
    """Normalize vendor name for matching."""
    s = name.strip()
    # Normalize legal suffixes
    s = re.sub(r'\bPvt\.?\s*Ltd\.?\b', 'Pvt Ltd', s, flags=re.IGNORECASE)
    s = re.sub(r'\bPrivate\s+Limited\b', 'Pvt Ltd', s, flags=re.IGNORECASE)
    s = re.sub(r'\bLimited\b', 'Ltd', s, flags=re.IGNORECASE)
    s = re.sub(r'\bLLP\b', 'LLP', s, flags=re.IGNORECASE)
    s = re.sub(r'\bInc\.?\b', 'Inc', s, flags=re.IGNORECASE)
    s = re.sub(r'\bCorp\.?\b', 'Corp', s, flags=re.IGNORECASE)
    s = re.sub(r'\bServices?\b', 'Services', s, flags=re.IGNORECASE)
    s = re.sub(r'\bSolutions?\b', 'Solutions', s, flags=re.IGNORECASE)
    s = re.sub(r'\bTechnolog(y|ies)\b', 'Technologies', s, flags=re.IGNORECASE)
    s = re.sub(r'\bEnterprise[s]?\b', 'Enterprises', s, flags=re.IGNORECASE)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def extract_vendor_master(page_texts: dict[int, str], pages: list[int] = None) -> list[VendorRecord]:
    """Extract vendor master data from specified pages."""
    pages = pages or [3, 4]
    combined_text = "\n".join(page_texts.get(p, "") for p in pages)

    vendors = []
    lines = combined_text.split("\n")

    current_vendor = {}
    vendor_id = 0

    for line in lines:
        line = line.strip()
        if not line:
            if current_vendor.get("raw_name"):
                vendor_id += 1
                v = VendorRecord(
                    vendor_id=f"V-{vendor_id:03d}",
                    raw_name=current_vendor.get("raw_name", ""),
                    canonical_name=_normalize_vendor_name(current_vendor.get("raw_name", "")),
                    gstin=current_vendor.get("gstin", ""),
                    ifsc=current_vendor.get("ifsc", ""),
                    state=current_vendor.get("state", ""),
                    pan=current_vendor.get("pan", ""),
                    bank_account=current_vendor.get("bank_account", ""),
                    source_pages=pages,
                )
                vendors.append(v)
                current_vendor = {}
            continue

        # Try to extract fields
        gstin_match = re.search(r'(?:GSTIN|GST)\s*[:#]?\s*(\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d][A-Z])', line, re.IGNORECASE)
        if gstin_match:
            current_vendor["gstin"] = gstin_match.group(1).upper()
            # Extract state from GSTIN
            continue

        ifsc_match = re.search(r'(?:IFSC)\s*[:#]?\s*([A-Z]{4}0[A-Z0-9]{6})', line, re.IGNORECASE)
        if ifsc_match:
            current_vendor["ifsc"] = ifsc_match.group(1).upper()
            continue

        pan_match = re.search(r'(?:PAN)\s*[:#]?\s*([A-Z]{5}\d{4}[A-Z])', line, re.IGNORECASE)
        if pan_match:
            current_vendor["pan"] = pan_match.group(1).upper()
            continue

        state_match = re.search(r'(?:State|Location)\s*[:#]?\s*(.+)', line, re.IGNORECASE)
        if state_match:
            current_vendor["state"] = _clean_field(state_match.group(1))
            continue

        bank_match = re.search(r'(?:Account|A/c)\s*(?:No|Number)?\s*[:#]?\s*(\d+)', line, re.IGNORECASE)
        if bank_match:
            current_vendor["bank_account"] = bank_match.group(1)
            continue

        # If no field match and no name yet, treat as vendor name
        if not current_vendor.get("raw_name") and len(line) > 3:
            # Skip headers and labels
            if not re.match(r'^(S\.?\s*No|Sr|Vendor|Name|GSTIN|IFSC|PAN|State|Bank|Account)', line, re.IGNORECASE):
                current_vendor["raw_name"] = _clean_field(line)

    # Don't forget last vendor
    if current_vendor.get("raw_name"):
        vendor_id += 1
        v = VendorRecord(
            vendor_id=f"V-{vendor_id:03d}",
            raw_name=current_vendor.get("raw_name", ""),
            canonical_name=_normalize_vendor_name(current_vendor.get("raw_name", "")),
            gstin=current_vendor.get("gstin", ""),
            ifsc=current_vendor.get("ifsc", ""),
            state=current_vendor.get("state", ""),
            pan=current_vendor.get("pan", ""),
            bank_account=current_vendor.get("bank_account", ""),
            source_pages=pages,
        )
        vendors.append(v)

    log.info(f"Extracted {len(vendors)} vendors from master pages")

    # Save
    out_path = paths.EXTRACTED / "vendor_master.json"
    out_path.write_text(json.dumps([v.model_dump(mode="json") for v in vendors], indent=2))

    return vendors


def extract_vendor_master_with_llm(page_texts: dict[int, str], bedrock_client, pages: list[int] = None) -> list[VendorRecord]:
    """Use LLM to extract vendor master when text parsing is insufficient."""
    pages = pages or [3, 4]
    combined_text = "\n".join(page_texts.get(p, "") for p in pages)

    prompt = f"""Extract ALL vendors from this Vendor Master document. Return a JSON array of objects.

Each vendor object must have these fields:
- "raw_name": exact vendor name as written
- "gstin": GSTIN number (15 chars, format: 2-digit state + PAN + entity + check)
- "ifsc": IFSC code (11 chars, format: 4 alpha + 0 + 6 alphanum)
- "state": registered state
- "pan": PAN number
- "bank_account": bank account number

Return ONLY valid JSON array. Do not guess or fabricate data. If a field is not found, use empty string.

DOCUMENT TEXT:
{combined_text}

Return JSON array:"""

    result = bedrock_client.extract_json(prompt, model=bedrock_client.model_reasoning)
    if not result:
        log.warning("LLM vendor extraction returned no results")
        return []

    vendors_data = result if isinstance(result, list) else result.get("vendors", [])
    vendors = []
    for i, vd in enumerate(vendors_data, 1):
        v = VendorRecord(
            vendor_id=f"V-{i:03d}",
            raw_name=vd.get("raw_name", ""),
            canonical_name=_normalize_vendor_name(vd.get("raw_name", "")),
            gstin=vd.get("gstin", ""),
            ifsc=vd.get("ifsc", ""),
            state=vd.get("state", ""),
            pan=vd.get("pan", ""),
            bank_account=str(vd.get("bank_account", "")),
            source_pages=pages,
        )
        vendors.append(v)

    log.info(f"LLM extracted {len(vendors)} vendors from master pages")
    out_path = paths.EXTRACTED / "vendor_master.json"
    out_path.write_text(json.dumps([v.model_dump(mode="json") for v in vendors], indent=2))
    return vendors
