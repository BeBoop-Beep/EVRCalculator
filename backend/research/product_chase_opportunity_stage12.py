"""Stage XII - the Product Chase Opportunity input contract.

RESEARCH ONLY. No sealed-product PRICE is read anywhere: Opportunity is an access
metric, and product economics belong to a later Chase Efficiency layer.

THE CONTRACT UNDER TEST
-----------------------
Set level, fixed at one market snapshot (Stage XI):

    s_i  = V_i / sum_j V_j
    HHI  = sum_i s_i^2
    HC_i = s_i^2 / HHI            with sum_i HC_i = 1

Product level:

    A_ip = P(N_ip >= 1)           one whole unit of product p
    O_p  = sum_i HC_i * A_ip

WHY CROSS-CARD INDEPENDENCE IS NOT REQUIRED
-------------------------------------------
O_p is the expectation of the random variable sum_i HC_i * 1{N_ip >= 1}. By
linearity of expectation,

    E[O_p] = sum_i HC_i * P(N_ip >= 1)

regardless of whether the hit events for cards i and j are independent, or even
mutually exclusive. The aggregation is therefore assumption-free. Only the method
used to obtain each MARGINAL P(N_ip >= 1) needs to be valid. This matters because
hits within one pack are genuinely dependent - a slot holds one card - and a
formulation needing joint independence would be unusable.

WHAT THE IID ASSUMPTION IS ACTUALLY USED FOR
--------------------------------------------
Only to lift a per-PACK marginal to a per-PRODUCT marginal:

    A_ip = 1 - (1 - p_i)^n

That is the production simulator's own `pack_independence_assumption` restated at
product scale, exactly as Stage V-C's `aggregate_to_product` does. It is inherited,
not independently validated - there is no non-IID product simulation in this system
to check it against.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

import numpy as np

#: Fraction of HC mass that must carry a valid pull probability before an
#: Opportunity score may be formed. Reported, not yet ratified - see Stage XII
#: Phase 17. It is deliberately high because the metric is dominated by a few
#: cards, so a small unmapped MASS can be a large unmapped MEANING.
DEFAULT_MIN_MAPPED_HC_MASS = 0.99


def chase_significance(values: Sequence[float]) -> np.ndarray:
    """HC_i = s_i^2 / HHI. Equivalently V_i^2 / sum_j V_j^2."""
    v = np.asarray(values, dtype=float)
    sq = v ** 2
    return sq / sq.sum()


def at_least_once(p_pack: Sequence[float], n_packs: int) -> np.ndarray:
    """A_ip = 1 - (1 - p_i)^n. The only place the IID lift is used."""
    p = np.clip(np.asarray(p_pack, dtype=float), 0.0, 1.0)
    if n_packs <= 0:
        return np.zeros_like(p)
    return 1.0 - (1.0 - p) ** int(n_packs)


def opportunity(hc: Sequence[float], a: Sequence[float]) -> float:
    """Candidate B - HC-weighted at-least-once coverage. Bounded [0, 1]."""
    return float(np.dot(np.asarray(hc, dtype=float), np.asarray(a, dtype=float)))


def expected_significance(hc: Sequence[float], p_pack: Sequence[float],
                          n_packs: int) -> float:
    """Candidate A - HC-weighted EXPECTED COPIES. Unbounded above."""
    return float(np.dot(np.asarray(hc, dtype=float),
                        np.asarray(p_pack, dtype=float) * float(n_packs)))


def per_pack_opportunity(hc: Sequence[float], p_pack: Sequence[float]) -> float:
    """O_pack = sum HC_i p_i - the set's underlying access rate, product-free."""
    return float(np.dot(np.asarray(hc, dtype=float), np.asarray(p_pack, dtype=float)))


def mapped_hc_mass(hc: Sequence[float], has_probability: Sequence[bool]) -> float:
    """Phase 17 diagnostic: share of Chase Significance that is joinable."""
    hc = np.asarray(hc, dtype=float)
    return float(hc[np.asarray(has_probability, dtype=bool)].sum())


def evaluate_product(*, values: Sequence[float], p_pack: Sequence[float],
                     n_random_packs: int,
                     guaranteed_index: Optional[Sequence[int]] = None,
                     min_mapped_mass: float = DEFAULT_MIN_MAPPED_HC_MASS,
                     has_probability: Optional[Sequence[bool]] = None
                     ) -> Dict[str, object]:
    """Full Opportunity payload for one product against one set snapshot.

    ``guaranteed_index`` names cards the product guarantees AND that legitimately
    belong to the set's random-pack Chase Significance universe. Their A is forced
    to 1. A promotional card that is not drawable from packs must never be added
    to the universe merely because a product includes it - it would dilute every
    other card's HC and inflate that product.
    """
    hc = chase_significance(values)
    mask = (np.ones(hc.size, dtype=bool) if has_probability is None
            else np.asarray(has_probability, dtype=bool))
    mass = mapped_hc_mass(hc, mask)
    if mass < min_mapped_mass:
        return {"opportunity": None, "status": "unavailable_insufficient_hc_coverage",
                "mappedHcMass": mass, "minMappedHcMass": min_mapped_mass,
                "statusReason": (
                    "%.4f of Chase Significance mass has no pull probability; the "
                    "metric is dominated by a few cards, so unmapped mass is not "
                    "renormalised away." % (1.0 - mass)),
                "rankable": False}

    a = at_least_once(p_pack, n_random_packs)
    if guaranteed_index:
        a = a.copy()
        for idx in guaranteed_index:
            a[int(idx)] = 1.0

    o = opportunity(hc, a)
    order = np.argsort(-hc)
    return {
        "opportunity": o,
        "expectedSignificance": expected_significance(hc, p_pack, n_random_packs),
        "perPackOpportunity": per_pack_opportunity(hc, p_pack),
        "randomPackCount": int(n_random_packs),
        "mappedHcMass": mass,
        "hcTop1Share": float(hc[order[0]]),
        "opportunityFromTop1": float(hc[order[0]] * a[order[0]] / o) if o > 0 else 0.0,
        "opportunityFromTop3": float((hc[order[:3]] * a[order[:3]]).sum() / o) if o > 0 else 0.0,
        "status": "ready",
        "rankable": True,
    }
