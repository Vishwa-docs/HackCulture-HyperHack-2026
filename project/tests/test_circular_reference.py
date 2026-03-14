"""Tests for circular reference detection."""
import networkx as nx
from src.storage.graph_store import GraphStore


def test_cycle_detection():
    """Test that circular reference chains are detected."""
    graph = GraphStore()
    graph.add_credit_note("CN-001", source_pages=[50])
    graph.add_debit_note("DN-001", source_pages=[60])
    graph.add_credit_note("CN-002", source_pages=[70])

    graph.link("CN-001", "DN-001", "references")
    graph.link("DN-001", "CN-002", "references")
    graph.link("CN-002", "CN-001", "references")  # Creates cycle

    cycles = graph.find_note_cycles()
    assert len(cycles) > 0
    # All nodes in cycle should be notes
    for cycle in cycles:
        for node in cycle:
            assert node.startswith("CN-") or node.startswith("DN-")


def test_no_cycle_with_invoice_anchor():
    """Test that chains anchored to real invoices are not flagged."""
    graph = GraphStore()
    graph.add_invoice("INV-001", source_pages=[10])
    graph.add_credit_note("CN-001", source_pages=[50])
    graph.add_debit_note("DN-001", source_pages=[60])

    graph.link("CN-001", "INV-001", "references")
    graph.link("DN-001", "CN-001", "references")
    # No cycle here, just a chain ending at an invoice

    cycles = graph.find_note_cycles()
    assert len(cycles) == 0
