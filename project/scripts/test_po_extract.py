"""Test PO line item extraction after fix."""
import fitz, json, sys
sys.path.insert(0, 'src')
from extraction.text_extract import extract_po_from_text

with open('data/split_docs/document_splits.json') as f:
    docs = json.load(f)

pdf = fitz.open('data/input/gauntlet.pdf')
po_docs = [d for d in docs if d['doc_type'] == 'purchase_order']

total_items = 0
po_with_items = 0
po_no_items = 0
for d in po_docs:
    ps, pe = d['page_start'], d['page_end']
    text = ''
    for p in range(ps-1, pe):
        text += pdf[p].get_text() + '\n'
    result = extract_po_from_text(text, list(range(ps, pe+1)), d['doc_id'])
    if result and result.line_items:
        n = len(result.line_items)
        total_items += n
        po_with_items += 1
        if po_with_items <= 3:
            print(f'{result.po_number}: {n} items')
            for li in result.line_items:
                print(f'  #{li.line_num} {li.description} qty={li.quantity} rate={li.unit_rate} amt={li.amount} hsn={li.hsn_sac}')
    elif result:
        po_no_items += 1
        if po_no_items <= 3:
            print(f'{result.po_number}: 0 items')

print(f'\nPOs with items: {po_with_items}/{len(po_docs)}, total items: {total_items}')
print(f'POs without items: {po_no_items}')
pdf.close()
