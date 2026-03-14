"""Document ID and reference normalization."""
import re


def normalize_invoice_number(ref: str) -> str:
    """Normalize invoice number for matching."""
    s = ref.strip().upper()
    s = re.sub(r'\s+', '', s)
    # Normalize leading zeros in numeric suffix
    m = re.match(r'(INV[-/]?\d{4}[-/]?)0*(\d+)', s)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return s


def normalize_po_number(ref: str) -> str:
    """Normalize PO number for matching."""
    s = ref.strip().upper()
    s = re.sub(r'\s+', '', s)
    m = re.match(r'(PO[-/]?\d{4}[-/]?)0*(\d+)', s)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return s


def normalize_doc_ref(ref: str) -> str:
    """Generic document reference normalization."""
    s = ref.strip().upper()
    s = re.sub(r'\s+', '', s)
    return s


def extract_all_refs(text: str) -> dict[str, list[str]]:
    """Extract all document references from text."""
    refs = {"invoices": [], "pos": [], "credit_notes": [], "debit_notes": [],
            "expense_reports": [], "receipts": [], "other": []}

    inv_matches = re.findall(r'(?:INV|INVOICE)[-#:\s]*(\S+)', text, re.IGNORECASE)
    refs["invoices"] = [normalize_invoice_number(f"INV-{m}") for m in inv_matches]

    po_matches = re.findall(r'(?:PO|P\.O\.|PURCHASE\s*ORDER)[-#:\s]*(\S+)', text, re.IGNORECASE)
    refs["pos"] = [normalize_po_number(f"PO-{m}") for m in po_matches]

    cn_matches = re.findall(r'(?:CN|CREDIT\s*NOTE)[-#:\s]*(\S+)', text, re.IGNORECASE)
    refs["credit_notes"] = cn_matches

    dn_matches = re.findall(r'(?:DN|DEBIT\s*NOTE)[-#:\s]*(\S+)', text, re.IGNORECASE)
    refs["debit_notes"] = dn_matches

    exp_matches = re.findall(r'(?:EXP|EXPENSE)[-#:\s]*(\S+)', text, re.IGNORECASE)
    refs["expense_reports"] = exp_matches

    # Standard format refs
    std_refs = re.findall(r'[A-Z]{2,4}-\d{4}-\d{3,6}', text)
    for r in std_refs:
        if r.startswith("INV") and r not in refs["invoices"]:
            refs["invoices"].append(r)
        elif r.startswith("PO") and r not in refs["pos"]:
            refs["pos"].append(r)
        elif r.startswith("CN") and r not in refs["credit_notes"]:
            refs["credit_notes"].append(r)
        elif r.startswith("DN") and r not in refs["debit_notes"]:
            refs["debit_notes"].append(r)
        elif r.startswith("EXP") and r not in refs["expense_reports"]:
            refs["expense_reports"].append(r)
        elif r not in refs["other"]:
            refs["other"].append(r)

    return refs
