"""Quick PDF structure analysis."""
import fitz
import re

doc = fitz.open("data/input/gauntlet.pdf")
types = {}

for i in range(len(doc)):
    text = doc[i].get_text("text")[:500]
    if "TAX INVOICE" in text:
        types.setdefault("TAX INVOICE", []).append(i + 1)
    elif "PURCHASE ORDER" in text:
        types.setdefault("PURCHASE ORDER", []).append(i + 1)
    elif "BANK STATEMENT" in text or "Statement of Account" in text:
        types.setdefault("BANK STATEMENT", []).append(i + 1)
    elif "EXPENSE REPORT" in text or "EXPENSE CLAIM" in text:
        types.setdefault("EXPENSE REPORT", []).append(i + 1)
    elif "CREDIT NOTE" in text:
        types.setdefault("CREDIT NOTE", []).append(i + 1)
    elif "DEBIT NOTE" in text:
        types.setdefault("DEBIT NOTE", []).append(i + 1)
    elif "VENDOR MASTER" in text:
        types.setdefault("VENDOR MASTER", []).append(i + 1)
    elif "ANSWER FORMAT" in text:
        types.setdefault("ANSWER FORMAT", []).append(i + 1)
    elif "Hackathon" in text or "Gauntlet" in text:
        types.setdefault("COVER", []).append(i + 1)
    else:
        types.setdefault("OTHER", []).append(i + 1)

for k, v in sorted(types.items()):
    print(f"{k}: {len(v)} pages (first 5: {v[:5]})")

doc.close()
