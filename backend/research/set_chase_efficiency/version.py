"""Immutable identity for a Set Chase Efficiency research run."""

from __future__ import annotations

#: Bump when the research pipeline's shape or cohort policy changes.
SET_CHASE_EFFICIENCY_RESEARCH_VERSION = "set-chase-efficiency-stage1-v1"

#: Bump when the CE mathematics itself changes.
SET_CHASE_EFFICIENCY_CALCULATION_VERSION = (
    "basket-conditional-value-times-any-hit-hazard-over-pack-cost-v1"
)

#: The observer used to obtain exact-under-model basket probabilities.
SET_CHASE_EFFICIENCY_PROBABILITY_SOURCE = "monte_carlo_v2_pack_decomposition"
