"""Show expense report + PO raw text for debugging."""
import json

page_texts = json.load(open("data/parsed/page_texts.json"))

# Expense report page 897
print("=== EXPENSE REPORT (page 897) ===")
print(page_texts.get("897", "N/A")[:3000])
print()

# PO page 15
print("=== PURCHASE ORDER (page 15) ===")
print(page_texts.get("15", "N/A")[:3000])
print()

# A 2-page invoice showing subtotal/tax/total
print("=== INVOICE PAGE 2 (page 6) ===")
print(page_texts.get("6", "N/A")[:3000])
