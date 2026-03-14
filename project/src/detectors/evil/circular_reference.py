"""Circular reference detector: credit/debit notes forming loops."""
from ..base import BaseDetector
from ...core.enums import Category
from ...core.models import FindingCandidate
from ...core.logging import get_logger

log = get_logger(__name__)


class CircularReferenceDetector(BaseDetector):
    category = Category.CIRCULAR_REFERENCE
    name = "circular_reference"

    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        findings = []
        if not graph:
            log.warning("No graph store available for circular reference detection")
            return findings

        cycles = graph.find_note_cycles()
        for cycle in cycles:
            # Get page info for involved nodes
            pages = []
            refs = []
            for node in cycle:
                node_data = graph.G.nodes.get(node, {})
                node_pages = node_data.get("source_pages", [])
                if isinstance(node_pages, str):
                    import json
                    node_pages = json.loads(node_pages)
                pages.extend(node_pages)
                refs.append(node)

            chain_str = " -> ".join(cycle) + " -> " + cycle[0]
            findings.append(self.make_finding(
                pages=sorted(set(pages)),
                document_refs=refs,
                description=f"Circular reference chain detected: {chain_str}. These credit/debit notes reference each other with no real invoice anchor.",
                reported_value=chain_str,
                correct_value="No circular chain should exist",
                confidence=0.72,
            ))

        log.info(f"CircularReference: found {len(findings)} candidates")
        return findings
