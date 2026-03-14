"""Document splitter and classifier using heuristic rules on page text."""
import re
import json
from typing import Optional
from ..core.logging import get_logger
from ..core.enums import DocType
from ..core import paths

log = get_logger(__name__)

# -- Continuation headers (must be checked BEFORE new-doc headers) --
CONTINUATION_PATTERNS = [
    (re.compile(r'(?i)\bTAX\s+INVOICE\s*\(Continued\)'), DocType.INVOICE),
    (re.compile(r'(?i)\bPURCHASE\s+ORDER\s*\(Continued\)'), DocType.PURCHASE_ORDER),
    (re.compile(r'(?i)\bBANK\s+STATEMENT\s*\(Continued\)'), DocType.BANK_STATEMENT),
    (re.compile(r'(?i)\bEXPENSE\s+REPORT\s*\(Continued\)'), DocType.EXPENSE_REPORT),
    (re.compile(r'(?i)\bCREDIT\s+NOTE\s*\(Continued\)'), DocType.CREDIT_NOTE),
    (re.compile(r'(?i)\bDEBIT\s+NOTE\s*\(Continued\)'), DocType.DEBIT_NOTE),
    (re.compile(r'(?i)\bVENDOR\s+MASTER\s*\(Continued\)'), DocType.VENDOR_MASTER),
]

# -- New-document headers --
NEW_DOC_PATTERNS = [
    (re.compile(r'(?i)\bTAX\s+INVOICE\b'), DocType.INVOICE),
    (re.compile(r'(?i)\bPURCHASE\s+ORDER\b'), DocType.PURCHASE_ORDER),
    (re.compile(r'(?i)\bBANK\s+STATEMENT\b'), DocType.BANK_STATEMENT),
    (re.compile(r'(?i)\bStatement\s+of\s+Account\b'), DocType.BANK_STATEMENT),
    (re.compile(r'(?i)\bEXPENSE\s+REPORT\b'), DocType.EXPENSE_REPORT),
    (re.compile(r'(?i)\bEXPENSE\s+CLAIM\b'), DocType.EXPENSE_REPORT),
    (re.compile(r'(?i)\bCREDIT\s+NOTE\b'), DocType.CREDIT_NOTE),
    (re.compile(r'(?i)\bDEBIT\s+NOTE\b'), DocType.DEBIT_NOTE),
    (re.compile(r'(?i)\bVENDOR\s+MASTER\b'), DocType.VENDOR_MASTER),
    (re.compile(r'(?i)\bDELIVERY\s+(NOTE|CHALLAN)\b'), DocType.DELIVERY_NOTE),
    (re.compile(r'(?i)\bTERMS\s+(AND|&)\s+CONDITIONS\b'), DocType.TERMS_CONDITIONS),
]

# -- Primary reference extraction (keyed by DocType) --
PRIMARY_REF_PATTERNS = {
    DocType.INVOICE: re.compile(
        r'Invoice\s*(?:No|Number|#)\s*[:#]?\s*(INV[-\s]?\d{4}[-\s]?\d+)', re.I),
    DocType.PURCHASE_ORDER: re.compile(
        r'(?:P\.?O\.?\s*(?:No|Number|#|Reference)|Purchase\s+Order\s*(?:No|Number|#))\s*[:#]?\s*(PO[-\s]?\d{4}[-\s]?\d+)', re.I),
    DocType.CREDIT_NOTE: re.compile(
        r'CREDIT\s+NOTE\s*(?:No|Number|#)\s*[:#]?\s*(CN[-\s]?\d{4}[-\s]?\d+)', re.I),
    DocType.DEBIT_NOTE: re.compile(
        r'DEBIT\s+NOTE\s*(?:No|Number|#)\s*[:#]?\s*(DN[-\s]?\d{4}[-\s]?\d+)', re.I),
    DocType.BANK_STATEMENT: re.compile(
        r'(BS[-\s]?\d{4}[-\s]?\d+)', re.I),
    DocType.EXPENSE_REPORT: re.compile(
        r'(?:Report\s*(?:ID|No|Number|#))\s*[:#]?\s*(EXP[-\s]?\d{4}[-\s]?\d+)', re.I),
}

# Generic pattern to find ANY well-formed reference on a page
ALL_REF_RE = re.compile(r'\b((?:INV|PO|CN|DN|BS|EXP)-\d{4}-\d{3,6})\b')


def classify_page(text: str):
    """Classify a page.
    Returns (doc_type, is_continuation, confidence, primary_ref).
    """
    head = text[:600]

    # 1. Check continuation first
    for pat, dtype in CONTINUATION_PATTERNS:
        if pat.search(head):
            ref = _extract_primary_ref(text, dtype)
            return dtype, True, 0.90, ref

    # 2. Check new document start
    for pat, dtype in NEW_DOC_PATTERNS:
        if pat.search(head):
            ref = _extract_primary_ref(text, dtype)
            return dtype, False, 0.90, ref

    # 3. Fallback
    if len(text.strip()) < 50:
        return DocType.FILLER, False, 0.5, None
    return DocType.UNKNOWN, False, 0.3, None


def _extract_primary_ref(text: str, doc_type: DocType) -> Optional[str]:
    pat = PRIMARY_REF_PATTERNS.get(doc_type)
    if pat:
        m = pat.search(text)
        if m:
            return m.group(1).replace(" ", "")
    return None


def extract_doc_refs(text: str) -> list[str]:
    """Extract ALL well-formed document reference numbers from text."""
    return list(set(ALL_REF_RE.findall(text)))


def split_into_documents(page_texts: dict[int, str]) -> list[dict]:
    """
    Split pages into logical document ranges.
    A new document starts when we see a non-continuation header.
    Continuation pages extend the current document.
    """
    documents = []
    current_doc = None
    doc_counter = 0

    sorted_pages = sorted(page_texts.keys())

    for page_num in sorted_pages:
        text = page_texts[page_num]
        doc_type, is_continuation, confidence, primary_ref = classify_page(text)
        all_refs = extract_doc_refs(text)

        # --- continuation page → extend current doc ---
        if is_continuation:
            if current_doc:
                current_doc["page_end"] = page_num
                if all_refs:
                    current_doc["doc_refs"] = list(
                        set(current_doc.get("doc_refs", []) + all_refs)
                    )
            continue

        # --- decide if this is a NEW document ---
        is_new_doc = False
        if doc_type not in (DocType.UNKNOWN, DocType.FILLER):
            is_new_doc = True        # every non-continuation header = new doc
        elif current_doc is None:
            is_new_doc = True

        if is_new_doc:
            if current_doc:
                documents.append(current_doc)
            doc_counter += 1
            current_doc = {
                "doc_id": f"DOC-{doc_counter:04d}",
                "doc_type": doc_type.value if isinstance(doc_type, DocType) else doc_type,
                "page_start": page_num,
                "page_end": page_num,
                "primary_ref": primary_ref or "",
                "doc_refs": all_refs,
                "confidence": confidence,
            }
        elif current_doc:
            # UNKNOWN / FILLER page → extend current
            current_doc["page_end"] = page_num
            if all_refs:
                current_doc["doc_refs"] = list(
                    set(current_doc.get("doc_refs", []) + all_refs)
                )

    if current_doc:
        documents.append(current_doc)

    # Save
    out_path = paths.SPLIT_DOCS / "document_splits.json"
    out_path.write_text(json.dumps(documents, indent=2, default=str))
    log.info(f"Split into {len(documents)} logical documents")
    return documents
