"""Phases 6 and 11: rank influence, and RIP tier movement through production's own curve.

RESEARCH ONLY.

TIERS ARE NOT COMPUTED ON THE RAW SCORE
---------------------------------------
Production grades a product by leader-normalizing the cohort so the best score
is exactly 100, dividing by ten to the published one-decimal display score, and
then applying locked S/A/B/C/D/F bands. Grading the raw blended score with those
same band numbers would be a different function and would report tier movement
that production would never show. This module therefore calls
``compute_leader_normalized_scores`` and ``public_leader_rip_tier`` directly, so
"a tier change" here means the thing a user would actually see.

A consequence worth stating: the leader curve is COHORT-RELATIVE. Adding Chase
weight moves the leader as well as the followers, so tier movement is not a
simple monotone function of the weight, and the report does not assume it is.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from backend.research.chase_pillar_stage6.stats import kendall_tau, rank, spearman

#: Phase 6's movement buckets.
MOVEMENT_STEPS = (1, 3, 5, 10)


def tiers(scores: Sequence[float], labels: Sequence[str]) -> Dict[str, Optional[str]]:
    """Production tiers for one candidate ranking."""
    from backend.rankings.public_relative import (
        compute_leader_normalized_scores, public_leader_rip_tier,
    )

    rows = [{"id": labels[i], "score": float(scores[i])} for i in range(len(labels))]
    leader = compute_leader_normalized_scores(
        rows, id_getter=lambda r: r["id"], score_getter=lambda r: r["score"])
    return {identity: public_leader_rip_tier(value) for identity, value in leader.items()}


def rank_influence(*, control: Sequence[float], candidate: Sequence[float],
                   labels: Sequence[str]) -> Dict[str, Any]:
    """Phase 6 in full, including the movement histogram the brief asks for."""
    base = np.asarray([float(v) for v in control], dtype=np.float64)
    cand = np.asarray([float(v) for v in candidate], dtype=np.float64)
    base_rank = rank(-base)
    cand_rank = rank(-cand)
    movement = np.abs(cand_rank - base_rank)

    inversions = 0
    n = base.size
    for i in range(n - 1):
        a = np.sign(base[i] - base[i + 1:])
        b = np.sign(cand[i] - cand[i + 1:])
        inversions += int(np.sum((a * b) < 0))

    turnover: Dict[str, Any] = {}
    for size in (5, 10):
        base_top = {labels[i] for i in np.argsort(base_rank)[:size]}
        cand_top = {labels[i] for i in np.argsort(cand_rank)[:size]}
        turnover["top%d" % size] = {
            "overlap": len(base_top & cand_top), "turnover": size - len(base_top & cand_top),
            "entered": sorted(cand_top - base_top), "left": sorted(base_top - cand_top),
        }

    base_tiers = tiers(base, labels)
    cand_tiers = tiers(cand, labels)
    tier_changes = [
        {"label": label, "from": base_tiers.get(label), "to": cand_tiers.get(label)}
        for label in labels if base_tiers.get(label) != cand_tiers.get(label)]

    return {
        "spearman": spearman(list(base), list(cand)),
        "kendallTau": kendall_tau(list(base), list(cand)),
        "medianAbsoluteMovement": float(np.median(movement)),
        "meanAbsoluteMovement": float(movement.mean()),
        "maxMovement": float(movement.max()),
        "pairwiseInversions": inversions,
        "movedAtAll": int(np.sum(movement > 0)),
        "movedAtLeast": {str(step): int(np.sum(movement >= step))
                         for step in MOVEMENT_STEPS},
        "turnover": turnover,
        "tierChanges": len(tier_changes),
        "tierChangeDetail": tier_changes,
        "promotions": sum(1 for c in tier_changes
                          if _tier_order(c["to"]) < _tier_order(c["from"])),
        "demotions": sum(1 for c in tier_changes
                         if _tier_order(c["to"]) > _tier_order(c["from"])),
    }


_TIER_ORDER = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4, "F": 5}


def _tier_order(tier: Optional[str]) -> int:
    return _TIER_ORDER.get(tier or "", 99)


def family_leverage(*, rows: Sequence[Mapping[str, Any]], chase: Sequence[float],
                    control: Sequence[float], candidate: Sequence[float]
                    ) -> List[Dict[str, Any]]:
    """Phase 15: does one nominal weight behave like a larger one for a format?

    Dispersion is the mechanism, so it is dispersion that is reported per family
    rather than the mean score: a format whose Chase scores are tightly bunched
    receives little effective weight no matter what the coefficient says.
    """
    by_family: Dict[str, List[int]] = {}
    for index, row in enumerate(rows):
        by_family.setdefault(row["family"], []).append(index)

    out: List[Dict[str, Any]] = []
    for family, members in sorted(by_family.items()):
        chase_values = np.asarray([chase[i] for i in members], dtype=np.float64)
        base = np.asarray([control[i] for i in members], dtype=np.float64)
        cand = np.asarray([candidate[i] for i in members], dtype=np.float64)
        out.append({
            "family": family,
            "n": len(members),
            "chaseMedian": float(np.median(chase_values)),
            "chaseSd": float(chase_values.std(ddof=1)) if len(members) > 1 else 0.0,
            "meanOverallShift": float((cand - base).mean()),
            "medianCoreK": float(np.median([rows[i]["coreK"] for i in members])),
        })
    return out
