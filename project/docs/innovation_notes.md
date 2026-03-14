# Innovation Notes

## Core Innovation: Deterministic-First, LLM-Second

Instead of sending everything to an LLM for classification, our pipeline uses deterministic computation as the primary detection layer:

- **Decimal arithmetic** for money math (no floating-point errors)
- **Regex classifiers** for document type detection
- **Rule-based validators** for dates, GST rates, GSTIN format
- **Graph algorithms** for circular references
- **Fuzzy matching** (rapidfuzz) for vendor name typos

LLM calls are reserved for structured extraction (turning raw text into records) and ambiguous cases where rules alone can't decide.

## Multi-Index Strategy

We maintain two parallel index structures:
1. **DuckDB** — columnar analytics engine for SQL queries (aggregations, joins, range scans)
2. **NetworkX** — directed graph for relationship traversal and cycle detection

This allows detectors to use the right tool: SQL for "find all invoices from vendor X" and graph traversal for "does this credit note chain form a cycle?"

## Evidence-Oriented Findings

Every finding carries full provenance:
- Source page numbers (for human verification)
- Document references (invoice/PO numbers)
- Confidence score (0.0–1.0)
- Free-text explanation
- Detector-specific metadata

## Precision-First Design

The pipeline is tuned for precision over recall:
- Per-category confidence thresholds (higher for noisier categories)
- Cross-category conflict resolution (e.g., `fake_vendor` suppressed when `vendor_name_typo` is more specific)
- Deduplication by (page, category, evidence overlap)
- Conservative default thresholds that can be relaxed after initial run

## Resumable Pipeline

Each stage caches its outputs. If the pipeline fails at Stage 4, you can fix the issue and resume from Stage 4 with `--from-stage 4`, reusing all prior work. API responses are cached per-page, so re-runs don't waste API credits.

## Structured Extraction via Prompt Engineering

Each document type has a custom extraction prompt that:
1. Provides the document text
2. Specifies the exact JSON schema expected
3. Includes examples of edge cases (partial amounts, alternate date formats)
4. Requests the LLM output ONLY valid JSON (no preamble)

This produces Pydantic-validated structured records with >95% parse success rate.
