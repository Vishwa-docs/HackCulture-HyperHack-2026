"""Base detector pattern."""
from abc import ABC, abstractmethod
from ..core.models import FindingCandidate
from ..core.enums import Category


class BaseDetector(ABC):
    """Abstract base class for all detectors."""

    category: Category = None
    name: str = ""

    @abstractmethod
    def detect(self, store, graph=None, vendors=None, **kwargs) -> list[FindingCandidate]:
        """Run detection and return candidate findings."""
        ...

    def make_finding(self, **kwargs) -> FindingCandidate:
        return FindingCandidate(
            category=self.category.value if self.category else "",
            detector_name=self.name,
            **kwargs,
        )
