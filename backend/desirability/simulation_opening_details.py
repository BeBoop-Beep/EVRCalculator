"""Simulation Opening Details v1 (simulationCoverage=full sets only).

Pull-access metrics computed from actual per-card pack probabilities. These
describe how *reachable* the desirable subjects are in one pack; they never
alter the universal desirability score or rank (Phase 8 rule).

Probability model
-----------------
Cards that share a pack slot are mutually exclusive outcomes, so their
probabilities ADD within a slot; independence applies only ACROSS slots.
When per-card slot groups are known we use the exact
``1 - prod_over_slots(1 - sum_within_slot(p))``. When slot structure is not
available for a set, we fall back to the additive capped bound
``min(sum(p_i), 1)`` - exact for same-slot cards, a slight overestimate
across slots - and report the method used per subject, so the approximation
is never silent.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.desirability.scoring_config import SIMULATION_OPENING_DETAILS_VERSION


DEMAND_THRESHOLDS = (60.0, 75.0, 90.0)

# --- Chase Magnetism (simulation-only; NOT part of Universal Set Desirability) ---
# The card-level market amplification study found that (a) price-independent
# appeal adds incremental out-of-sample value for log(price) beyond structural
# controls and actual pull scarcity, and (b) the appeal x scarcity interaction
# is positive and robust: the price slope on appeal is several times steeper for
# hard-to-pull cards than for easy ones. Chase Magnetism exposes that structure
# as its own simulation-only metric.
#
# Hard rules:
#   * It is NEVER merged into Universal Set Desirability, which must stay pure,
#     price-independent, simulation-independent subject appeal available across
#     all eras (including eras with no pull model at all).
#   * It does NOT feed RIP. The Profit/Safety/Stability pillars already contain
#     pull-distribution and price information, so admitting it would require a
#     redundancy audit against those pillars first.
#   * Its shape is a REASONED DEFAULT chosen structurally. No coefficient from
#     the price model is transferred here - those fit price, not user utility.
CHASE_MAGNETISM_DEMAND_BASELINE = 50.0
# Scarcity reference points for normalizing -log10(p): 1-in-10 -> 0, 1-in-1000 -> 1.
CHASE_MAGNETISM_SCARCITY_FLOOR = 1.0
CHASE_MAGNETISM_SCARCITY_CEILING = 3.0
CHASE_MAGNETISM_SATURATION_K = 2.0
CHASE_MAGNETISM_VERSION = "chase_magnetism_v1_simulation_only"

# Deterministic thresholds behind the Opening Experience labels. Reasoned
# defaults; these labels are interpretation only and are never weighted into
# desirability or RIP.
EXPERIENCE_THRESHOLDS = {
    "accessible_any_top3_probability": 0.05,
    "elite_subject_demand": 85.0,
    "broad_coverage_subjects_above_60": 8,
    "strong_top_subject_demand": 75.0,
}

METHOD_SLOT_EXACT = "slot_exclusive_exact"
METHOD_ADDITIVE_CAPPED = "additive_mutually_exclusive_approximation"


def _as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _subject_access_probability(cards: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """P(>=1 eligible card for the subject in one pack)."""
    with_slots = [card for card in cards if card.get("slot_group")]
    probabilities = [
        _as_float(card.get("pull_probability"))
        for card in cards
        if _as_float(card.get("pull_probability")) is not None
    ]
    if not probabilities:
        return {"probability": None, "method": None, "card_count": len(cards)}

    if len(with_slots) == len(cards):
        by_slot: Dict[str, float] = defaultdict(float)
        for card in cards:
            probability = _as_float(card.get("pull_probability"))
            if probability is not None:
                by_slot[str(card.get("slot_group"))] += probability
        miss = 1.0
        for slot_probability in by_slot.values():
            miss *= 1.0 - _clamp_probability(slot_probability)
        return {
            "probability": _clamp_probability(1.0 - miss),
            "method": METHOD_SLOT_EXACT,
            "card_count": len(cards),
        }

    return {
        "probability": _clamp_probability(sum(probabilities)),
        "method": METHOD_ADDITIVE_CAPPED,
        "card_count": len(cards),
    }


def compute_simulation_opening_details(
    card_rows: Sequence[Mapping[str, Any]],
    *,
    special_pack: Optional[Mapping[str, Any]] = None,
    inaccessible_probability_threshold: float = 0.005,
) -> Dict[str, Any]:
    """Compute Pull-Accessible Favorite Exposure and Special Pack Appeal.

    ``card_rows``: one entry per eligible card with a known subject -
        ``subject_key``, ``subject_name``, ``subject_demand`` (Pure Demand),
        ``pull_probability`` (per single pack), optional ``slot_group``,
        optional ``hit_family`` (rarity bucket) and ``card_name``.
    ``special_pack``: optional ``{"probability": p, "expected_demand_exposure": d}``;
        ``None`` when the set has no special-pack mechanic (result is null,
        never zero).
    """
    by_subject: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in card_rows:
        subject_key = str(row.get("subject_key") or "")
        if subject_key:
            by_subject[subject_key].append(row)

    subjects: List[Dict[str, Any]] = []
    for subject_key, cards in by_subject.items():
        demand = max(
            (_as_float(card.get("subject_demand")) or 0.0 for card in cards),
            default=0.0,
        )
        access = _subject_access_probability(cards)
        family_contributions: Dict[str, float] = defaultdict(float)
        for card in cards:
            probability = _as_float(card.get("pull_probability"))
            family = str(card.get("hit_family") or "unknown")
            if probability is not None:
                family_contributions[family] += probability
        subjects.append(
            {
                "subject_key": subject_key,
                "subject_name": cards[0].get("subject_name"),
                "subject_demand": round(demand, 4),
                "subject_access_probability": access["probability"],
                "probability_method": access["method"],
                "eligible_card_count": access["card_count"],
                "access_by_hit_family": {
                    family: round(value, 6) for family, value in sorted(family_contributions.items())
                },
            }
        )

    subjects.sort(key=lambda row: (-(row["subject_demand"] or 0.0), str(row["subject_name"] or "")))
    accessible = [row for row in subjects if row["subject_access_probability"] is not None]

    raw_accessible_demand = sum(
        row["subject_access_probability"] * row["subject_demand"] for row in accessible
    )

    top_subject = subjects[0] if subjects else None
    top3 = subjects[:3]
    top3_probabilities = [
        row["subject_access_probability"]
        for row in top3
        if row["subject_access_probability"] is not None
    ]
    any_top3_probability = (
        _clamp_probability(1.0 - math.prod(1.0 - _clamp_probability(p) for p in top3_probabilities))
        if top3_probabilities
        else None
    )

    threshold_probabilities: Dict[str, Optional[float]] = {}
    for threshold in DEMAND_THRESHOLDS:
        probabilities = [
            row["subject_access_probability"]
            for row in accessible
            if row["subject_demand"] > threshold
        ]
        threshold_probabilities[f"p_subject_above_{int(threshold)}"] = (
            _clamp_probability(1.0 - math.prod(1.0 - _clamp_probability(p) for p in probabilities))
            if probabilities
            else None
        )

    most_accessible_favorites = sorted(
        (row for row in accessible if row["subject_demand"] > 60.0),
        key=lambda row: -(row["subject_access_probability"] * row["subject_demand"]),
    )[:10]
    desirable_but_inaccessible = [
        row
        for row in subjects
        if row["subject_demand"] > 75.0
        and (
            row["subject_access_probability"] is None
            or row["subject_access_probability"] < inaccessible_probability_threshold
        )
    ][:10]

    special_pack_appeal = None
    if isinstance(special_pack, Mapping):
        probability = _as_float(special_pack.get("probability"))
        exposure = _as_float(special_pack.get("expected_demand_exposure"))
        if probability is not None and exposure is not None:
            special_pack_appeal = {
                "special_event_probability": probability,
                "expected_additional_demand_exposure": round(exposure, 4),
                "appeal": round(probability * exposure, 6),
            }

    return {
        "version": SIMULATION_OPENING_DETAILS_VERSION,
        "pull_accessible_favorite_exposure": {
            "raw_accessible_demand": round(raw_accessible_demand, 4),
            "subject_count": len(subjects),
            "subjects_with_probability": len(accessible),
            "top_subject_encounter_probability": (
                top_subject["subject_access_probability"] if top_subject else None
            ),
            "any_top3_encounter_probability": any_top3_probability,
            **threshold_probabilities,
            "most_accessible_favorites": most_accessible_favorites,
            "desirable_but_inaccessible_subjects": desirable_but_inaccessible,
            "subjects": subjects,
        },
        "special_pack_appeal": special_pack_appeal,
        "chase_magnetism": compute_chase_magnetism(subjects),
        "opening_experience": interpret_opening_experience(
            subjects=subjects,
            any_top3_probability=any_top3_probability,
            special_pack_appeal=special_pack_appeal,
        ),
        "does_not_alter": [
            "universal_set_desirability_score",
            "universal_set_desirability_rank",
            "rip_weights",
        ],
    }


def compute_chase_magnetism(subjects: Sequence[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Simulation-only "popular Pokemon on genuinely hard-to-pull cards" metric.

    Per distinct subject:
        appeal_excess   = max((demand - 50) / 50, 0)                  in [0, 1]
        scarcity_weight = clamp((-log10(p) - floor) / (ceil - floor)) in [0, 1]
        contribution    = appeal_excess * scarcity_weight

    Set score = saturated sum of contributions, 0-100. Both the reference
    scarcity band (1-in-10 .. 1-in-1000) and the saturation constant are
    reasoned defaults, not fitted values.

    Returns None (never 0) when no subject has a usable pull probability.
    """
    contributions: List[Dict[str, Any]] = []
    for row in subjects:
        probability = _as_float(row.get("subject_access_probability"))
        demand = _as_float(row.get("subject_demand"))
        if probability is None or probability <= 0 or demand is None:
            continue
        appeal_excess = max((demand - CHASE_MAGNETISM_DEMAND_BASELINE) / CHASE_MAGNETISM_DEMAND_BASELINE, 0.0)
        scarcity = -math.log10(min(probability, 1.0))
        scarcity_weight = (scarcity - CHASE_MAGNETISM_SCARCITY_FLOOR) / (
            CHASE_MAGNETISM_SCARCITY_CEILING - CHASE_MAGNETISM_SCARCITY_FLOOR
        )
        scarcity_weight = max(0.0, min(1.0, scarcity_weight))
        contribution = appeal_excess * scarcity_weight
        if contribution > 0:
            contributions.append(
                {
                    "subject_name": row.get("subject_name"),
                    "subject_demand": demand,
                    "pull_scarcity_neg_log10_p": round(scarcity, 4),
                    "one_in_x": round(1.0 / probability, 1),
                    "contribution": round(contribution, 6),
                }
            )
    if not contributions:
        return None
    raw = sum(item["contribution"] for item in contributions)
    score = 100.0 * (1.0 - math.exp(-raw / CHASE_MAGNETISM_SATURATION_K))
    return {
        "score": round(score, 4),
        "raw": round(raw, 4),
        "version": CHASE_MAGNETISM_VERSION,
        "contributing_subject_count": len(contributions),
        "top_contributors": sorted(contributions, key=lambda item: -item["contribution"])[:10],
        "weights_label": "Reasoned defaults, not fitted to price.",
        "policy": (
            "Simulation-only. Never merged into Universal Set Desirability and "
            "never fed into RIP without a redundancy audit against Profit, "
            "Safety, and Stability, which already carry pull and price information."
        ),
    }


def interpret_opening_experience(
    *,
    subjects: Sequence[Mapping[str, Any]],
    any_top3_probability: Optional[float],
    special_pack_appeal: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Deterministic, threshold-backed label. Interpretation only."""
    strong_subjects = [row for row in subjects if (row.get("subject_demand") or 0.0) > 60.0]
    elite_subjects = [
        row for row in subjects
        if (row.get("subject_demand") or 0.0) >= EXPERIENCE_THRESHOLDS["elite_subject_demand"]
    ]
    accessible_top3 = (
        any_top3_probability is not None
        and any_top3_probability >= EXPERIENCE_THRESHOLDS["accessible_any_top3_probability"]
    )

    if special_pack_appeal is not None and (special_pack_appeal.get("appeal") or 0.0) > 0:
        label = "special_pack_upside"
    elif len(strong_subjects) >= EXPERIENCE_THRESHOLDS["broad_coverage_subjects_above_60"] and accessible_top3:
        label = "deep_and_accessible"
    elif len(strong_subjects) >= EXPERIENCE_THRESHOLDS["broad_coverage_subjects_above_60"]:
        label = "broad_coverage"
    elif len(elite_subjects) == 1 and len(strong_subjects) <= 2:
        label = "one_elite_chase"
    elif strong_subjects and not accessible_top3:
        label = "strong_but_hard_to_pull"
    elif strong_subjects:
        label = "deep_and_accessible" if accessible_top3 else "broad_coverage"
    else:
        label = "limited_subject_appeal"

    return {
        "label": label,
        "thresholds": dict(EXPERIENCE_THRESHOLDS),
        "note": "Deterministic interpretation; never a hidden weight in any score.",
    }
