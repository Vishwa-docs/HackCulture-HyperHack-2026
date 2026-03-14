"""Inspect expense reports and credit/debit notes."""
import fitz, json, re

with open('data/split_docs/document_splits.json') as f:
    docs = json.load(f)
pdf = fitz.open('data/input/gauntlet.pdf')

# Check expense reports
exp_docs = [d for d in docs if d['doc_type'] == 'expense_report']
print(f'Total expense reports: {len(exp_docs)}')

for d in exp_docs[:2]:
    ps, pe = d['page_start'], d['page_end']
    text = ''
    for p in range(ps-1, pe):
        text += pdf[p].get_text()
    print(f'\n=== {d["primary_ref"]} pages {ps}-{pe} ===')
    print(text[:2500])

# credit/debit notes
cn_docs = [d for d in docs if d['doc_type'] in ('credit_note', 'debit_note')]
print(f'\n\nTotal credit/debit notes: {len(cn_docs)}')
for d in cn_docs[:3]:
    ps, pe = d['page_start'], d['page_end']
    text = ''
    for p in range(ps-1, pe):
        text += pdf[p].get_text()
    print(f'\n=== {d["primary_ref"]} type={d["doc_type"]} pages {ps}-{pe} ===')
    print(text[:2000])

pdf.close()
