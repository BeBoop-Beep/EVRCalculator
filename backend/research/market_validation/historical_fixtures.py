"""Compatibility check against known prior card/set-level market-validation findings.

These figures are recorded from prior research (as supplied by the task, not
recomputed here) and used only to CLASSIFY whether a new harness run's results are
consistent with, or diverge from, the historical study -- never to force a new
result to match. Cohorts and data authorities may have legitimately changed since
these were produced; classify_discrepancy() reports the gap, it does not paper
over it.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Prior card-level findings (raw Spearman vs. price), as supplied.
PRIOR_CARD_LEVEL_FINDINGS = {
    "pure_pokemon_demand_raw_spearman": 0.370,
    "treatment_raw_spearman": 0.582,
    "old_merged_card_appeal_raw_spearman": 0.569,
}

# Prior set-level finding: qualitative, not a single number -- scarcity dominated
# the old demand x scarcity interaction. Recorded as a flag for classify_set_level
# to compare against.
PRIOR_SET_LEVEL_FINDING = "scarcity_dominated_demand_x_scarcity_interaction"

# Discrepancy bands: how far a new estimate can drift from the historical point
# estimate before being classified as a material discrepancy rather than
# reproduction-noise. These are informational bands, not statistical significance
# tests (see raw_correlations.bootstrap CI for that).
CONSISTENT_BAND = 0.05
MODERATE_DRIFT_BAND = 0.15


def classify_discrepancy(new_value: Optional[float], historical_key: str) -> Dict[str, Any]:
    """Compares a freshly-computed raw Spearman against a recorded historical value
    and classifies the gap. Never raises, never "corrects" either number."""
    historical_value = PRIOR_CARD_LEVEL_FINDINGS.get(historical_key)
    if historical_value is None:
        return {
            "historicalKey": historical_key,
            "historicalValue": None,
            "newValue": new_value,
            "classification": "NO_HISTORICAL_REFERENCE",
        }
    if new_value is None:
        return {
            "historicalKey": historical_key,
            "historicalValue": historical_value,
            "newValue": None,
            "classification": "NEW_VALUE_UNAVAILABLE",
        }
    gap = abs(new_value - historical_value)
    if gap <= CONSISTENT_BAND:
        classification = "CONSISTENT_WITH_PRIOR_STUDY"
    elif gap <= MODERATE_DRIFT_BAND:
        classification = "MODERATE_DRIFT_REVIEW_COHORT"
    else:
        classification = "MATERIAL_DISCREPANCY_INVESTIGATE"
    return {
        "historicalKey": historical_key,
        "historicalValue": historical_value,
        "newValue": new_value,
        "absoluteGap": gap,
        "classification": classification,
    }


def classify_set_level(new_interaction_note: Optional[str]) -> Dict[str, Any]:
    """Qualitative comparison for the set-level scarcity-dominance finding -- the
    caller supplies a short description of what the new study found (e.g.
    'scarcity dominated' or 'demand dominated' or 'no dominant term'), and this
    function just records whether it matches the prior qualitative finding."""
    matches = new_interaction_note == PRIOR_SET_LEVEL_FINDING
    return {
        "priorFinding": PRIOR_SET_LEVEL_FINDING,
        "newFinding": new_interaction_note,
        "matchesPrior": matches,
    }
