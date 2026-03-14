"""Per-category detection agents.

Each agent wraps a LangChain ReAct agent backed by Claude (Bedrock) and
equipped with the corresponding detection tool.  The agent receives a
system prompt that describes the anomaly category, expected needle count,
and scoring criteria, then invokes the tool, reviews the candidates, and
returns a validated list.
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from .llm import get_fast_llm
from .tools import (
    EASY_TOOLS, MEDIUM_TOOLS, EVIL_TOOLS,
    detect_arithmetic_errors,
    detect_billing_typos,
    detect_duplicate_line_items,
    detect_invalid_dates,
    detect_wrong_tax_rates,
    detect_po_invoice_mismatches,
    detect_vendor_name_typos,
    detect_double_payments,
    detect_ifsc_mismatches,
    detect_duplicate_expenses,
    detect_date_cascades,
    detect_gstin_state_mismatches,
    detect_quantity_accumulations,
    detect_price_escalations,
    detect_balance_drifts,
    detect_circular_references,
    detect_triple_expense_claims,
    detect_employee_id_collisions,
    detect_fake_vendors,
    detect_phantom_po_references,
)
from ..core.logging import get_logger

log = get_logger(__name__)

# ─── Category metadata ──────────────────────────────────────────────
CATEGORY_META = {
    "arithmetic_error": {
        "target": 12, "difficulty": "easy", "weight": 1,
        "description": "Line-item arithmetic errors: qty×rate≠amount, subtotal≠Σitems, grand-total mismatches.",
        "tool": detect_arithmetic_errors,
    },
    "billing_typo": {
        "target": 4, "difficulty": "easy", "weight": 1,
        "description": "Typographical errors in billing fields: transposed digits, misspelled vendor names.",
        "tool": detect_billing_typos,
    },
    "duplicate_line_item": {
        "target": 4, "difficulty": "easy", "weight": 1,
        "description": "Duplicate line items within a single invoice — same description, amount, or HSN.",
        "tool": detect_duplicate_line_items,
    },
    "invalid_date": {
        "target": 10, "difficulty": "easy", "weight": 1,
        "description": "Impossible calendar dates: Feb 30, month>12, day>31.",
        "tool": detect_invalid_dates,
    },
    "wrong_tax_rate": {
        "target": 10, "difficulty": "easy", "weight": 1,
        "description": "Tax rate mismatches against HSN/SAC-mandated GST rates.",
        "tool": detect_wrong_tax_rates,
    },
    "po_invoice_mismatch": {
        "target": 15, "difficulty": "medium", "weight": 3,
        "description": "Discrepancies between PO and invoice line items: qty, rate, or description based on HSN-code matching.",
        "tool": detect_po_invoice_mismatches,
    },
    "vendor_name_typo": {
        "target": 10, "difficulty": "medium", "weight": 3,
        "description": "Invoice vendor names that are slight misspellings of vendor master entries.",
        "tool": detect_vendor_name_typos,
    },
    "double_payment": {
        "target": 10, "difficulty": "medium", "weight": 3,
        "description": "Duplicate bank-statement payments to the same beneficiary for the same amount.",
        "tool": detect_double_payments,
    },
    "ifsc_mismatch": {
        "target": 5, "difficulty": "medium", "weight": 3,
        "description": "IFSC code outliers per vendor — invoices whose bank code differs from the vendor's majority IFSC.",
        "tool": detect_ifsc_mismatches,
    },
    "duplicate_expense": {
        "target": 10, "difficulty": "medium", "weight": 3,
        "description": "Duplicate entries across expense reports.",
        "tool": detect_duplicate_expenses,
    },
    "date_cascade": {
        "target": 5, "difficulty": "medium", "weight": 3,
        "description": "Invoice dates that precede their purchase order dates — timeline anomalies.",
        "tool": detect_date_cascades,
    },
    "gstin_state_mismatch": {
        "target": 5, "difficulty": "medium", "weight": 3,
        "description": "GSTIN first-two-digit state codes inconsistent with vendor master state.",
        "tool": detect_gstin_state_mismatches,
    },
    "quantity_accumulation": {
        "target": 35, "difficulty": "evil", "weight": 7,
        "description": "Cumulative invoiced quantities exceeding PO-authorised quantities by >20%.",
        "tool": detect_quantity_accumulations,
    },
    "price_escalation": {
        "target": 10, "difficulty": "evil", "weight": 7,
        "description": "Invoice unit rates that exceed PO-agreed rates by >3%.",
        "tool": detect_price_escalations,
    },
    "balance_drift": {
        "target": 15, "difficulty": "evil", "weight": 7,
        "description": "Bank-statement balance continuity errors where closing≠next-opening.",
        "tool": detect_balance_drifts,
    },
    "circular_reference": {
        "target": 8, "difficulty": "evil", "weight": 7,
        "description": "Circular chains among credit/debit notes (A→B→C→A).",
        "tool": detect_circular_references,
    },
    "triple_expense_claim": {
        "target": 10, "difficulty": "evil", "weight": 7,
        "description": "Expenses claimed three or more times across reports.",
        "tool": detect_triple_expense_claims,
    },
    "employee_id_collision": {
        "target": 7, "difficulty": "evil", "weight": 7,
        "description": "Multiple employees sharing the same ID across expense reports.",
        "tool": detect_employee_id_collisions,
    },
    "fake_vendor": {
        "target": 10, "difficulty": "evil", "weight": 7,
        "description": "Invoice vendors with no close match in the vendor master.",
        "tool": detect_fake_vendors,
    },
    "phantom_po_reference": {
        "target": 5, "difficulty": "evil", "weight": 7,
        "description": "Invoices referencing PO numbers that do not exist in the PO dataset.",
        "tool": detect_phantom_po_references,
    },
}


def _agent_system_prompt(category: str, meta: dict) -> str:
    """Build the system prompt for a detection agent."""
    return f"""You are a specialised financial-anomaly detection agent.

CATEGORY: {category}
DIFFICULTY: {meta['difficulty'].upper()} (point weight: {meta['weight']}× per needle)
TARGET COUNT: {meta['target']} needles expected in the dataset
DESCRIPTION: {meta['description']}

TASK:
1. Call your detection tool to scan all relevant documents.
2. Review the returned candidate findings.
3. Rank candidates by confidence (highest first).
4. Select exactly the top {meta['target']} candidates.
5. Return ONLY a JSON array of the selected findings — no commentary.

RULES:
- Never fabricate findings. Only return what the tool reports.
- If fewer than {meta['target']} candidates are found, return all of them.
- Preserve all fields from the tool output exactly as returned.
- Return raw JSON only, no markdown fences.
"""


def build_detection_agent(category: str):
    """Build a LangGraph ReAct agent for a single detection category.

    Returns (agent_executor, system_prompt, category_meta).
    """
    meta = CATEGORY_META[category]
    llm = get_fast_llm()
    system_prompt = _agent_system_prompt(category, meta)

    agent = create_react_agent(
        model=llm,
        tools=[meta["tool"]],
        prompt=system_prompt,
    )
    return agent, system_prompt, meta


def run_detection_agent(category: str) -> list[dict]:
    """Run a single detection agent end-to-end and return its findings.

    This is the primary entry-point consumed by the orchestrator.
    """
    log.info(f"[Agent:{category}] Starting detection agent")
    meta = CATEGORY_META[category]

    agent, sys_prompt, _ = build_detection_agent(category)

    user_msg = (
        f"Run the {category} detection tool now. "
        f"Analyse the candidates, rank by confidence, and return the top {meta['target']} as a JSON array."
    )

    result = agent.invoke(
        {"messages": [HumanMessage(content=user_msg)]},
    )

    # Extract the final AI message content
    ai_messages = [m for m in result["messages"] if hasattr(m, "type") and m.type == "ai"]
    if not ai_messages:
        log.warning(f"[Agent:{category}] No AI response")
        return []

    final_text = ai_messages[-1].content
    if not final_text:
        # Agent may have only used tool calls; fall back to tool output
        tool_messages = [m for m in result["messages"] if hasattr(m, "type") and m.type == "tool"]
        if tool_messages:
            final_text = tool_messages[-1].content

    # Parse JSON from agent output
    try:
        findings = json.loads(final_text)
        if isinstance(findings, list):
            log.info(f"[Agent:{category}] Returned {len(findings)} findings")
            return findings
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: try extracting JSON array from text
    import re
    match = re.search(r'\[.*\]', final_text or "", re.DOTALL)
    if match:
        try:
            findings = json.loads(match.group(0))
            log.info(f"[Agent:{category}] Parsed {len(findings)} findings from text")
            return findings
        except json.JSONDecodeError:
            pass

    log.warning(f"[Agent:{category}] Could not parse findings from agent output")
    return []
