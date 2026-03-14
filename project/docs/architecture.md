# Architecture

## System Overview

The Needle Finder pipeline uses a **multi-agent architecture** built on
**LangChain** and **LangGraph**.  Each of the 20 anomaly categories has a
dedicated **detection agent** (a LangChain ReAct agent backed by Claude on
AWS Bedrock) that owns the end-to-end lifecycle for its category — invoking
rule-based tools, reviewing candidates, and returning validated findings.
A **LangGraph orchestrator** coordinates the agents in three parallel tiers
and performs final adjudication.

```
┌──────────────────────────────────────────────────────────────┐
│                          CLI (Typer)                          │
├──────────────────────────────────────────────────────────────┤
│           LangGraph Pipeline Orchestrator                    │
│  ┌────────────────┬──────────────────┬─────────────────────┐ │
│  │  EASY TIER (5) │  MEDIUM TIER (7) │   EVIL TIER (8)     │ │
│  │  agents //     │  agents //       │   agents //         │ │
│  └────────────────┴──────────────────┴─────────────────────┘ │
│                      ↓ merge & rank                          │
│              Adjudication Node (top-N)                        │
├──────────────────────────────────────────────────────────────┤
│         LangChain ReAct Agents  ×  20 categories             │
│    ┌──────────────────────────────────────────────────┐      │
│    │  System Prompt  →  Tool Call  →  LLM Review      │      │
│    │  (category ctx)    (detector)    (validate/rank)  │      │
│    └──────────────────────────────────────────────────┘      │
├────────┬────────┬────────┬────────┬────────┬────────┬───────┤
│ Ingest │ Split  │Vendor  │Extract │ Index  │Detect  │Final  │
│        │        │Master  │        │        │Tools   │ize    │
├────────┴────────┴────────┴────────┴────────┴────────┴───────┤
│  Normalization Layer  │  Storage Layer  │  Config Layer      │
├───────────────────────┴─────────────────┴────────────────────┤
│  HyperAPI Client  │  Bedrock (LangChain)  │  PyMuPDF         │
└───────────────────┴───────────────────────┴──────────────────┘
```

## Agent Architecture

### Agent-per-Category Design

Each detection category is served by its own **LangChain ReAct agent**:

| Component | Technology | Purpose |
|-----------|-----------|---------|
| LLM | Claude Haiku 4.5 (Bedrock) via `langchain-aws` | Agent reasoning & tool orchestration |
| Tool | `@langchain_core.tools.tool` | Wraps rule-based detector function |
| Agent | `langgraph.prebuilt.create_react_agent` | ReAct loop: reason → act → observe |
| Orchestrator | `langgraph.StateGraph` | Multi-agent pipeline DAG |

### Agent Flow (per category)

```
┌─────────────────────────────────────────────────────┐
│  Detection Agent (e.g. arithmetic_error)            │
│                                                     │
│  1. Receives system prompt with category context    │
│  2. Calls detection tool (rule-based scanner)       │
│  3. Reviews tool output (candidate findings)        │
│  4. Ranks by confidence, selects top-N              │
│  5. Returns validated JSON findings                 │
└─────────────────────────────────────────────────────┘
```

### Pipeline Orchestration (LangGraph)

```
START → initialise → easy_tier → medium_tier → evil_tier → adjudicate → END
              │          │              │              │
              │     5 agents        7 agents       8 agents
              │    (parallel)      (parallel)      (parallel)
              │          │              │              │
              │          └──────────────┴──────────────┘
              │                         │
              │                    merge results
              │                    rank by confidence
              │                    cap per-category (top-N)
              │                    assign finding IDs
              │                         │
              └─────────────────── submission.json
```

### Key Files

| File | Purpose |
|------|---------|
| `src/agents/llm.py` | LangChain ChatBedrockConverse wrapper |
| `src/agents/tools.py` | 20 `@tool`-decorated detection functions |
| `src/agents/detection_agents.py` | Per-category ReAct agent builders |
| `src/agents/orchestrator.py` | LangGraph StateGraph pipeline |
| `scripts/run_detection.py` | Entry point (`python run_detection.py agent`) |

## Data Flow

1. **Ingest** (Stage 1): PyMuPDF opens the PDF, extracts text per page, renders page images for HyperAPI OCR.
2. **Split** (Stage 2): Regex classifiers assign each page a `DocType`. Contiguous same-type pages are grouped into logical documents. Document boundaries are detected by reference number changes.
3. **Vendor Master** (Stage 3): Pages 3-4 contain the vendor master table. Regex + LLM fallback parse vendor records.
4. **Extract** (Stage 4): Each logical document is sent to Bedrock Claude for structured extraction. Type-specific prompts produce Pydantic-validated records (InvoiceRecord, PurchaseOrderRecord, etc.).
5. **Index** (Stage 5): Records are inserted into DuckDB (for SQL analytics) and a NetworkX graph (for relationship traversal).
6. **Detect** (Stage 6): All 20 detectors run against the indexed data, producing `FindingCandidate` objects.
7. **Finalize** (Stage 7): Candidates pass through confidence thresholds, deduplication, and cross-category conflict resolution. Survivors are assigned IDs and written to `submission.json`.

## Storage Strategy

### DuckDB (Analytical)
- 9 tables: pages, documents, vendors, invoices, purchase_orders, bank_statements, expense_reports, credit_debit_notes, findings
- Used for: aggregations, joins, range scans, duplicate detection

### NetworkX (Graph)
- Nodes: documents, invoices, POs, credit/debit notes
- Edges: references between documents (INV→PO, CN→INV, DN→INV)
- Used for: circular reference detection, link traversal, phantom PO discovery

### File Cache
- Stage outputs cached as JSON in `data/cache/`
- API responses cached per page in `data/cache/hyperapi/` and `data/cache/bedrock/`
- Enables resume from any stage

## Detection Architecture

All detectors inherit from `BaseDetector` and are **wrapped as LangChain tools**
consumed by per-category ReAct agents:

```python
# Base detector pattern (rule-based logic)
class BaseDetector(ABC):
    def detect(self, store, graph, vendors, ...) -> List[FindingCandidate]
    def make_finding(self, category, page, ...) -> FindingCandidate

# LangChain tool wrapper
@tool
def detect_arithmetic_errors(query: str = "") -> str:
    """Scan invoices for arithmetic errors..."""
    return run_detector("detect_arithmetic_error", invoices)

# Agent that owns the category
agent = create_react_agent(
    model=ChatBedrockConverse(model="claude-haiku-4.5"),
    tools=[detect_arithmetic_errors],
    prompt=category_system_prompt,
)
```

Detectors are organized by difficulty:
- `src/detectors/easy/` — 5 detectors (arithmetic, date, tax, typo, duplicate)
- `src/detectors/medium/` — 7 detectors (PO mismatch, vendor, payment, IFSC, expense, date cascade, GSTIN)
- `src/detectors/evil/` — 8 detectors (accumulation, escalation, drift, circular, triple claim, ID collision, fake vendor, phantom PO)

## Adjudication

1. **Agent Self-Review**: Each agent reviews its tool output before returning findings
2. **Threshold Gating**: Per-category minimum confidence from `category_thresholds.yaml`
3. **Deduplication**: Same page + category + overlapping evidence = duplicate
4. **Cross-Category Check**: `fake_vendor` findings suppressed if `vendor_name_typo` already found for same vendor
5. **Top-N Selection**: LangGraph adjudication node caps per-category counts to target
6. **ID Assignment**: Sequential `F-NNN` IDs assigned after filtering

## External Dependencies

| Service | Usage | Fallback |
|---------|-------|----------|
| HyperAPI | OCR, field extraction, line items | PyMuPDF text extraction |
| AWS Bedrock (Claude Sonnet 4.6) | Structured extraction, complex reasoning | Regex-based extraction |
| AWS Bedrock (Claude Haiku 4.5) | Agent reasoning, tool orchestration | Direct rule-based pipeline |
| LangChain | Agent framework, tool abstraction | — |
| LangGraph | Multi-agent pipeline orchestration | Sequential execution |
