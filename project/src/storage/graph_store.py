"""Graph-based storage for document linkage and cycle detection."""
import json
from typing import Optional
import networkx as nx

from ..core.logging import get_logger
from ..core import paths

log = get_logger(__name__)


class GraphStore:
    """NetworkX-based graph for document relationships."""

    def __init__(self):
        self.G = nx.DiGraph()

    def add_vendor(self, vendor_id: str, **attrs):
        self.G.add_node(vendor_id, node_type="vendor", **attrs)

    def add_invoice(self, invoice_number: str, **attrs):
        self.G.add_node(invoice_number, node_type="invoice", **attrs)

    def add_po(self, po_number: str, **attrs):
        self.G.add_node(po_number, node_type="po", **attrs)

    def add_bank_txn(self, txn_ref: str, **attrs):
        self.G.add_node(txn_ref, node_type="bank_txn", **attrs)

    def add_expense_report(self, report_id: str, **attrs):
        self.G.add_node(report_id, node_type="expense_report", **attrs)

    def add_credit_note(self, note_number: str, **attrs):
        self.G.add_node(note_number, node_type="credit_note", **attrs)

    def add_debit_note(self, note_number: str, **attrs):
        self.G.add_node(note_number, node_type="debit_note", **attrs)

    def link(self, source: str, target: str, rel_type: str = "", **attrs):
        self.G.add_edge(source, target, rel_type=rel_type, **attrs)

    def find_cycles(self) -> list[list[str]]:
        """Find all cycles in the graph."""
        try:
            return list(nx.simple_cycles(self.G))
        except Exception:
            return []

    def find_note_cycles(self) -> list[list[str]]:
        """Find cycles involving only credit/debit notes (no real invoice anchor)."""
        cycles = self.find_cycles()
        note_cycles = []
        for cycle in cycles:
            node_types = [self.G.nodes[n].get("node_type", "") for n in cycle if n in self.G.nodes]
            # Cycle is suspicious if it doesn't contain a real invoice
            has_invoice = any(t == "invoice" for t in node_types)
            all_notes = all(t in ("credit_note", "debit_note") for t in node_types)
            if not has_invoice or all_notes:
                note_cycles.append(cycle)
        return note_cycles

    def get_linked_invoices(self, po_number: str) -> list[str]:
        """Get all invoices linked to a PO."""
        linked = []
        if po_number not in self.G:
            return linked
        for neighbor in self.G.predecessors(po_number):
            if self.G.nodes.get(neighbor, {}).get("node_type") == "invoice":
                linked.append(neighbor)
        for neighbor in self.G.successors(po_number):
            if self.G.nodes.get(neighbor, {}).get("node_type") == "invoice":
                linked.append(neighbor)
        return linked

    def get_vendor_docs(self, vendor_id: str) -> list[str]:
        """Get all documents linked to a vendor."""
        if vendor_id not in self.G:
            return []
        return list(self.G.successors(vendor_id)) + list(self.G.predecessors(vendor_id))

    def save(self, path: Optional[str] = None):
        path = path or str(paths.INDEXES / "doc_graph.json")
        data = nx.node_link_data(self.G)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def load(self, path: Optional[str] = None):
        path = path or str(paths.INDEXES / "doc_graph.json")
        with open(path) as f:
            data = json.load(f)
        self.G = nx.node_link_graph(data, directed=True)
