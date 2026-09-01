"""Phases 3 and 4: the weight grid and what a coefficient literally means.

RESEARCH ONLY.

THE SEPARATION THIS MODULE ENFORCES
-----------------------------------
The brief's central instruction is not to equate a nominal coefficient with
"percentage importance". :func:`score_point_semantics` therefore reports only
the first of those - the literal arithmetic of the blend, before any
distributional effect - and deliberately says nothing about influence. Influence
is measured in ``attribution``, ``pairs`` and ``decisions``, from data.

FUNDING RULE
------------
In the primary grid, Collector Appeal is held at its production 0.10 and Chase
is funded ENTIRELY from Financial. :func:`chase_grid` will not produce any other
shape, and the test suite pins that, so a later analysis cannot quietly move
Collector and attribute the resulting movement to Chase.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

#: Phase 3's pre-registered nominal Chase weights. Discrete on purpose: the
#: brief forbids continuous optimization, and a fine sweep searched for a
#: favourite number is continuous optimization with extra steps.
CHASE_WEIGHTS: Tuple[float, ...] = (
    0.00, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.075, 0.10,
)

PILLARS: Tuple[str, ...] = ("financial_rip", "collector_appeal", "chase")


def chase_grid(chase_weights: Sequence[float] = CHASE_WEIGHTS, *,
               base: Optional[Mapping[str, float]] = None) -> List[Dict[str, Any]]:
    """Candidate weight sets: Collector fixed, Chase funded from Financial only."""
    if base is None:
        from backend.research.chase_pillar_stage6.control import canonical_versions
        base = canonical_versions()["overallWeights"]
    financial = float(base["financial_rip"])
    collector = float(base["collector_appeal"])

    out: List[Dict[str, Any]] = []
    for share in chase_weights:
        share = float(share)
        if share > financial:
            continue
        out.append({
            "chaseWeight": share,
            "weights": {
                "financial_rip": financial - share,
                "collector_appeal": collector,
                "chase": share,
            },
            "label": "%.4g/%.4g/%.4g" % ((financial - share) * 100, collector * 100,
                                         share * 100),
        })
    return out


def blend(*, financial: Any, collector: Any, chase: Any,
          weights: Mapping[str, float]) -> Optional[float]:
    """The candidate Overall score. Same arithmetic shape as production."""
    total = 0.0
    for name, value in (("financial_rip", financial), ("collector_appeal", collector),
                        ("chase", chase)):
        weight = float(weights.get(name, 0.0))
        if weight == 0.0:
            continue
        if value is None:
            return None
        total += weight * float(value)
    return total


def score_point_semantics(weights: Mapping[str, float], *,
                          step: float = 10.0) -> Dict[str, Any]:
    """Phase 4: what ``+step`` points on each pillar is worth in Overall points.

    Pure arithmetic. It is the honest answer to "what does a 5% Chase weight
    mean?" only in the sense of the formula, and the report must not present it
    as an answer about importance.
    """
    return {
        "step": step,
        "perPillar": {name: step * float(weights.get(name, 0.0)) for name in PILLARS},
        "chasePointsPerFinancialPoint": (
            float(weights["financial_rip"]) / float(weights["chase"])
            if weights.get("chase") else None),
        "coreKNeededNote": (
            "Chase points are not linear in K: the saturating transform gives most "
            "of its range to the first few chases, so a fixed Overall-point step "
            "costs progressively more K"),
    }


def k_step_semantics(weights: Mapping[str, float], transform,
                     pairs: Sequence[Tuple[int, int]] = ((0, 1), (1, 2), (2, 3),
                                                         (4, 5), (9, 10), (13, 14))
                     ) -> List[Dict[str, Any]]:
    """Overall points bought by one more Core K, at several places on the curve.

    This is the semantics a reader can actually check against a product page:
    "this box has one more chase card than that one, and it is worth X points".
    """
    weight = float(weights.get("chase", 0.0))
    out: List[Dict[str, Any]] = []
    for low, high in pairs:
        delta = transform(high) - transform(low)
        out.append({
            "fromK": low, "toK": high,
            "chasePointDelta": delta,
            "overallPointDelta": weight * delta,
            "financialPointsEquivalent": (
                weight * delta / float(weights["financial_rip"])
                if weights.get("financial_rip") else None),
        })
    return out
