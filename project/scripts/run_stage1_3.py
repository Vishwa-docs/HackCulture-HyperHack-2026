"""Run pipeline stages 1-3 (no LLM needed)."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__) + "/..")
os.chdir(os.path.dirname(__file__) + "/..")

from dotenv import load_dotenv
load_dotenv()

from src.pipelines.run_all import Pipeline

p = Pipeline(team_id="hackculture")
p.run_all(from_stage=1, to_stage=3)

print(f"\nPages extracted: {len(p.page_texts)}")
print(f"Documents split: {len(p.documents)}")
print(f"Vendors found: {len(p.vendors)}")

# Show document type distribution
from collections import Counter
type_counts = Counter(d.get("doc_type", "?") for d in p.documents)
print("\nDocument type distribution:")
for dtype, count in type_counts.most_common():
    print(f"  {dtype}: {count}")

if p.vendors:
    print(f"\nFirst 3 vendors:")
    for v in p.vendors[:3]:
        print(f"  {v.vendor_id}: {v.canonical_name} | GSTIN={v.gstin} | IFSC={v.ifsc}")
