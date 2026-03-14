#!/usr/bin/env python3
import json
from collections import Counter

v3 = json.load(open('data/outputs/submission_v3.json'))
v4 = json.load(open('data/outputs/submission_v4.json'))

def make_key(f):
    return (f['category'], tuple(sorted(f.get('document_refs',[]))))

v3_keys = {}
for f in v3['findings']:
    k = make_key(f)
    v3_keys[k] = f

v4_keys = {}
for f in v4['findings']:
    k = make_key(f)
    v4_keys[k] = f

only_v3 = set(v3_keys.keys()) - set(v4_keys.keys())
only_v4 = set(v4_keys.keys()) - set(v3_keys.keys())
in_both = set(v3_keys.keys()) & set(v4_keys.keys())

print(f'=== v3: {len(v3["findings"])} findings, v4: {len(v4["findings"])} findings ===')
print(f'In both: {len(in_both)}')
print(f'Only in v3: {len(only_v3)}')
print(f'Only in v4: {len(only_v4)}')

print('\n=== ONLY IN V3 (removed in v4) ===')
for k in sorted(only_v3):
    f = v3_keys[k]
    print(f'  {f["category"]:30s} refs={f["document_refs"]} pages={f["pages"]}')
    print(f'    desc: {f["description"][:120]}')
    print(f'    reported: {f["reported_value"]} correct: {f["correct_value"]}')

print('\n=== ONLY IN V4 (added in v4) ===')
for k in sorted(only_v4):
    f = v4_keys[k]
    print(f'  {f["category"]:30s} refs={f["document_refs"]} pages={f["pages"]}')
    print(f'    desc: {f["description"][:120]}')
    print(f'    reported: {f["reported_value"]} correct: {f["correct_value"]}')

print('\n=== CHANGED VALUES (same key, diff fields) ===')
for k in sorted(in_both):
    f3 = v3_keys[k]
    f4 = v4_keys[k]
    if f3.get('reported_value') != f4.get('reported_value') or f3.get('correct_value') != f4.get('correct_value') or f3.get('pages') != f4.get('pages'):
        print(f'  {f3["category"]:30s} refs={f3["document_refs"]}')
        if f3.get('pages') != f4.get('pages'):
            print(f'    pages: {f3["pages"]} -> {f4["pages"]}')
        if f3.get('reported_value') != f4.get('reported_value'):
            print(f'    reported: {f3["reported_value"]} -> {f4["reported_value"]}')
        if f3.get('correct_value') != f4.get('correct_value'):
            print(f'    correct: {f3["correct_value"]} -> {f4["correct_value"]}')

# Category breakdown
print('\n=== CATEGORY COUNTS v3 vs v4 ===')
v3_cats = Counter(f['category'] for f in v3['findings'])
v4_cats = Counter(f['category'] for f in v4['findings'])
all_cats = sorted(set(list(v3_cats.keys()) + list(v4_cats.keys())))
for cat in all_cats:
    c3 = v3_cats.get(cat, 0)
    c4 = v4_cats.get(cat, 0)
    diff = c4 - c3
    mark = ' <--' if diff != 0 else ''
    print(f'  {cat:30s}: v3={c3:2d}  v4={c4:2d}  diff={diff:+d}{mark}')
