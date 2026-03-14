# Prompt Registry

All LLM prompts used in the pipeline, organized by module.

## Extraction Prompts

### Invoice Extraction (`src/extraction/llm_structured_extract.py`)
```
Extract structured invoice data from the following document text.
Return ONLY valid JSON with these fields:
- invoice_number, invoice_date, due_date
- vendor_name, vendor_gstin, vendor_ifsc
- bill_to_name, bill_to_gstin, ship_to_name
- po_reference
- currency (default INR)
- line_items: [{description, hsn_sac, qty, unit, rate, amount, gst_rate, gst_amount}]
- subtotal, total_gst, grand_total
- payment_terms, bank_account, notes
```

### Purchase Order Extraction
```
Extract structured purchase order data...
- po_number, po_date, delivery_date, vendor_name, vendor_gstin
- line_items: [{description, hsn_sac, qty, unit, rate, amount}]
- total_amount, terms, delivery_address
```

### Bank Statement Extraction
```
Extract bank statement data...
- account_number, account_holder, bank_name, ifsc
- statement_month, statement_year
- opening_balance, closing_balance
- transactions: [{date, description, reference, debit, credit, balance}]
```

### Expense Report Extraction
```
Extract expense report data...
- report_id, employee_name, employee_id, department
- report_date, period_start, period_end, approver
- lines: [{date, category, merchant, description, amount, receipt_ref}]
- total_amount, advance_received, net_payable
```

### Credit/Debit Note Extraction
```
Extract credit or debit note data...
- note_number, note_type (credit/debit), note_date
- vendor_name, vendor_gstin
- original_invoice_ref, reason
- line_items: [{description, qty, rate, amount}]
- total_amount, gst_amount, net_amount, linked_documents
```

## Vendor Master Extraction (`src/extraction/vendor_master.py`)
```
Extract vendor master information from this text.
Return JSON array of vendors, each with:
- vendor_id, vendor_name, gstin, pan, ifsc
- bank_account, bank_name, address, state, state_code
- contact_person, phone, email, category, credit_terms
```

## Classification Prompt (not currently LLM-based)
Document classification uses regex patterns. If LLM fallback is needed:
```
Classify this document page as one of:
VENDOR_MASTER, INVOICE, PURCHASE_ORDER, BANK_STATEMENT,
EXPENSE_REPORT, CREDIT_NOTE, DEBIT_NOTE, REMITTANCE_ADVICE,
DELIVERY_CHALLAN, COVER_PAGE, TABLE_OF_CONTENTS, UNKNOWN
```
