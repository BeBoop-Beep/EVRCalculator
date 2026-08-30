"""Stage-I research foundation for Set-Level Chase Efficiency.

RESEARCH ONLY. Nothing in this package is imported by production scoring,
ranking, publication or API code, and nothing here writes to a production
table. See ``docs/research/SET_CHASE_EFFICIENCY_STAGE1.md``.
"""

from .version import (
    SET_CHASE_EFFICIENCY_RESEARCH_VERSION,
    SET_CHASE_EFFICIENCY_CALCULATION_VERSION,
)

__all__ = [
    "SET_CHASE_EFFICIENCY_RESEARCH_VERSION",
    "SET_CHASE_EFFICIENCY_CALCULATION_VERSION",
]
