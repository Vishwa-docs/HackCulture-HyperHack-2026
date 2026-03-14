"""Analyze findings distribution and sample some to check quality."""
import json

submission = json.load(open("data/outputs/submission_pretty.json"))
findings = submission["findings"]

from collections import Counter
cats = Counter(f["category"] for f in findings)
print(f"Total findings: {len(findings)}")
print(f"\nCategory distribution:")
for cat, count in cats.most_common():
    print(f"  {cat}: {count}")

# Sample arithmetic errors
print("\n=== ARITHMETIC ERROR SAMPLES ===")
arith = [f for f in findings if f["category"] == "arithmetic_error"]
for f in arith[:5]:
    print(f"  {f['finding_id']}: {f['document_refs']} pages={f['pages']}")
    print(f"    {f['description'][:100]}")

# Sample IFSC mismatches
print("\n=== IFSC MISMATCH SAMPLES ===")
ifsc = [f for f in findings if f["category"] == "ifsc_mismatch"]
for f in ifsc[:5]:
    print(f"  {f['finding_id']}: {f['document_refs']} pages={f['pages']}")
    print(f"    {f['description'][:120]}")

# Sample date cascades
print("\n=== DATE CASCADE SAMPLES ===")
dc = [f for f in findings if f["category"] == "date_cascade"]
for f in dc[:5]:
    print(f"  {f['finding_id']}: {f['document_refs']} pages={f['pages']}")
    print(f"    {f['description'][:120]}")
