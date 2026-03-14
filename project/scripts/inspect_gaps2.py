#!/usr/bin/env python3
import json, re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

d = json.load(open('data/extracted/all_extracted.json'))
vm = json.load(open('data/extracted/vendor_master.json'))

# 1. WRONG TAX RATE: Parse from raw text
print("=== INVOICE GST RATE FROM RAW TEXT ===")
rates_found = {}
for inv in d['invoices'][:20]:
    raw = inv.get('raw_text', '')
    # Look for GST @XX%
    m = re.search(r'GST\s*[@]\s*(\d+(?:\.\d+)?)\s*%', raw, re.IGNORECASE)
    if not m:
        m = re.search(r'CGST\s*[@]\s*(\d+(?:\.\d+)?)\s*%', raw, re.IGNORECASE)
    if not m:
        m = re.search(r'(?:GST|IGST|CGST|SGST)\s*\(\s*(\d+(?:\.\d+)?)\s*%\)', raw, re.IGNORECASE)
    if m:
        rate = m.group(1)
        rates_found[inv['invoice_number']] = rate

if rates_found:
    print(f"  Found rates in {len(rates_found)} invoices")
    for k, v in list(rates_found.items())[:5]:
        print(f"    {k}: {v}%")
else:
    # Try different patterns
    print("  No GST @X% pattern found, checking raw text...")
    sample_raw = d['invoices'][0].get('raw_text', '')
    # Find all lines with GST/tax
    for line in sample_raw.split('\n'):
        if any(w in line.upper() for w in ['GST', 'TAX', 'CGST', 'SGST', 'IGST']):
            print(f"  TAX LINE: {line.strip()}")

# 2. GSTIN STATE MISMATCH - check invoice GSTINs vs vendor master
print("\n=== INVOICE GSTIN VS VENDOR STATE ===")
GST_STATE_CODES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "25": "Daman & Diu", "26": "Dadra & Nagar Haveli",
    "27": "Maharashtra", "28": "Andhra Pradesh", "29": "Karnataka",
    "30": "Goa", "31": "Lakshadweep", "32": "Kerala",
    "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman & Nicobar Islands", "36": "Telangana",
    "37": "Andhra Pradesh", "38": "Ladakh",
}

# Build vendor GSTIN lookup
vendor_by_gstin = {}
for v in vm:
    g = v.get('gstin','').upper()
    if g:
        vendor_by_gstin[g] = v

mismatches = []
for inv in d['invoices']:
    inv_gstin = inv.get('gstin_vendor', '').strip().upper()
    if not inv_gstin or len(inv_gstin) < 2:
        continue
    
    # Check if this GSTIN is in vendor master
    if inv_gstin in vendor_by_gstin:
        # GSTIN matches vendor master exactly, check state code
        vendor = vendor_by_gstin[inv_gstin]
        code = inv_gstin[:2]
        expected_state = GST_STATE_CODES.get(code, '')
        vendor_state = vendor.get('state', '')
        if expected_state and vendor_state and expected_state.lower() != vendor_state.lower():
            mismatches.append((inv['invoice_number'], inv_gstin, code, expected_state, vendor_state))
    else:
        # Invoice GSTIN doesn't match any vendor master GSTIN
        # Check if the first 2 digits differ from the vendor's GSTIN
        vendor_name = inv.get('vendor_name_raw', '')
        for v in vm:
            if v['canonical_name'].lower() == vendor_name.lower() or v['raw_name'].lower() == vendor_name.lower():
                master_gstin = v.get('gstin','').upper()
                if master_gstin and inv_gstin[:2] != master_gstin[:2]:
                    mismatches.append((inv['invoice_number'], inv_gstin, master_gstin, 'Invoice has different state code', v['state']))

print(f"  GSTIN mismatches found: {len(mismatches)}")
for m in mismatches[:10]:
    print(f"    {m}")

# 3. DUPLICATE EXPENSE - broaden matching
print("\n=== DUPLICATE EXPENSE - BROADER ===")
all_exp = []
for er in d['expense_reports']:
    for el in er.get('expense_lines', []):
        all_exp.append({
            'report_id': er.get('report_id',''),
            'employee_id': er.get('employee_id',''),
            'employee_name': er.get('employee_name',''),
            'amount': el.get('amount',''),
            'date': el.get('date',''),
            'description': el.get('description',''),
            'category': el.get('category',''),
            'merchant': el.get('merchant',''),
        })

# Try: same amount + same description across ANY two reports (regardless of employee)
groups = defaultdict(list)
for exp in all_exp:
    key = f"{exp['amount']}|{exp['description']}"
    groups[key].append(exp)

dupes = {k: v for k, v in groups.items() if len(v) >= 2 and len(set(e['report_id'] for e in v)) >= 2}
print(f"  Same amount+description, diff reports: {len(dupes)}")
for k, v in list(dupes.items())[:5]:
    rids = sorted(set(e['report_id'] for e in v))
    print(f"    {k}: reports={rids}")

# Try: same employee + same amount across diff reports
groups2 = defaultdict(list)
for exp in all_exp:
    key = f"{exp['employee_id']}|{exp['amount']}"
    groups2[key].append(exp)

dupes2 = {k: v for k, v in groups2.items() if len(v) >= 2 and len(set(e['report_id'] for e in v)) >= 2}
print(f"  Same employee+amount, diff reports: {len(dupes2)}")
for k, v in list(dupes2.items())[:5]:
    rids = sorted(set(e['report_id'] for e in v))
    print(f"    {k}: reports={rids}, descs={[e['description'][:30] for e in v]}")

# 4. TRIPLE EXPENSE - check hotel stays
print("\n=== TRIPLE EXPENSE CLAIM ===")
# Group by employee + hotel name
hotel_groups = defaultdict(list)
for er in d['expense_reports']:
    hotel = er.get('hotel_name','').strip()
    emp = er.get('employee_id','').strip()
    if hotel and emp:
        hotel_groups[f"{emp}|{hotel.upper()}"].append(er)

triples = {k: v for k, v in hotel_groups.items() if len(v) >= 3}
print(f"  Triple hotel stays (emp+hotel in 3+ reports): {len(triples)}")
for k, v in list(triples.items())[:5]:
    print(f"    {k}: reports={[e['report_id'] for e in v]}")

# Try without employee - same hotel in 3+ reports
hotel_only = defaultdict(list)
for er in d['expense_reports']:
    hotel = er.get('hotel_name','').strip().upper()
    if hotel:
        hotel_only[hotel].append(er)

triples2 = {k: v for k, v in hotel_only.items() if len(v) >= 3}
print(f"  Same hotel in 3+ reports (any employee): {len(triples2)}")
for k, v in list(triples2.items())[:5]:
    rids = [e['report_id'] for e in v]
    emps = [e['employee_id'] for e in v]
    print(f"    {k}: reports={rids}, employees={emps}")

# 5. CIRCULAR REFERENCE - trace chains
print("\n=== CIRCULAR REFERENCE CHAIN ANALYSIS ===")
# Build adjacency graph
graph = {}
all_note_ids = set()
for cn in d['credit_debit_notes']:
    nn = cn.get('note_number', '')
    all_note_ids.add(nn)
    refs = cn.get('linked_documents', [])
    ref = cn.get('referenced_doc', '')
    target = cn.get('target_doc', '')
    
    neighbors = set()
    if refs:
        neighbors.update(refs)
    if ref:
        neighbors.add(ref)
    if target:
        neighbors.add(target)
    neighbors.discard(nn)
    
    graph[nn] = list(neighbors)

print(f"  Graph nodes: {len(graph)}")
for node, neighbors in sorted(graph.items()):
    in_dataset = all(n in graph for n in neighbors)
    print(f"    {node} -> {neighbors} {'(all in dataset)' if in_dataset else '(DANGLING)'}")

# Find connected components / chains
visited = set()
def trace_chain(node, chain=None, visited_local=None):
    if chain is None:
        chain = []
    if visited_local is None:
        visited_local = set()
    
    if node in visited_local:
        return chain  # cycle detected
    
    chain.append(node)
    visited_local.add(node)
    visited.add(node)
    
    for neighbor in graph.get(node, []):
        if neighbor not in visited_local:
            trace_chain(neighbor, chain, visited_local)
    
    return chain

print("\n  Connected components:")
for node in sorted(graph.keys()):
    if node not in visited:
        chain = trace_chain(node)
        # Check for cycles within component
        has_cycle = False
        for n in chain:
            for neighbor in graph.get(n, []):
                if neighbor in chain and neighbor != n:
                    has_cycle = True
        print(f"    Component: {chain} (cycle={has_cycle})")
