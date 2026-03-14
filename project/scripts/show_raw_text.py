"""Show raw text of sample documents to debug regex patterns."""
import json

page_texts = json.load(open("data/parsed/page_texts.json"))

# Bank statement page 834-835
print("=== BANK STATEMENT (page 834) ===")
print(page_texts.get("834", "N/A")[:2000])
print()

# Expense report page 897
print("=== EXPENSE REPORT (page 897) ===")
print(page_texts.get("897", "N/A")[:2000])
print()

# PO without number - page 12
print("=== PURCHASE ORDER (page 12) ===")
print(page_texts.get("12", "N/A")[:2000])
print()

# Invoice with line items - page 5
print("=== INVOICE (page 5) ===")
print(page_texts.get("5", "N/A")[:2000])
