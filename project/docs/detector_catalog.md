# Detector Catalog

Complete reference for all 20 error detection categories.

## Easy Detectors

### 1. arithmetic_error
**File**: `src/detectors/easy/arithmetic_error.py`
**Logic**: Recomputes qty × rate for each line item, sums subtotal, verifies tax computation, checks grand total. Uses `Decimal` arithmetic with 0.01 tolerance.
**Catches**: Wrong line amounts, subtotal mismatches, tax computation errors, grand total drift.

### 2. billing_typo
**File**: `src/detectors/easy/billing_typo.py`
**Logic**: Detects HH:MM time format used as decimal hours (e.g., 2:15 treated as 2.15 instead of 2.25).
**Catches**: Time-based billing where minutes are treated as decimal fractions.

### 3. duplicate_line_item
**File**: `src/detectors/easy/duplicate_line_item.py`
**Logic**: Creates a signature from (description_normalized, qty, rate) for each line item within a single invoice. Detects exact and near-duplicate signatures.
**Catches**: Copy-paste line items within an invoice.

### 4. invalid_date
**File**: `src/detectors/easy/invalid_date.py`
**Logic**: Validates all date fields against calendar rules: max days per month, leap year rules, February constraints (28/29).
**Catches**: Feb 29 in non-leap years, Sep 31, Jun 31, etc.

### 5. wrong_tax_rate
**File**: `src/detectors/easy/wrong_tax_rate.py`
**Logic**: Cross-references line item GST rates against HSN/SAC code or service description. Validates against known GST rate tables.
**Catches**: 12% GST when HSN code requires 18%, etc.

## Medium Detectors

### 6. po_invoice_mismatch
**File**: `src/detectors/medium/po_invoice_mismatch.py`
**Logic**: Matches invoice line items to PO line items by description/HSN. Compares qty, rate, and amount.
**Catches**: Invoice qty ≠ PO qty, invoice rate ≠ PO rate, unauthorized line items.

### 7. vendor_name_typo
**File**: `src/detectors/medium/vendor_name_typo.py`
**Logic**: Fuzzy-matches document vendor names against Vendor Master using rapidfuzz. Score between 60-95 = likely typo; <60 = might be fake vendor.
**Catches**: "Acme Corp" vs "Acmee Corp", transposed characters, missing words.

### 8. double_payment
**File**: `src/detectors/medium/double_payment.py`
**Logic**: Clusters bank statement transactions by (vendor, amount, reference pattern). Detects same payment appearing in multiple months.
**Catches**: Same invoice paid twice across different bank statement periods.

### 9. ifsc_mismatch
**File**: `src/detectors/medium/ifsc_mismatch.py`
**Logic**: Compares IFSC code on invoice/remittance against Vendor Master IFSC for the same vendor.
**Catches**: Invoice shows different bank routing than vendor's registered bank.

### 10. duplicate_expense
**File**: `src/detectors/medium/duplicate_expense.py`
**Logic**: Groups expense lines by (employee_id, merchant_normalized, date, amount). 2+ matching lines across different reports = duplicate.
**Catches**: Same receipt submitted in two different expense reports.

### 11. date_cascade
**File**: `src/detectors/medium/date_cascade.py`
**Logic**: Checks that invoice_date >= po_date for linked INV→PO pairs. An invoice dated before its PO suggests backdating.
**Catches**: Invoice dated before the purchase order it references.

### 12. gstin_state_mismatch
**File**: `src/detectors/medium/gstin_state_mismatch.py`
**Logic**: Extracts the 2-digit state code from GSTIN and compares against the vendor's registered state.
**Catches**: GSTIN starting with 29 (Karnataka) but vendor registered in Maharashtra.

## Evil Detectors

### 13. quantity_accumulation
**File**: `src/detectors/evil/quantity_accumulation.py`
**Logic**: Sums all invoice quantities for a given PO line item. If cumulative invoice qty > 120% of PO qty, flags the excess.
**Catches**: Multiple small invoices that individually look fine but collectively exceed the PO authorization.

### 14. price_escalation
**File**: `src/detectors/evil/price_escalation.py`
**Logic**: Compares unit rates across all invoices against the PO contracted rate. If all invoices for a line item exceed the PO rate, flags escalation.
**Catches**: Gradual price creep where every invoice charges slightly more than the PO rate.

### 15. balance_drift
**File**: `src/detectors/evil/balance_drift.py`
**Logic**: Sorts bank statements chronologically. Checks that month N opening balance == month N-1 closing balance.
**Catches**: Opening balance adjusted between months (off by small amounts).

### 16. circular_reference
**File**: `src/detectors/evil/circular_reference.py`
**Logic**: Builds a directed graph of credit/debit note references. Uses NetworkX cycle detection to find loops (A→B→C→A).
**Catches**: Credit notes that reference each other in a cycle with no anchor to a real invoice.

### 17. triple_expense_claim
**File**: `src/detectors/evil/triple_expense_claim.py`
**Logic**: Groups expense lines by (merchant, date, amount) across ALL reports and employees. Flags items appearing in 3+ reports.
**Catches**: Same hotel stay claimed by three different employees (or same employee three times).

### 18. employee_id_collision
**File**: `src/detectors/evil/employee_id_collision.py`
**Logic**: Groups expense reports by employee_id. If the same ID maps to multiple distinct names (verified by low fuzzy match score), flags collision.
**Catches**: Two different people assigned the same employee ID.

### 19. fake_vendor
**File**: `src/detectors/evil/fake_vendor.py`
**Logic**: For each vendor appearing in invoices, checks if name, GSTIN, or IFSC match anything in the Vendor Master. Complete misses = fake vendor.
**Catches**: Invoices from vendors not in the approved vendor list.

### 20. phantom_po_reference
**File**: `src/detectors/evil/phantom_po_reference.py`
**Logic**: Collects all PO references cited in invoices. Checks each against the extracted PO index. Missing POs = phantom reference.
**Catches**: Invoice references "PO-9999" but that PO doesn't exist anywhere in the document bundle.
