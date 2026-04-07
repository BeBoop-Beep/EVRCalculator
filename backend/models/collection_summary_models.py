"""Domain models for collection summary calculations.

This module intentionally defines only the summary output contract.
Calculation and data-access logic are implemented in separate backend layers.
"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CollectionSummary:
    """Aggregate collection metrics returned by the summary calculator."""

    portfolio_value: float
    cards_count: int
    sealed_count: int
    graded_count: int

    def to_dict(self) -> dict:
        """Return a JSON-serializable dictionary for controller/API responses."""
        return asdict(self)
