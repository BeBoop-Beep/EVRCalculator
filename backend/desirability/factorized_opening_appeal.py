"""Factorized Opening Appeal candidates (RESEARCH ONLY; never wired into RIP).

Tests the hypothesis that the previously rejected merged Opening Appeal failed
because Pokemon desirability was embedded *repeatedly* across Universal Roster
Appeal, Accessible Appeal, and Elite Chase Magnetism. The proposed remedy:

    Opening Appeal = Desirability x Opening Structure

where desirability is applied EXACTLY ONCE and the structural factors describe
only how that desirability is distributed through the pack-opening experience.

AUDIT FINDING (see the results doc): the repeated-desirability premise is only
half true.

  * ``compute_accessible_appeal`` weights by ``appeal_excess / total_excess`` -
    a NORMALIZED share. The absolute desirability magnitude already cancels, so
    Accessible Appeal was ALREADY factor-free. ``A*`` below reproduces it.
  * ``compute_elite_chase_magnetism`` uses ``appeal_excess * scarcity`` - the
    absolute magnitude genuinely IS multiplied in. Magnetism is the real
    offender, which is why it correlates ~0.75 with Roster Appeal while
    Accessibility correlates ~-0.15.

So factorization removes double-counting from the Magnetism path only.

Hard rules enforced here (asserted in the unit tests):
  * No price, EV, profit, set value, or any market outcome enters any factor.
  * No Treatment Prestige enters any factor.
  * Desirability is applied exactly once, in ``D``. ``A*`` and ``M*`` may use
    desirability to SELECT and PRIORITIZE subjects (normalized shares, demand
    ranking) but never to scale magnitude a second time.
  * Fixed normalization only: no cohort percentiles. Adding or removing a set
    can never move another set's score.
  * Missing pull data returns None ("unavailable"), never 0.
  * The pull input is *modeled* (config-derived pack model), never observed.

Every weight, anchor, and saturation constant is a **reasoned default**, not an
empirically optimized value. Nothing here is fitted to price.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from backend.desirability.opening_appeal import (
    EASY_PROBABILITY,
    ELITE_PROBABILITY,
    access_transform,
    appeal_excess,
    scarcity_transform,
    union_probability_from_cards,
)
from backend.desirability.scoring_config import FAVORITE_COVERAGE_SATURATION_K

FACTORIZED_OPENING_APPEAL_VERSION = "factorized_opening_appeal_v1_research"
D_FACTOR_VERSION = "desirability_factor_v1"
A_STAR_VERSION = "accessibility_structure_v1_factor_free"
M_STAR_VERSION = "elite_chase_structure_v1_factor_free"

# --- D2 saturation constants -------------------------------------------------
# The existing convention is FAVORITE_COVERAGE_SATURATION_K (3.0). Fixed and
# documented, never a cohort percentile.
#
# NOTE: D2 at K_D = 3.0 is *algebraically identical* to Universal Roster
# Appeal's own ``favorite_hit_coverage`` component / 100. D2 is therefore not a
# new construct; it is one of D1's three components promoted to stand alone.
D_SATURATION_K_DEFAULT = float(FAVORITE_COVERAGE_SATURATION_K)
D_SATURATION_K_VARIANTS: Tuple[float, ...] = (2.0, 3.0, 4.5, 6.0)

# --- A* structural weightings (reasoned defaults + pre-registered variants) ---
A_STAR_BROAD_WEIGHT = 0.60
A_STAR_TOP3_WEIGHT = 0.40
A_STAR_VARIANTS: Dict[str, Tuple[float, float]] = {
    "A_60_40": (0.60, 0.40),
    "A_70_30": (0.70, 0.30),
    "A_50_50": (0.50, 0.50),
    "A_broad_only": (1.00, 0.00),
    "A_top3_only": (0.00, 1.00),
}

# --- M* slot weightings ------------------------------------------------------
M_STAR_SLOT_WEIGHTS: Tuple[float, ...] = (0.50, 0.30, 0.20)
M_STAR_TOP_N_VARIANTS: Dict[str, Tuple[float, ...]] = {
    "M1_top1": (1.0,),
    "M1_top3": (0.50, 0.30, 0.20),
    "M1_top5": (0.40, 0.25, 0.15, 0.12, 0.08),
}

# --- Probability anchors (fixed; never fitted to price) ----------------------
ANCHOR_VARIANTS: Dict[str, Dict[str, float]] = {
    "anchors_1in10_to_1in1000": {"easy_probability": 0.1, "elite_probability": 0.001},
    "anchors_1in5_to_1in500": {"easy_probability": 0.2, "elite_probability": 0.002},
    "anchors_1in20_to_1in2000": {"easy_probability": 0.05, "elite_probability": 0.0005},
}

# --- F3 pre-registered alphas ------------------------------------------------
# Pre-registered BEFORE looking at any outcome. There is deliberately no search
# loop over alpha: fitting alpha to price would make this a price model.
F3_ALPHAS: Tuple[float, ...] = (0.25, 0.50, 0.75)

FACTORIZED_CANDIDATE_KEYS: Tuple[str, ...] = (
    "F1_balanced_multiplicative",
    "F2_either_path_union",
    "F3_alpha_0.25",
    "F3_alpha_0.50",
    "F3_alpha_0.75",
    "F4_market_chase",
    "F5_accessible_roster",
    "F6_roster_baseline",
)

# Product classification labels (section 17 of the study brief).
LABEL_UNIVERSAL_ROSTER = "universal_roster_appeal"
LABEL_ACCESSIBLE_OPENING = "accessible_opening_appeal"
LABEL_MARKET_CHASE = "market_chase_strength"
LABEL_BALANCED_OPENING = "balanced_opening_experience"
LABEL_NOT_RECOMMENDED = "not_recommended"


def _as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# The shared desirability factor D
# ---------------------------------------------------------------------------

def raw_desirability_mass(subject_demands: Iterable[Any]) -> float:
    """``D2_raw = sum(sqrt(u_s))`` over DISTINCT subjects.

    ``u_s = max((demand - 50) / 50, 0)``. sqrt gives diminishing returns so a
    large modern checklist cannot win on roster size alone. Each subject is
    counted exactly once (callers must pass distinct subjects).

    Price-independent, probability-independent, prestige-independent,
    era-independent, simulation-independent by construction: the only input is
    subject demand.
    """
    total = 0.0
    for demand in subject_demands:
        excess = appeal_excess(demand)
        if excess > 0:
            total += math.sqrt(excess)
    return total


def compute_d2(
    subject_demands: Iterable[Any],
    *,
    saturation_k: float = D_SATURATION_K_DEFAULT,
) -> Dict[str, Any]:
    """D2 - raw distinct-subject desirability mass, fixed-saturated onto [0,1].

        D2 = 1 - exp(-D2_raw / K_D)

    ``K_D`` is a fixed documented constant, never a cohort percentile, so a
    set's D2 never depends on which other sets are in the cohort.
    """
    demands = list(subject_demands)
    raw = raw_desirability_mass(demands)
    k = float(saturation_k)
    if k <= 0:
        raise ValueError("saturation_k must be positive")
    value = 0.0 if raw <= 0 else 1.0 - math.exp(-raw / k)
    return {
        "value": _clamp(value),
        "raw_mass": round(raw, 6),
        "saturation_k": k,
        "distinct_subject_count": len(demands),
        "contributing_subject_count": sum(1 for d in demands if appeal_excess(d) > 0),
        "version": D_FACTOR_VERSION,
        "formula": "1 - exp(-sum(sqrt(max((demand-50)/50, 0))) / K_D)",
        "excluded_inputs": [
            "market_price", "expected_value", "profit", "set_value",
            "pull_probability", "treatment_prestige", "era", "simulation_output",
        ],
    }


def compute_d1(roster_appeal: Any) -> Optional[float]:
    """D1 - the existing Universal Roster Appeal rescaled to [0,1].

    Preserves the current product interpretation and makes the comparison
    against the shipping pillar direct.
    """
    value = _as_float(roster_appeal)
    return None if value is None else _clamp(value / 100.0)


# ---------------------------------------------------------------------------
# Shared subject helpers
# ---------------------------------------------------------------------------

def desirable_subjects(subjects: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """Subjects with demand strictly above the baseline (u_s > 0).

    This is desirability used as SELECTION, which the design explicitly permits.
    It is not a second application of desirability *magnitude*.
    """
    return [row for row in subjects if (_as_float(row.get("appeal_excess")) or 0.0) > 0.0]


def demand_shares(subjects: Sequence[Mapping[str, Any]]) -> Dict[str, float]:
    """``q_s = u_s / sum(u_s)`` over desirable distinct subjects.

    These shares say how the common desirability mass is DISTRIBUTED. They sum
    to 1, so the absolute magnitude of desirability cancels and cannot be
    applied a second time inside a structural factor.
    """
    eligible = desirable_subjects(subjects)
    total = sum((_as_float(row.get("appeal_excess")) or 0.0) for row in eligible)
    if total <= 0:
        return {}
    return {
        str(row.get("subject_key")): (_as_float(row.get("appeal_excess")) or 0.0) / total
        for row in eligible
    }


def _rank_by_demand(subjects: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """Highest subject demand first; name breaks ties deterministically."""
    return sorted(
        subjects,
        key=lambda row: (-(_as_float(row.get("subject_demand")) or 0.0), str(row.get("subject_name") or "")),
    )


# ---------------------------------------------------------------------------
# A* - factor-free accessibility structure
# ---------------------------------------------------------------------------

TOP3_MODE_PROBABILITY = "raw_probability"
TOP3_MODE_ACCESS = "access_transform"


def compute_a_star(
    subjects: Sequence[Mapping[str, Any]],
    *,
    broad_weight: float = A_STAR_BROAD_WEIGHT,
    top3_weight: float = A_STAR_TOP3_WEIGHT,
    easy_probability: float = EASY_PROBABILITY,
    elite_probability: float = ELITE_PROBABILITY,
    top3_mode: str = TOP3_MODE_PROBABILITY,
) -> Optional[Dict[str, Any]]:
    """Probability structure applied to an already-defined desirable roster.

        broad_access_structure = sum(q_s * access_transform(p_subject_s))
        top3_access_structure  = P(>=1 eligible card from the three
                                   highest-demand distinct subjects)
        A* = 0.60 * broad + 0.40 * top3

    ``q_s`` are normalized shares, so absolute desirability never re-enters.
    ``top3_access_structure`` is computed from the underlying CARDS through the
    slot logic (probabilities add within a mutually exclusive slot; independent
    slots multiply), never by combining already-aggregated subject
    probabilities under a false independence assumption.

    SCALE-MIXING CAVEAT (reported, not silently fixed): the pre-registered
    definition mixes a LOG-scaled quantity (``broad``, via access_transform)
    with a LINEAR one (``top3``, a raw probability). Real per-pack top-3
    probabilities are small (order 1e-2), so the raw top3 term sits near 0 for
    every set and mostly acts as a near-constant shrink of ``broad`` rather than
    an independent axis. ``top3_mode=access_transform`` is the pre-registered
    sensitivity variant that puts both terms on the same log axis. The default
    follows the brief literally; both are reported.

    Returns None (never 0) when no desirable subject carries modeled pull data.
    """
    eligible = [
        row for row in desirable_subjects(subjects)
        if row.get("subject_probability") is not None
    ]
    if not eligible:
        return None

    shares = demand_shares(eligible)
    if not shares:
        return None

    broad = 0.0
    contributions: List[Dict[str, Any]] = []
    for row in eligible:
        key = str(row.get("subject_key"))
        share = shares.get(key)
        probability = _as_float(row.get("subject_probability"))
        if share is None or probability is None:
            continue
        access = access_transform(
            probability,
            easy_probability=easy_probability,
            elite_probability=elite_probability,
        )
        if access is None:
            continue
        broad += share * access
        contributions.append(
            {
                "subject_name": row.get("subject_name"),
                "subject_demand": round(_as_float(row.get("subject_demand")) or 0.0, 2),
                "demand_share": round(share, 6),
                "subject_probability": round(probability, 8),
                "one_in_x": round(1.0 / probability, 1) if probability > 0 else None,
                "access": round(access, 6),
                "contribution": round(share * access, 6),
            }
        )

    # Top three by SUBJECT DEMAND (the brief's rule), unioned through slots.
    top3_subjects = _rank_by_demand(eligible)[:3]
    top3_cards: List[Mapping[str, Any]] = []
    for row in top3_subjects:
        top3_cards.extend(row.get("cards") or [])
    top3_probability = union_probability_from_cards(top3_cards)
    top3_probability = 0.0 if top3_probability is None else top3_probability
    if top3_mode == TOP3_MODE_ACCESS:
        transformed = access_transform(
            top3_probability,
            easy_probability=easy_probability,
            elite_probability=elite_probability,
        ) if top3_probability > 0 else 0.0
        top3_structure = 0.0 if transformed is None else transformed
    elif top3_mode == TOP3_MODE_PROBABILITY:
        top3_structure = _clamp(top3_probability)
    else:
        raise ValueError(f"unknown top3_mode: {top3_mode!r}")

    total_weight = broad_weight + top3_weight
    if total_weight <= 0:
        return None
    value = (broad_weight * broad + top3_weight * top3_structure) / total_weight

    return {
        "value": _clamp(value),
        "broad_access_structure": round(broad, 6),
        "top3_access_structure": round(top3_structure, 6),
        "top3_raw_probability": round(top3_probability, 8),
        "top3_mode": top3_mode,
        "version": A_STAR_VERSION,
        "weights": {"broad": broad_weight, "top3": top3_weight},
        "anchors": {"easy_probability": easy_probability, "elite_probability": elite_probability},
        "weights_label": "Reasoned defaults, not fitted.",
        "desirable_subject_count": len(eligible),
        "top3_subjects": [row.get("subject_name") for row in top3_subjects],
        "top_contributors": sorted(contributions, key=lambda item: -item["contribution"])[:10],
    }


def accessibility_interpretations(
    subjects: Sequence[Mapping[str, Any]],
    *,
    etb_packs: int = 9,
    booster_box_packs: int = 36,
) -> Optional[Dict[str, Any]]:
    """Direct user-facing readings that need no transform to interpret.

    A score on [0,1] is not something a collector can act on; these are.
    ``median_packs_to_top3`` is only mathematically valid for independent
    repeated packs, which is why it is reported as None when p <= 0.
    """
    eligible = [
        row for row in desirable_subjects(subjects)
        if row.get("subject_probability") is not None
    ]
    if not eligible:
        return None

    any_cards: List[Mapping[str, Any]] = []
    for row in eligible:
        any_cards.extend(row.get("cards") or [])
    p_any = union_probability_from_cards(any_cards) or 0.0

    top3_cards: List[Mapping[str, Any]] = []
    for row in _rank_by_demand(eligible)[:3]:
        top3_cards.extend(row.get("cards") or [])
    p_top3 = union_probability_from_cards(top3_cards) or 0.0

    def per_opening(probability: float, packs: int) -> Optional[float]:
        if probability <= 0:
            return None
        return round(1.0 - (1.0 - probability) ** packs, 6)

    median_packs = None
    if 0 < p_top3 < 1:
        median_packs = round(math.log(0.5) / math.log(1.0 - p_top3), 2)
    elif p_top3 >= 1:
        median_packs = 1.0

    return {
        "p_any_desirable_subject_per_pack": round(p_any, 8),
        "p_top3_desirable_subject_per_pack": round(p_top3, 8),
        "one_in_x_any_desirable": round(1.0 / p_any, 1) if p_any > 0 else None,
        "one_in_x_top3": round(1.0 / p_top3, 1) if p_top3 > 0 else None,
        "median_packs_to_top3_encounter": median_packs,
        "p_top3_per_etb": per_opening(p_top3, etb_packs),
        "p_top3_per_booster_box": per_opening(p_top3, booster_box_packs),
        "p_any_per_etb": per_opening(p_any, etb_packs),
        "p_any_per_booster_box": per_opening(p_any, booster_box_packs),
        "etb_packs": etb_packs,
        "booster_box_packs": booster_box_packs,
        "note": (
            "Per-opening probabilities assume independent packs, which overstates "
            "certainty for products with anti-duplicate or guaranteed-slot rules."
        ),
    }


# ---------------------------------------------------------------------------
# M* - factor-free elite chase structure
# ---------------------------------------------------------------------------

def subject_elite_scarcity(
    subject: Mapping[str, Any],
    *,
    easy_probability: float = EASY_PROBABILITY,
    elite_probability: float = ELITE_PROBABILITY,
) -> Optional[Dict[str, Any]]:
    """``max(scarcity_transform(p_card))`` over the subject's eligible cards.

    Taking the MAX (never a union probability) is what stops an accessible
    secondary printing from erasing an elite chase's scarcity. Collapsing to one
    value per distinct subject is what stops one Pokemon taking several slots.

    Desirability magnitude is deliberately absent here - that is the whole point
    of the factorization.
    """
    best: Optional[Dict[str, Any]] = None
    for card in subject.get("cards") or []:
        scarcity = scarcity_transform(
            card.get("pull_probability"),
            easy_probability=easy_probability,
            elite_probability=elite_probability,
        )
        if scarcity is None:
            continue
        if best is None or scarcity > best["scarcity"]:
            probability = _as_float(card.get("pull_probability")) or 0.0
            best = {
                "scarcity": scarcity,
                "card_name": card.get("card_name"),
                "rarity": card.get("rarity"),
                "pull_probability": probability,
                "one_in_x": round(1.0 / probability, 1) if probability > 0 else None,
            }
    return best


def _scored_subjects(
    subjects: Sequence[Mapping[str, Any]],
    *,
    easy_probability: float,
    elite_probability: float,
) -> List[Dict[str, Any]]:
    scored: List[Dict[str, Any]] = []
    for row in desirable_subjects(subjects):
        best = subject_elite_scarcity(
            row, easy_probability=easy_probability, elite_probability=elite_probability
        )
        if best is None:
            continue
        scored.append(
            {
                "subject_key": str(row.get("subject_key")),
                "subject_name": row.get("subject_name"),
                "subject_demand": round(_as_float(row.get("subject_demand")) or 0.0, 2),
                "elite_scarcity": best["scarcity"],
                "driving_card": best,
            }
        )
    return scored


def compute_m_star_m1(
    subjects: Sequence[Mapping[str, Any]],
    *,
    slot_weights: Sequence[float] = M_STAR_SLOT_WEIGHTS,
    easy_probability: float = EASY_PROBABILITY,
    elite_probability: float = ELITE_PROBABILITY,
) -> Optional[Dict[str, Any]]:
    """M1 - elite scarcity of the top distinct subjects BY SUBJECT DEMAND.

        M1 = 0.50*scarcity_top1 + 0.30*scarcity_top2 + 0.20*scarcity_top3

    Subjects are ranked by demand (selection/prioritization - allowed), and the
    scarcity values are NOT scaled by demand (magnitude - forbidden). Missing
    slots renormalize over the available slots, never insert zero.
    """
    scored = _scored_subjects(
        subjects, easy_probability=easy_probability, elite_probability=elite_probability
    )
    if not scored:
        return None

    ranked = _rank_by_demand(scored)[: len(slot_weights)]
    raw_weights = list(slot_weights)[: len(ranked)]
    total = sum(raw_weights)
    if total <= 0:
        return None
    effective = [w / total for w in raw_weights]
    value = sum(row["elite_scarcity"] * weight for row, weight in zip(ranked, effective))

    return {
        "value": _clamp(value),
        "version": M_STAR_VERSION,
        "method": "top_demand_subject_elite_scarcity",
        "slot_weights": list(slot_weights),
        "effective_slot_weights": [round(w, 6) for w in effective],
        "anchors": {"easy_probability": easy_probability, "elite_probability": elite_probability},
        "weights_label": "Reasoned defaults, not fitted.",
        "distinct_subject_count": len(scored),
        "top_subjects": [
            {**row, "slot_weight": round(weight, 6)} for row, weight in zip(ranked, effective)
        ],
    }


def compute_m_star_m2(
    subjects: Sequence[Mapping[str, Any]],
    *,
    easy_probability: float = EASY_PROBABILITY,
    elite_probability: float = ELITE_PROBABILITY,
) -> Optional[Dict[str, Any]]:
    """M2 - desirability-SHARE-weighted elite scarcity.

        M2 = sum(q_s * subject_elite_scarcity_s)

    ``q_s`` sums to 1, so this uses normalized demand shares without
    multiplying absolute desirability a second time.
    """
    scored = _scored_subjects(
        subjects, easy_probability=easy_probability, elite_probability=elite_probability
    )
    if not scored:
        return None

    by_key = {str(row.get("subject_key")): row for row in subjects}
    present = [by_key[row["subject_key"]] for row in scored if row["subject_key"] in by_key]
    shares = demand_shares(present)
    if not shares:
        return None
    # Renormalize across subjects that actually carry modeled pull data, so a
    # subject with no pull model does not silently contribute zero scarcity.
    covered_total = sum(shares.get(row["subject_key"], 0.0) for row in scored)
    if covered_total <= 0:
        return None

    value = 0.0
    detail: List[Dict[str, Any]] = []
    for row in scored:
        share = shares.get(row["subject_key"], 0.0) / covered_total
        value += share * row["elite_scarcity"]
        detail.append({**row, "demand_share": round(share, 6),
                       "contribution": round(share * row["elite_scarcity"], 6)})

    return {
        "value": _clamp(value),
        "version": M_STAR_VERSION,
        "method": "demand_share_weighted_elite_scarcity",
        "anchors": {"easy_probability": easy_probability, "elite_probability": elite_probability},
        "weights_label": "Normalized demand shares; absolute desirability never re-applied.",
        "distinct_subject_count": len(scored),
        "top_subjects": sorted(detail, key=lambda item: -item["contribution"])[:5],
    }


# ---------------------------------------------------------------------------
# A* / M* complementarity
# ---------------------------------------------------------------------------

def complement_error(a_star: Any, m_star: Any) -> Optional[float]:
    """``|A* + M* - 1|``.

    If A* and M* are near-exact complements then an equal additive blend
    ``alpha*A* + (1-alpha)*M*`` collapses toward a constant and is
    mathematically uninformative. See ``f3_degeneracy_note``.
    """
    a = _as_float(a_star)
    m = _as_float(m_star)
    if a is None or m is None:
        return None
    return abs(a + m - 1.0)


def f3_degeneracy_note(alpha: float) -> str:
    """Why F3 is degenerate under exact complementarity.

    If ``M* = 1 - A*`` exactly then

        F3 = D * (alpha*A* + (1-alpha)*(1 - A*))
           = D * ((2*alpha - 1)*A* + (1 - alpha))

    At alpha = 0.50 the A* term vanishes entirely and F3 = 0.5 * D - i.e. a
    rescaled Roster baseline carrying NO structural information whatsoever.
    """
    slope = 2.0 * alpha - 1.0
    if abs(slope) < 1e-12:
        return (
            "DEGENERATE under exact complementarity: the A* term cancels and "
            "F3 = (1-alpha)*D, a rescaled D with zero structural content."
        )
    return (
        f"Under exact complementarity F3 = D*({slope:+.2f}*A* + {1-alpha:.2f}); "
        f"structural content is scaled by |2*alpha-1| = {abs(slope):.2f}."
    )


# ---------------------------------------------------------------------------
# Factorized candidate formulas
# ---------------------------------------------------------------------------

def compute_factorized_candidates(
    *,
    d: Any,
    a_star: Any,
    m_star: Any,
) -> Dict[str, Optional[float]]:
    """All factorized candidates on [0,1]. None when any input is missing.

    Every formula has the shape ``D x structure`` so desirability enters exactly
    once. F6 (= D alone) is the mandatory simplicity benchmark: a factorized
    candidate must beat it to justify any added complexity.
    """
    d_value = _as_float(d)
    a_value = _as_float(a_star)
    m_value = _as_float(m_star)
    if d_value is None or a_value is None or m_value is None:
        return {key: None for key in FACTORIZED_CANDIDATE_KEYS}

    d_value = _clamp(d_value)
    a_value = _clamp(a_value)
    m_value = _clamp(m_value)

    candidates: Dict[str, Optional[float]] = {
        # Balanced: rewards having BOTH attainable favorites and elite chases;
        # collapses to 0 if either is absent.
        "F1_balanced_multiplicative": d_value * math.sqrt(a_value * m_value),
        # Either-path: a desirable set may succeed through accessibility, elite
        # chases, or both.
        "F2_either_path_union": d_value * (1.0 - (1.0 - a_value) * (1.0 - m_value)),
        # Market chase factorization.
        "F4_market_chase": d_value * m_value,
        # Accessible roster factorization.
        "F5_accessible_roster": d_value * a_value,
        # Mandatory simplicity benchmark.
        "F6_roster_baseline": d_value,
    }
    for alpha in F3_ALPHAS:
        candidates[f"F3_alpha_{alpha:.2f}"] = d_value * (alpha * a_value + (1.0 - alpha) * m_value)
    return {key: candidates[key] for key in FACTORIZED_CANDIDATE_KEYS}


def to_display_scale(value: Any) -> Optional[float]:
    """Scale a raw [0,1] candidate to 0-100 for display ONLY.

    Raw values are preserved in the report; this is applied after every
    calculation, never before.
    """
    parsed = _as_float(value)
    return None if parsed is None else round(100.0 * _clamp(parsed), 4)


def factorized_payload(
    *,
    d_label: str,
    d: Any,
    a_star: Any,
    m_star: Any,
) -> Dict[str, Any]:
    raw = compute_factorized_candidates(d=d, a_star=a_star, m_star=m_star)
    return {
        "version": FACTORIZED_OPENING_APPEAL_VERSION,
        "d_label": d_label,
        "d": _as_float(d),
        "a_star": _as_float(a_star),
        "m_star": _as_float(m_star),
        "complement_error": complement_error(a_star, m_star),
        "candidates_raw": raw,
        "candidates_display": {key: to_display_scale(value) for key, value in raw.items()},
        "available": all(value is not None for value in raw.values()),
        "inputsLabel": "modeledPullScarcity (config-derived pack model), never observed pull data.",
        "excludedInputs": [
            "market_price", "set_value", "expected_value", "profit",
            "treatment_prestige", "any_market_outcome",
        ],
        "researchOnly": True,
    }
