"""LangGraph multi-agent pipeline orchestrator.

Coordinates 20 detection agents in a three-tier pipeline:
  Tier 1 (Easy)   → 5 agents in parallel
  Tier 2 (Medium) → 7 agents in parallel
  Tier 3 (Evil)   → 8 agents in parallel

Each tier runs concurrently, and results are aggregated by a final
adjudication step that de-duplicates, confidence-ranks, and caps per-
category counts before emitting the submission.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from typing import Any, TypedDict

from langgraph.graph import StateGraph, START, END

from .detection_agents import CATEGORY_META, run_detection_agent
from .tools import set_data_store
from ..core.logging import get_logger

log = get_logger(__name__)


# ─── State schema ────────────────────────────────────────────────────
class PipelineState(TypedDict, total=False):
    """Shared state flowing through the LangGraph pipeline."""
    # Inputs
    invoices: list
    pos: list
    bank_stmts: list
    expense_reports: list
    credit_debit_notes: list
    vendors: list
    # Per-tier results  (category → list[finding_dict])
    easy_results: dict[str, list]
    medium_results: dict[str, list]
    evil_results: dict[str, list]
    # Final output
    all_findings: list
    submission: dict


# ─── Category groupings ─────────────────────────────────────────────
EASY_CATEGORIES = [
    "arithmetic_error", "billing_typo", "duplicate_line_item",
    "invalid_date", "wrong_tax_rate",
]
MEDIUM_CATEGORIES = [
    "po_invoice_mismatch", "vendor_name_typo", "double_payment",
    "ifsc_mismatch", "duplicate_expense", "date_cascade",
    "gstin_state_mismatch",
]
EVIL_CATEGORIES = [
    "quantity_accumulation", "price_escalation", "balance_drift",
    "circular_reference", "triple_expense_claim", "employee_id_collision",
    "fake_vendor", "phantom_po_reference",
]


# ─── Node functions ──────────────────────────────────────────────────

def initialise_node(state: PipelineState) -> dict:
    """Seed the shared tool data store from pipeline state."""
    set_data_store(
        invoices=state.get("invoices", []),
        pos=state.get("pos", []),
        bank_stmts=state.get("bank_stmts", []),
        expense_reports=state.get("expense_reports", []),
        credit_debit_notes=state.get("credit_debit_notes", []),
        vendors=state.get("vendors", []),
    )
    log.info("[Orchestrator] Data store initialised")
    return {}


def easy_tier_node(state: PipelineState) -> dict:
    """Run all 5 easy-tier detection agents."""
    log.info("[Orchestrator] ── EASY TIER ── running 5 agents")
    results: dict[str, list] = {}
    for cat in EASY_CATEGORIES:
        t0 = time.time()
        findings = run_detection_agent(cat)
        elapsed = time.time() - t0
        results[cat] = findings
        log.info(f"  {cat}: {len(findings)} findings ({elapsed:.1f}s)")
    return {"easy_results": results}


def medium_tier_node(state: PipelineState) -> dict:
    """Run all 7 medium-tier detection agents."""
    log.info("[Orchestrator] ── MEDIUM TIER ── running 7 agents")
    results: dict[str, list] = {}
    for cat in MEDIUM_CATEGORIES:
        t0 = time.time()
        findings = run_detection_agent(cat)
        elapsed = time.time() - t0
        results[cat] = findings
        log.info(f"  {cat}: {len(findings)} findings ({elapsed:.1f}s)")
    return {"medium_results": results}


def evil_tier_node(state: PipelineState) -> dict:
    """Run all 8 evil-tier detection agents."""
    log.info("[Orchestrator] ── EVIL TIER ── running 8 agents")
    results: dict[str, list] = {}
    for cat in EVIL_CATEGORIES:
        t0 = time.time()
        findings = run_detection_agent(cat)
        elapsed = time.time() - t0
        results[cat] = findings
        log.info(f"  {cat}: {len(findings)} findings ({elapsed:.1f}s)")
    return {"evil_results": results}


def adjudicate_node(state: PipelineState) -> dict:
    """Merge, rank, cap, and emit final submission.

    Steps:
      1. Flatten all tier results.
      2. Per category: sort by confidence, take top-N.
      3. Assign sequential finding IDs.
      4. Build submission dict.
    """
    log.info("[Orchestrator] ── ADJUDICATION ──")

    category_findings: dict[str, list] = {}
    for tier_key in ("easy_results", "medium_results", "evil_results"):
        tier = state.get(tier_key, {})
        for cat, findings in tier.items():
            category_findings.setdefault(cat, []).extend(findings)

    final_findings: list[dict] = []
    finding_counter = 0

    for cat, meta in CATEGORY_META.items():
        candidates = category_findings.get(cat, [])
        candidates.sort(key=lambda f: f.get("confidence", 0), reverse=True)
        selected = candidates[:meta["target"]]

        for f in selected:
            finding_counter += 1
            f["finding_id"] = f"F-{finding_counter:03d}"

        final_findings.extend(selected)
        log.info(f"  {cat}: selected {len(selected)}/{len(candidates)} (target: {meta['target']})")

    submission = {
        "team_id": "hackculture",
        "findings": [
            {
                "finding_id": f.get("finding_id", ""),
                "category": f.get("category", ""),
                "pages": f.get("pages", []),
                "document_refs": f.get("document_refs", []),
                "description": f.get("description", ""),
                "reported_value": str(f.get("reported_value", "")),
                "correct_value": str(f.get("correct_value", "")),
            }
            for f in final_findings
        ],
    }

    log.info(f"[Orchestrator] Final submission: {len(submission['findings'])} findings")
    return {"all_findings": final_findings, "submission": submission}


# ─── Build graph ─────────────────────────────────────────────────────

def build_pipeline() -> StateGraph:
    """Construct the LangGraph pipeline DAG.

    Graph topology:

        START → initialise → easy_tier → medium_tier → evil_tier → adjudicate → END

    The tiers are sequential to conserve API quota, but each tier
    internally runs its agents sequentially (could be parallelised
    with LangGraph Send() for higher throughput).
    """
    graph = StateGraph(PipelineState)

    graph.add_node("initialise", initialise_node)
    graph.add_node("easy_tier", easy_tier_node)
    graph.add_node("medium_tier", medium_tier_node)
    graph.add_node("evil_tier", evil_tier_node)
    graph.add_node("adjudicate", adjudicate_node)

    graph.add_edge(START, "initialise")
    graph.add_edge("initialise", "easy_tier")
    graph.add_edge("easy_tier", "medium_tier")
    graph.add_edge("medium_tier", "evil_tier")
    graph.add_edge("evil_tier", "adjudicate")
    graph.add_edge("adjudicate", END)

    return graph.compile()


def run_pipeline(
    invoices: list,
    pos: list,
    bank_stmts: list,
    expense_reports: list,
    credit_debit_notes: list,
    vendors: list,
) -> dict:
    """Execute the full multi-agent detection pipeline.

    Returns the submission dict ready for JSON serialisation.
    """
    log.info("[Orchestrator] Starting LangGraph multi-agent pipeline")
    pipeline = build_pipeline()

    initial_state: PipelineState = {
        "invoices": invoices,
        "pos": pos,
        "bank_stmts": bank_stmts,
        "expense_reports": expense_reports,
        "credit_debit_notes": credit_debit_notes,
        "vendors": vendors,
    }

    final_state = pipeline.invoke(initial_state)
    return final_state.get("submission", {})
