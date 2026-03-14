# Needle Finder — Financial Needle in the Haystack

A production-style CLI pipeline that ingests `gauntlet.pdf` (a 1,000-page AP bundle), parses and splits the document, extracts structured financial data, cross-references records, detects 200 deliberate errors across 20 categories, and emits a final JSON submission.

## Quick Start

```bash
# 1. Clone and enter project
cd project/

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy .env.example to .env and fill in keys
cp .env.example .env

# 4. Place gauntlet.pdf
cp gauntlet.pdf data/input/

# 5. Bootstrap (verify setup)
python3 -m src.cli bootstrap

# 6. Run full pipeline
python3 -m src.cli run-all --team-id hackculture
```

## Architecture

```
PDF (1000 pages)
  │
  ├─ Stage 1: INGEST ─── PyMuPDF text extraction → page_texts.json
  ├─ Stage 2: SPLIT ──── Heuristic + pattern-based doc splitting
  ├─ Stage 3: VENDOR ─── Vendor Master extraction (pages 3-4)
  ├─ Stage 4: EXTRACT ── LLM-based structured extraction per doc type
  ├─ Stage 5: INDEX ──── DuckDB analytical + NetworkX graph indexes
  ├─ Stage 6: DETECT ─── 20 category-specific detectors
  └─ Stage 7: FINALIZE ─ Adjudication + confidence + dedup → submission.json
```

## Pipeline Stages

| Stage | Command | Description |
|-------|---------|-------------|
| 1-2 | `python3 -m src.cli ingest` | Parse PDF, split into documents |
| 3-4 | `python3 -m src.cli extract` | Extract vendor master + entities |
| 5 | `python3 -m src.cli index` | Build DuckDB + graph indexes |
| 6 | `python3 -m src.cli detect` | Run all 20 detector categories |
| 7 | `python3 -m src.cli finalize` | Adjudicate and write JSON |
| 1-7 | `python3 -m src.cli run-all` | Full end-to-end pipeline |

## CLI Options

```bash
python3 -m src.cli run-all \
  --input data/input/gauntlet.pdf \
  --team-id hackculture \
  --from-stage 1 \
  --to-stage 7 \
  --only-category arithmetic_error \
  --limit-pages 100 \
  --resume
```

## Detection Categories

### Easy (5)
| Category | Method |
|----------|--------|
| arithmetic_error | Decimal recomputation of qty×rate, subtotals, tax, grand total |
| billing_typo | HH:MM time format confusion (0.15 → 0.25 decimal hours) |
| duplicate_line_item | Signature-based duplicate detection within invoice |
| invalid_date | Calendar validation (Feb 31, Sep 31, leap year, etc.) |
| wrong_tax_rate | GST rate vs HSN/SAC/service type validation |

### Medium (7)
| Category | Method |
|----------|--------|
| po_invoice_mismatch | PO↔Invoice line item qty/rate comparison |
| vendor_name_typo | Fuzzy match against Vendor Master with GSTIN support |
| double_payment | Bank statement transaction clustering across months |
| ifsc_mismatch | Invoice IFSC vs Vendor Master IFSC |
| duplicate_expense | Employee+merchant+date+amount clustering across reports |
| date_cascade | Invoice date < PO date detection |
| gstin_state_mismatch | GSTIN state code vs registered state |

### Evil (8)
| Category | Method |
|----------|--------|
| quantity_accumulation | Cumulative invoice qty > 120% of PO qty |
| price_escalation | All invoices exceed PO contracted rate |
| balance_drift | Opening balance ≠ prior month closing balance |
| circular_reference | Graph cycle detection in credit/debit note chains |
| triple_expense_claim | Same hotel stay in 3+ expense reports |
| employee_id_collision | Same ID, different names (fuzzy-verified) |
| fake_vendor | No match in Vendor Master (name/GSTIN/IFSC) |
| phantom_po_reference | Invoice cites non-existent PO number |

## Outputs

| File | Description |
|------|-------------|
| `data/outputs/submission.json` | Final submission (compact JSON) |
| `data/outputs/submission_pretty.json` | Pretty-printed submission |
| `data/outputs/all_candidates.json` | All findings including rejected |
| `data/outputs/rejected_candidates.json` | Rejected findings with reasons |
| `data/outputs/findings.csv` | CSV for spreadsheet review |
| `data/outputs/analytics_summary.json` | Detection statistics |

## Running Tests

```bash
python3 -m pytest tests/ -v
```

## Key Design Decisions

1. **Deterministic-first**: Rules and arithmetic before LLM calls
2. **Confidence gating**: Category-specific thresholds, reject weak findings
3. **Cross-category dedup**: Prevents fake_vendor vs vendor_name_typo conflicts
4. **Evidence provenance**: Every finding has source pages and document_refs
5. **Decimal arithmetic**: No float for money math
6. **Multi-index**: DuckDB for SQL + NetworkX for graph + cached API responses
7. **Resumability**: Each stage caches outputs; re-run from any stage

## Tuning

Edit `configs/category_thresholds.yaml` to adjust per-category confidence thresholds.
Higher thresholds = fewer false positives but may miss some needles.

## Project Structure

```
project/
├── src/
│   ├── cli.py                      # CLI entry point
│   ├── core/                       # Config, models, enums, utils
│   ├── ingestion/                  # PDF parsing, HyperAPI, Bedrock, splitting
│   ├── extraction/                 # Vendor master, LLM structured extraction
│   ├── normalization/              # Dates, money, vendor names, IDs
│   ├── storage/                    # DuckDB, graph store
│   ├── detectors/{easy,medium,evil}/ # 20 detector implementations
│   ├── adjudication/               # Confidence scoring, dedup, filtering
│   ├── output/                     # JSON/CSV formatting
│   └── pipelines/                  # End-to-end orchestration
├── tests/                          # 45+ unit tests
├── configs/                        # YAML configuration
├── data/                           # Input, cache, outputs
└── docs/                           # Architecture, innovation notes
```
