"""Stage XIV - Chase Accessibility publication contract.

RESEARCH MODULE, NOT YET A PRODUCTION PUBLICATION PATH. Nothing here is read by a
canonical reader, and no sealed-product price is read anywhere - Accessibility is a
SET-level access metric and product economics belong to the future Chase Efficiency
layer.

THE METRIC
----------
    HC_i     = V_i^2 / sum_j V_j^2          (Chase Significance, Stage XI)
    O_pack   = sum_i HC_i * p_i             (Chase Accessibility)

Equivalently, and computed both ways as a parity check:

    O_pack   = sum_i V_i^2 p_i / sum_j V_j^2

Interpretation: the probability-weighted share of a set's collectible chase
significance that is reachable in one random pack.

WHAT IT IS NOT
--------------
It is NOT "the probability of pulling a chase card". There is no chase roster -
Stages IX, X and XI all failed to produce a defensible discrete Core/Extended tier,
and the architecture deliberately no longer needs one. Every card carries continuous
significance, so a binary "hit a chase" event does not exist to have a probability.

PROBABILITY AUTHORITY, AND A PERMANENT TRAP
-------------------------------------------
    p_i = simulation_card_variant_pull_rates.modeled_probability

`effective_pull_rate` is 1-in-N ODDS (observed range 20-1430), NOT a probability.
Reading it as one inverts the weighting and silently produces a plausible but wrong
answer - this happened in Stage XI and was caught only in Stage XII. The relationship
is p_i = 1 / effective_pull_rate_i, verified across all 7,615 cohort rows.

`pull_count / simulation_count` is ALSO not a substitute: it is expected COPIES, and
it differs from P(N>=1) on 2,398 of those 7,615 rows where a pack can hold more than
one copy of the same variant.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

import numpy as np

#: Research identity. Not a production version - nothing canonical reads this.
CHASE_ACCESSIBILITY_RESEARCH_VERSION = (
    "chase_accessibility_stage14_hc_weighted_per_pack_probability"
)

#: Minimum share of Chase Significance that must carry BOTH a market value and a
#: modeled probability. Ratified in Stage XIV against observed coverage: the worst
#: real unmapped mass across 22 sets is 0.0025 (Scarlet and Violet 151, one $24.59
#: card outside the pull model), so 0.99 leaves 4x headroom over the worst observed
#: case while still refusing a set that has genuinely lost a significant card.
MIN_MAPPED_HC_MASS = 0.99

STATUS_READY = "ready"
STATUS_NO_PULL_MODEL = "unavailable_pull_model"
STATUS_LOW_COVERAGE = "unavailable_insufficient_hc_coverage"


def chase_significance(values: Sequence[float]) -> np.ndarray:
    """HC_i = V_i^2 / sum_j V_j^2. Sums to exactly 1; scale-invariant."""
    v = np.asarray(values, dtype=float)
    sq = v * v
    total = sq.sum()
    if total <= 0:
        return np.zeros_like(sq)
    return sq / total


def accessibility_via_hc(hc: Sequence[float], p: Sequence[float]) -> float:
    """O_pack as the HC-weighted mean of probabilities."""
    return float(np.dot(np.asarray(hc, float), np.asarray(p, float)))


def accessibility_direct(values: Sequence[float], p: Sequence[float]) -> float:
    """O_pack in the single-expression form. Parity-checked against the above."""
    v = np.asarray(values, dtype=float)
    sq = v * v
    total = sq.sum()
    if total <= 0:
        return 0.0
    return float((sq * np.asarray(p, float)).sum() / total)


def mapped_hc_mass(values: Sequence[float], usable: Sequence[bool]) -> float:
    """Share of Chase Significance carrying both a value and a probability.

    Computed over the FULL drawable universe including unusable cards, so that a
    missing high-significance card lowers the mass instead of vanishing. Dividing
    only by the usable cards' squares would renormalise the gap away and make a set
    look more accessible precisely because an important card went missing.
    """
    v = np.asarray(values, dtype=float)
    sq = v * v
    total = sq.sum()
    if total <= 0:
        return 0.0
    return float(sq[np.asarray(usable, dtype=bool)].sum() / total)


def compute_chase_accessibility(
    *,
    values: Sequence[float],
    probabilities: Sequence[float],
    usable: Optional[Sequence[bool]] = None,
    has_pull_model: bool = True,
    min_mapped_mass: float = MIN_MAPPED_HC_MASS,
) -> Dict[str, object]:
    """Chase Accessibility for one set at one coherent snapshot.

    ``values`` and ``probabilities`` must be the SAME drawable card-variant rows -
    no canonical-card fan-out, no cross-table join, no product input.
    """
    if not has_pull_model:
        return {
            "accessibility": None, "status": STATUS_NO_PULL_MODEL, "rankable": False,
            "statusReason": (
                "this set has no authoritative modeled pull probabilities, so "
                "Accessibility cannot be computed. A rate is never fabricated and the "
                "metric is never extended to eras the pull model does not cover."),
            "version": CHASE_ACCESSIBILITY_RESEARCH_VERSION,
        }

    v = np.asarray(values, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    mask = (np.ones(v.size, dtype=bool) if usable is None
            else np.asarray(usable, dtype=bool))
    mass = mapped_hc_mass(v, mask)
    if mass < min_mapped_mass:
        return {
            "accessibility": None, "status": STATUS_LOW_COVERAGE, "rankable": False,
            "mappedHcMass": mass, "minMappedHcMass": min_mapped_mass,
            "statusReason": (
                "%.4f of Chase Significance has no value or no probability. Unmapped "
                "mass is never renormalised away." % (1.0 - mass)),
            "version": CHASE_ACCESSIBILITY_RESEARCH_VERSION,
        }

    vv, pp = v[mask], p[mask]
    hc = chase_significance(vv)
    o_hc = accessibility_via_hc(hc, pp)
    o_direct = accessibility_direct(vv, pp)
    order = np.argsort(-hc)
    return {
        "accessibility": o_hc,
        "accessibilityPercent": o_hc * 100.0,
        "parityDelta": abs(o_hc - o_direct),
        "mappedHcMass": mass,
        "cardCount": int(vv.size),
        "hcTop1": float(hc[order[0]]),
        "accessibilityShareTop1": float(hc[order[0]] * pp[order[0]] / o_hc) if o_hc > 0 else 0.0,
        "accessibilityShareTop3": float((hc[order[:3]] * pp[order[:3]]).sum() / o_hc) if o_hc > 0 else 0.0,
        "chaseDepthNHC": float(1.0 / (hc * hc).sum()),
        "status": STATUS_READY,
        "rankable": True,
        "version": CHASE_ACCESSIBILITY_RESEARCH_VERSION,
    }
