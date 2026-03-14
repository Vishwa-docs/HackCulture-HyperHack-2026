"""Check document splits look reasonable."""
import json

docs = json.load(open("data/split_docs/document_splits.json"))
from collections import Counter

# Check page span distribution
spans = [(d["page_end"] - d["page_start"] + 1) for d in docs]
print(f"Total docs: {len(docs)}")
print(f"Page spans: min={min(spans)}, max={max(spans)}, median={sorted(spans)[len(spans)//2]}")
print(f"\nSpan distribution:")
for s in sorted(Counter(spans).items()):
    print(f"  {s[0]} pages: {s[1]} docs")

# Show a sample of each type
print("\nSample from each type:")
by_type = {}
for d in docs:
    by_type.setdefault(d["doc_type"], []).append(d)

for dtype, ddocs in sorted(by_type.items()):
    sample = ddocs[:3]
    print(f"\n  {dtype} ({len(ddocs)} docs):")
    for d in sample:
        ref = d.get("primary_ref", "")
        print(f"    {d['doc_id']} pages {d['page_start']}-{d['page_end']} ref={ref}")
