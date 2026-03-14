#!/usr/bin/env python3
"""Quick analysis of what's likely failing per category."""
import json

sub = json.load(open('data/outputs/submission.json'))

# Count per category
from collections import Counter
cats = Counter(f['category'] for f in sub['findings'])

# Known targets
TARGETS = {
    "arithmetic_error": 12, "billing_typo": 4, "duplicate_line_item": 4,
    "invalid_date": 10, "wrong_tax_rate": 10,
    "po_invoice_mismatch": 15, "vendor_name_typo": 10, "double_payment": 10,
    "ifsc_mismatch": 5, "duplicate_expense": 10, "date_cascade": 5,
    "gstin_state_mismatch": 5,
    "quantity_accumulation": 35, "price_escalation": 10, "balance_drift": 15,
    "circular_reference": 8, "triple_expense_claim": 10,
    "employee_id_collision": 7, "fake_vendor": 10, "phantom_po_reference": 5,
}

# Score results: Easy=19/40, Medium=29/60, Evil=64/100
# Penalty=-44.5 means 89 false positives
EASY = ["arithmetic_error", "billing_typo", "duplicate_line_item", "invalid_date", "wrong_tax_rate"]
MEDIUM = ["po_invoice_mismatch", "vendor_name_typo", "double_payment", "ifsc_mismatch", "duplicate_expense", "date_cascade", "gstin_state_mismatch"]
EVIL = ["quantity_accumulation", "price_escalation", "balance_drift", "circular_reference", "triple_expense_claim", "employee_id_collision", "fake_vendor", "phantom_po_reference"]

print("=== SUBMISSIONS PER CATEGORY ===")
print(f"{'Category':35s} {'Submitted':>10s} {'Target':>8s} {'Over':>6s}")
total_over = 0
for cat in sorted(TARGETS.keys()):
    submitted = cats.get(cat, 0)
    target = TARGETS[cat]
    over = max(0, submitted - target)
    total_over += over
    tier = "EASY" if cat in EASY else "MED" if cat in MEDIUM else "EVIL"
    print(f"  {cat:33s} {submitted:10d} {target:8d} {over:6d}  [{tier}]")

print(f"\n  Total submitted: {sum(cats.values())}")
print(f"  Total target: {sum(TARGETS.values())}")
print(f"  Excess over targets: {total_over}")
print(f"\n  Easy submitted: {sum(cats.get(c,0) for c in EASY)} (target: 40)")
print(f"  Medium submitted: {sum(cats.get(c,0) for c in MEDIUM)} (target: 60)")
print(f"  Evil submitted: {sum(cats.get(c,0) for c in EVIL)} (target: 100)")

# Show sample findings for categories that are likely over-reporting
print("\n=== SAMPLE FINDINGS FOR OVER-REPORTING CATEGORIES ===")
for cat in ["wrong_tax_rate", "duplicate_expense", "triple_expense_claim"]:
    findings = [f for f in sub['findings'] if f['category'] == cat]
    print(f"\n--- {cat} ({len(findings)} submitted, target {TARGETS[cat]}) ---")
    for f in findings[:3]:
        print(f"  {f['finding_id']}: pages={f['pages'][:3]}, refs={f['document_refs'][:2]}")
        print(f"    {f['description'][:120]}")
        print(f"    reported={f['reported_value'][:60]}, correct={f['correct_value'][:60]}")
