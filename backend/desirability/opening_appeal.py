"""Opening Appeal candidate constructs (research; simulation-covered sets only).

Three submetrics, deliberately kept separate from the all-set universal score:

1. **Universal Roster Appeal** - `universal_set_desirability_v3`, unchanged and
   unmerged. Price-independent, simulation-independent, available for every
   adequately-mapped set. This module never redefines it.
2. **Accessible Appeal** - how reachable the set's *existing* desirable roster
   is, using slot-aware pack logic.
3. **Elite Chase Magnetism** - card-level appeal x card-level modeled scarcity,
   collapsed to one value per distinct subject.

Hard rules:
  * No price, EV, set value, or any market outcome enters any construct here.
  * No coefficient from the card-level price regression is imported. Those fit
    price, not user utility.
  * Scarcity/accessibility are NEVER merged into the universal all-set ranking.
  * The pull input is *modeled*, not observed: call it modeledPullScarcity.

Every weight, anchor, and transform below is a **reasoned default**, not an
empirically-optimized value. Sensitivity variants are parameters.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

OPENING_APPEAL_VERSION = "opening_appeal_candidate_v1_research"
ACCESSIBLE_APPEAL_VERSION = "accessible_appeal_v1_slot_aware"
ELITE_CHASE_MAGNETISM_VERSION = "elite_chase_magnetism_v1_card_level"

# Transform identities. These name the SHAPE of the transform (log10 interpolation
# between two anchors, clamped to [0, 1]); the anchor VALUES are the separate
# constants below. Both are folded into the Collector Appeal fingerprint, so a
# change to either the shape or the anchors invalidates every stored score that
# depended on them. Bump these when the transform's mathematics changes; changing
# an anchor constant alone already moves the fingerprint on its own.
ACCESS_TRANSFORM_VERSION = "access_transform_v1_log10_anchor_interpolation"
SCARCITY_TRANSFORM_VERSION = "scarcity_transform_v1_access_complement"

DEMAND_BASELINE = 50.0

# Shared probability anchors (reasoned defaults): 1-in-10 is "easy", 1-in-1000
# is "elite". Accessibility and scarcity read the same axis from opposite ends,
# so at identical anchors access_transform(p) == 1 - scarcity_transform(p).
# That complementarity is intentional and is an acknowledged tradeoff, not a
# bug - see the archetype tests and the results doc.
EASY_PROBABILITY = 0.1      # 1-in-10
ELITE_PROBABILITY = 0.001   # 1-in-1000

# Candidate Opening Appeal weightings (research candidates; none is "optimal").
OPENING_APPEAL_CANDIDATES: Dict[str, Dict[str, float]] = {
    "OA_60_20_20": {"roster": 0.60, "accessible": 0.20, "magnetism": 0.20},
    "OA_50_25_25": {"roster": 0.50, "accessible": 0.25, "magnetism": 0.25},
    "OA_70_15_15": {"roster": 0.70, "accessible": 0.15, "magnetism": 0.15},
}
OA_BALANCED_KEY = "OA_balanced"
OA_BALANCED_ROSTER_WEIGHT = 0.60
OA_BALANCED_INTERACTION_WEIGHT = 0.40

ACCESSIBLE_BROAD_WEIGHT = 0.60
ACCESSIBLE_TOP3_WEIGHT = 0.40

MAGNETISM_SLOT_WEIGHTS = (0.50, 0.30, 0.20)


def _as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def appeal_excess(subject_demand: Any) -> float:
    """max((demand - 50) / 50, 0) -> 0..1. Price-independent by construction."""
    demand = _as_float(subject_demand)
    if demand is None:
        return 0.0
    return max((demand - DEMAND_BASELINE) / DEMAND_BASELINE, 0.0)


def access_transform(
    probability: Any,
    *,
    easy_probability: float = EASY_PROBABILITY,
    elite_probability: float = ELITE_PROBABILITY,
) -> Optional[float]:
    """Reachability on 0..1: 1-in-10 or easier -> 1.0, 1-in-1000 or harder -> 0."""
    p = _as_float(probability)
    if p is None or p <= 0:
        return None
    low = math.log10(elite_probability)
    high = math.log10(easy_probability)
    if high <= low:
        return None
    return _clamp((math.log10(min(p, 1.0)) - low) / (high - low))


def scarcity_transform(
    probability: Any,
    *,
    easy_probability: float = EASY_PROBABILITY,
    elite_probability: float = ELITE_PROBABILITY,
) -> Optional[float]:
    """Modeled scarcity on 0..1: 1-in-10 -> 0, 1-in-1000 or harder -> 1."""
    access = access_transform(
        probability, easy_probability=easy_probability, elite_probability=elite_probability
    )
    return None if access is None else 1.0 - access


# ---------------------------------------------------------------------------
# Slot-aware probability
# ---------------------------------------------------------------------------

def union_probability_from_cards(cards: Sequence[Mapping[str, Any]]) -> Optional[float]:
    """P(at least one of these cards in one pack), respecting slot structure.

    Cards drawn from the same slot are mutually exclusive outcomes, so their
    probabilities ADD within the slot (clamped at 1). Slots are independent, so
    complements multiply ACROSS slots. An independence formula is never applied
    to cards that share a slot.

    Returns None when no card carries a usable modeled probability.
    """
    by_slot: Dict[str, float] = defaultdict(float)
    seen = False
    for card in cards:
        probability = _as_float(card.get("pull_probability"))
        if probability is None or probability <= 0:
            continue
        seen = True
        by_slot[str(card.get("slot_group") or "__unknown__")] += probability
    if not seen:
        return None
    miss = 1.0
    for slot_total in by_slot.values():
        miss *= 1.0 - _clamp(slot_total)
    return _clamp(1.0 - miss)


def build_subjects(cards: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse eligible cards into distinct subjects with slot-aware probability.

    Each card needs: ``subject_key``, ``subject_name``, ``subject_demand``,
    ``pull_probability`` (per pack), ``slot_group``.
    """
    by_subject: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for card in cards:
        key = str(card.get("subject_key") or "")
        if key:
            by_subject[key].append(card)

    subjects: List[Dict[str, Any]] = []
    for key, subject_cards in by_subject.items():
        demand = max((_as_float(c.get("subject_demand")) or 0.0) for c in subject_cards)
        subjects.append(
            {
                "subject_key": key,
                "subject_name": subject_cards[0].get("subject_name"),
                "subject_demand": demand,
                "appeal_excess": appeal_excess(demand),
                "subject_probability": union_probability_from_cards(subject_cards),
                "cards": list(subject_cards),
                "card_count": len(subject_cards),
            }
        )
    subjects.sort(key=lambda row: (-(row["subject_demand"] or 0.0), str(row["subject_name"] or "")))
    return subjects


# ---------------------------------------------------------------------------
# Accessible Appeal
# ---------------------------------------------------------------------------

def compute_accessible_appeal(
    subjects: Sequence[Mapping[str, Any]],
    *,
    broad_weight: float = ACCESSIBLE_BROAD_WEIGHT,
    top3_weight: float = ACCESSIBLE_TOP3_WEIGHT,
    easy_probability: float = EASY_PROBABILITY,
    elite_probability: float = ELITE_PROBABILITY,
) -> Optional[Dict[str, Any]]:
    """How reachable the set's existing desirable roster is (0-100).

    broad_accessibility = sum(appeal_weight_s * access_transform(P_s)), where
    appeal_weight_s normalizes appeal_excess across desirable subjects - so this
    asks "of the appeal this set has, how much of it can you actually reach?"
    and does not reward simply having more subjects.

    top3_accessibility = P(>= 1 of the top-three desirable subjects in one pack),
    computed by unioning those subjects' CARDS through the slot logic (never by
    multiplying subject-level probabilities, which would double-count a shared
    slot).

    Returns None (never 0) when no desirable subject has modeled pull data.
    """
    desirable = [
        row for row in subjects
        if (row.get("appeal_excess") or 0.0) > 0 and row.get("subject_probability") is not None
    ]
    if not desirable:
        return None

    total_excess = sum(row["appeal_excess"] for row in desirable)
    if total_excess <= 0:
        return None

    broad = 0.0
    contributions = []
    for row in desirable:
        weight = row["appeal_excess"] / total_excess
        access = access_transform(
            row["subject_probability"],
            easy_probability=easy_probability,
            elite_probability=elite_probability,
        )
        if access is None:
            continue
        broad += weight * access
        contributions.append(
            {
                "subject_name": row.get("subject_name"),
                "subject_demand": round(row["subject_demand"], 2),
                "appeal_weight": round(weight, 6),
                "subject_probability": round(row["subject_probability"], 6),
                "one_in_x": round(1.0 / row["subject_probability"], 1) if row["subject_probability"] > 0 else None,
                "access": round(access, 6),
                "contribution": round(weight * access, 6),
            }
        )

    top3_subjects = sorted(desirable, key=lambda row: -(row["appeal_excess"] or 0.0))[:3]
    top3_cards: List[Mapping[str, Any]] = []
    for row in top3_subjects:
        top3_cards.extend(row.get("cards") or [])
    top3 = union_probability_from_cards(top3_cards)
    if top3 is None:
        top3 = 0.0

    total_weight = broad_weight + top3_weight
    score = 100.0 * ((broad_weight * broad + top3_weight * top3) / total_weight)
    return {
        "score": round(_clamp(score, 0.0, 100.0), 4),
        "broad_accessibility": round(broad, 6),
        "top3_accessibility": round(top3, 6),
        "version": ACCESSIBLE_APPEAL_VERSION,
        "weights": {"broad": broad_weight, "top3": top3_weight},
        "anchors": {"easy_probability": easy_probability, "elite_probability": elite_probability},
        "weights_label": "Reasoned defaults, not fitted.",
        "desirable_subject_count": len(desirable),
        "top3_subjects": [row.get("subject_name") for row in top3_subjects],
        "top_contributors": sorted(contributions, key=lambda item: -item["contribution"])[:10],
    }


# ---------------------------------------------------------------------------
# Elite Chase Magnetism
# ---------------------------------------------------------------------------

def compute_elite_chase_magnetism(
    subjects: Sequence[Mapping[str, Any]],
    *,
    slot_weights: Sequence[float] = MAGNETISM_SLOT_WEIGHTS,
    easy_probability: float = EASY_PROBABILITY,
    elite_probability: float = ELITE_PROBABILITY,
) -> Optional[Dict[str, Any]]:
    """Card-level appeal x card-level modeled scarcity, per distinct subject.

    Reproduces the construct the market study validated (card appeal x card
    scarcity) rather than using a subject's any-card probability:

        card_magnetism    = appeal_excess(subject) * scarcity_transform(p_card)
        subject_magnetism = max(card_magnetism over that subject's cards)

    Taking the MAX (not the union probability) is what stops an accessible
    secondary printing from erasing an elite chase's scarcity, and collapsing to
    distinct subjects is what stops one Pokemon from occupying several chase
    slots.

    Returns None (never 0) when no card has modeled pull data.
    """
    scored: List[Dict[str, Any]] = []
    for row in subjects:
        excess = row.get("appeal_excess") or 0.0
        best: Optional[Dict[str, Any]] = None
        for card in row.get("cards") or []:
            scarcity = scarcity_transform(
                card.get("pull_probability"),
                easy_probability=easy_probability,
                elite_probability=elite_probability,
            )
            if scarcity is None:
                continue
            magnetism = excess * scarcity
            if best is None or magnetism > best["card_magnetism"]:
                probability = _as_float(card.get("pull_probability")) or 0.0
                best = {
                    "card_magnetism": magnetism,
                    "card_name": card.get("card_name"),
                    "rarity": card.get("rarity"),
                    "pull_probability": probability,
                    "one_in_x": round(1.0 / probability, 1) if probability > 0 else None,
                    "scarcity": round(scarcity, 6),
                }
        if best is None:
            continue
        scored.append(
            {
                "subject_key": row.get("subject_key"),
                "subject_name": row.get("subject_name"),
                "subject_demand": round(row.get("subject_demand") or 0.0, 2),
                "appeal_excess": round(excess, 6),
                "subject_magnetism": round(best["card_magnetism"], 6),
                "driving_card": best,
            }
        )
    if not scored:
        return None

    scored.sort(key=lambda row: (-(row["subject_magnetism"]), str(row.get("subject_name") or "")))
    ranked = scored[: len(slot_weights)]
    raw_weights = list(slot_weights)[: len(ranked)]
    total = sum(raw_weights)
    if total <= 0:
        return None
    # Missing slots renormalize (never insert zero), mirroring Roster Appeal.
    effective = [w / total for w in raw_weights]
    score = 100.0 * sum(row["subject_magnetism"] * weight for row, weight in zip(ranked, effective))
    return {
        "score": round(_clamp(score, 0.0, 100.0), 4),
        "version": ELITE_CHASE_MAGNETISM_VERSION,
        "slot_weights": list(slot_weights),
        "effective_slot_weights": [round(w, 6) for w in effective],
        "anchors": {"easy_probability": easy_probability, "elite_probability": elite_probability},
        "weights_label": "Reasoned defaults, not fitted.",
        "distinct_subject_count": len(scored),
        "top_subjects": [
            {**row, "slot_weight": round(weight, 6)} for row, weight in zip(ranked, effective)
        ],
    }


# ---------------------------------------------------------------------------
# Opening Appeal candidates
# ---------------------------------------------------------------------------

def compute_opening_appeal_candidates(
    *,
    roster_appeal: Any,
    accessible_appeal: Any,
    elite_chase_magnetism: Any,
) -> Dict[str, Optional[float]]:
    """All candidate Opening Appeal formulas. None when an input is missing.

    Missing inputs yield None (never 0) so a set without modeled pull data is
    reported unavailable rather than scored as unappealing.
    """
    roster = _as_float(roster_appeal)
    accessible = _as_float(accessible_appeal)
    magnetism = _as_float(elite_chase_magnetism)
    if roster is None or accessible is None or magnetism is None:
        return {key: None for key in list(OPENING_APPEAL_CANDIDATES) + [OA_BALANCED_KEY]}

    candidates: Dict[str, Optional[float]] = {}
    for name, weights in OPENING_APPEAL_CANDIDATES.items():
        candidates[name] = round(
            weights["roster"] * roster
            + weights["accessible"] * accessible
            + weights["magnetism"] * magnetism,
            4,
        )
    # Balance-sensitive candidate: the geometric mean rewards having BOTH
    # attainable favorites and elite chases, and collapses toward 0 when either
    # is absent. That is an explicit product judgment, not an empirical result.
    candidates[OA_BALANCED_KEY] = round(
        OA_BALANCED_ROSTER_WEIGHT * roster
        + OA_BALANCED_INTERACTION_WEIGHT * math.sqrt(max(accessible, 0.0) * max(magnetism, 0.0)),
        4,
    )
    return candidates


def opening_appeal_payload(
    *,
    roster_appeal: Any,
    accessible: Optional[Mapping[str, Any]],
    magnetism: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    accessible_score = (accessible or {}).get("score")
    magnetism_score = (magnetism or {}).get("score")
    return {
        "version": OPENING_APPEAL_VERSION,
        "rosterAppeal": _as_float(roster_appeal),
        "accessibleAppeal": accessible_score,
        "eliteChaseMagnetism": magnetism_score,
        "candidates": compute_opening_appeal_candidates(
            roster_appeal=roster_appeal,
            accessible_appeal=accessible_score,
            elite_chase_magnetism=magnetism_score,
        ),
        "available": accessible_score is not None and magnetism_score is not None,
        "inputsLabel": "modeledPullScarcity (config-derived pack model), never observed pull data.",
        "excludedInputs": ["market_price", "set_value", "expected_value", "profit", "any_market_outcome"],
    }
