"""Universal Set Desirability v3 and the two independent coverage axes.

Universal Set Desirability is a **price-independent, Treatment-free,
simulation-free** score computed identically for every adequately-mapped set:

    Universal Set Desirability =
        (30/90) * Chase Subject Strength
      + (25/90) * Chase Subject Depth
      + (35/90) * Favorite Hit Coverage

All weights come from :mod:`backend.desirability.scoring_config` and are
reasoned defaults, not empirically fitted values.

Inputs are the *distinct-subject rollups* already produced by the shipped V2
pipeline (``set_components.collapse_subject_rollups`` or the persisted
``subject_rollups_json`` on ``pokemon_set_desirability_component_scores``).
Each rollup is one distinct Pokemon subject with its best (max) Pure Demand
score, so one Pokemon with many cards can never occupy multiple slots.

What deliberately does NOT enter this module: market price, set value,
Treatment Score, Card Appeal, scarcity, pull probabilities, special-pack
mechanics, or any simulation output. Rarity appears only as the universal
hit/subject *eligibility classification* (which cards represent meaningful
collectible subjects), never as a numeric multiplier.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from backend.desirability.rarity_buckets import HIT_BUCKETS
from backend.desirability.scoring_config import (
    CHASE_STRENGTH_SLOT_WEIGHTS,
    DEPTH_EFFECTIVE_COUNT_CAP,
    FAVORITE_COVERAGE_DEMAND_BASELINE,
    FAVORITE_COVERAGE_NORMALIZATION_VERSION,
    FAVORITE_COVERAGE_SATURATION_K,
    UNIVERSAL_COMPONENT_WEIGHTS,
    UNIVERSAL_ELIGIBILITY_POLICY_VERSION,
    UNIVERSAL_SET_DESIRABILITY_VERSION,
    renormalize_weights,
)


# ---------------------------------------------------------------------------
# Coverage axes (Phase 1) - two independent states, never one generic flag
# ---------------------------------------------------------------------------

COVERAGE_FULL = "full"
COVERAGE_PARTIAL = "partial"
COVERAGE_UNAVAILABLE = "unavailable"

# desirabilityCoverage reason codes
MISSING_CHECKLIST = "missing_checklist"
MISSING_SUBJECT_LINKS = "missing_subject_links"
INSUFFICIENT_LINK_COVERAGE = "insufficient_link_coverage"
NO_ELIGIBLE_POKEMON_SUBJECTS = "no_eligible_pokemon_subjects"
MISSING_DEMAND_SCORES = "missing_demand_scores"
DATA_QUALITY_BLOCK = "data_quality_block"

# simulationCoverage reason codes
MISSING_PULL_RATES = "missing_pull_rates"
MISSING_PACK_SCHEMA = "missing_pack_schema"
INCOMPLETE_SUBSET_BLENDING = "incomplete_subset_blending"
SIMULATION_NOT_VALIDATED = "simulation_not_validated"
MISSING_FINANCIAL_OUTPUTS = "missing_financial_outputs"

# Minimum linked/scored share of hit-eligible cards for `full` desirability
# coverage, and the floor below which coverage is `unavailable`. Reasoned
# defaults, reported with every coverage payload.
FULL_COVERAGE_MIN_LINKED_SHARE = 0.90
PARTIAL_COVERAGE_MIN_LINKED_SHARE = 0.50


def _as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def assess_desirability_coverage(
    *,
    canonical_card_count: Any,
    hit_eligible_card_count: Any,
    scored_hit_eligible_card_count: Any,
    unique_subject_count: Any,
    unmatched_pokemon_hit_count: Any = 0,
    true_missing_link_count: Any = 0,
) -> Dict[str, Any]:
    """Classify a set's desirability coverage as full / partial / unavailable."""
    canonical = _as_int(canonical_card_count)
    eligible = _as_int(hit_eligible_card_count)
    scored = _as_int(scored_hit_eligible_card_count)
    subjects = _as_int(unique_subject_count)
    missing_links = _as_int(unmatched_pokemon_hit_count) + _as_int(true_missing_link_count)

    reasons: List[str] = []
    if canonical <= 0:
        reasons.append(MISSING_CHECKLIST)
    if eligible > 0 and subjects <= 0:
        reasons.append(
            MISSING_SUBJECT_LINKS if missing_links >= eligible else NO_ELIGIBLE_POKEMON_SUBJECTS
        )
    if canonical > 0 and eligible <= 0:
        reasons.append(NO_ELIGIBLE_POKEMON_SUBJECTS)

    scored_share = (scored / eligible) if eligible > 0 else 0.0
    if eligible > 0 and subjects > 0:
        if scored_share < PARTIAL_COVERAGE_MIN_LINKED_SHARE:
            reasons.append(INSUFFICIENT_LINK_COVERAGE)
        elif scored_share < FULL_COVERAGE_MIN_LINKED_SHARE:
            reasons.append(INSUFFICIENT_LINK_COVERAGE)
        if scored <= 0:
            reasons.append(MISSING_DEMAND_SCORES)

    if canonical <= 0 or eligible <= 0 or subjects <= 0 or scored <= 0:
        status = COVERAGE_UNAVAILABLE
    elif scored_share >= FULL_COVERAGE_MIN_LINKED_SHARE:
        status = COVERAGE_FULL
    elif scored_share >= PARTIAL_COVERAGE_MIN_LINKED_SHARE:
        status = COVERAGE_PARTIAL
    else:
        status = COVERAGE_UNAVAILABLE

    return {
        "status": status,
        "reasons": sorted(set(reasons)),
        "scoredHitEligibleShare": round(scored_share, 4),
        "thresholds": {
            "full_min_scored_share": FULL_COVERAGE_MIN_LINKED_SHARE,
            "partial_min_scored_share": PARTIAL_COVERAGE_MIN_LINKED_SHARE,
            "note": "Reasoned defaults, not empirically optimized.",
        },
    }


def assess_simulation_coverage(row: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Classify simulation coverage from a set's latest simulation summary row.

    ``row`` is the set's ``explore_rip_statistics_latest`` row (or equivalent
    summary mapping); ``None`` means no simulation output exists for the set.
    """
    if not isinstance(row, Mapping):
        return {
            "status": COVERAGE_UNAVAILABLE,
            "reasons": [MISSING_FINANCIAL_OUTPUTS, MISSING_PULL_RATES],
        }

    reasons: List[str] = []
    pillars_present = all(
        _as_float(row.get(key)) is not None
        for key in ("profit_score", "safety_score", "stability_score")
    )
    if not pillars_present:
        reasons.append(MISSING_FINANCIAL_OUTPUTS)
    if _as_float(row.get("pack_cost")) is None:
        reasons.append(MISSING_PACK_SCHEMA)
    if _as_float(row.get("mean_value")) is None and _as_float(row.get("mean_value_to_cost_ratio")) is None:
        reasons.append(MISSING_FINANCIAL_OUTPUTS)

    if not reasons:
        status = COVERAGE_FULL
    elif pillars_present:
        status = COVERAGE_PARTIAL
    else:
        status = COVERAGE_UNAVAILABLE
    return {"status": status, "reasons": sorted(set(reasons))}


# ---------------------------------------------------------------------------
# Distinct-subject selection (Phase 4 eligibility, applied to rollups)
# ---------------------------------------------------------------------------

def eligible_subject_rollups(subject_rollups: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Distinct Pokemon subjects backed by at least one hit-eligible card.

    Rollups are already collapsed by ``pokemon_reference_id`` (one row per
    subject), so duplicates/variants cannot inflate a subject. Rarity is used
    only as the eligibility classification (``universal_desirability_eligibility_v2``,
    which wraps the shipped, price-independent hit-bucket policy), never as a
    score input.
    """
    eligible: List[Dict[str, Any]] = []
    seen_keys: set = set()
    for row in subject_rollups:
        if not isinstance(row, Mapping):
            continue
        subject_key = str(row.get("subject_key") or "")
        if not subject_key or subject_key in seen_keys:
            continue
        buckets = row.get("rarity_buckets_present")
        buckets = buckets if isinstance(buckets, list) else [row.get("best_rarity_bucket")]
        if not any(str(bucket) in HIT_BUCKETS for bucket in buckets if bucket):
            continue
        if _as_float(row.get("max_desirability_score")) is None:
            continue
        seen_keys.add(subject_key)
        eligible.append(dict(row))
    eligible.sort(
        key=lambda row: (
            _as_float(row.get("max_desirability_score")) or -1.0,
            str(row.get("subject_name") or ""),
        ),
        reverse=True,
    )
    return eligible


def _subject_json(row: Mapping[str, Any], **extra: Any) -> Dict[str, Any]:
    payload = {
        "subject_name": row.get("subject_name"),
        "pokemon_reference_id": row.get("pokemon_reference_id"),
        "subject_demand": _as_float(row.get("max_desirability_score")),
        "card_count": row.get("card_count"),
        "representative_card_name": row.get("representative_card_name"),
        "best_rarity_bucket": row.get("best_rarity_bucket"),
    }
    payload.update(extra)
    return payload


# ---------------------------------------------------------------------------
# Component 1 - Chase Subject Strength
# ---------------------------------------------------------------------------

def compute_chase_subject_strength_v3(
    subjects: Sequence[Mapping[str, Any]],
) -> Tuple[float, Dict[str, Any]]:
    """0.50/0.30/0.20 over the top-3 *distinct* subjects by Pure Demand.

    Missing slots renormalize the available slot weights (never insert zero),
    so a legitimate one-chase set is scored on the strength it has instead of
    being penalized for slots that cannot exist.
    """
    ranked = list(subjects)[: len(CHASE_STRENGTH_SLOT_WEIGHTS)]
    if not ranked:
        return 0.0, {
            "slot_weights": list(CHASE_STRENGTH_SLOT_WEIGHTS),
            "missing_slot_policy": "renormalize_available_slot_weights",
            "top_subjects": [],
        }
    raw_weights = CHASE_STRENGTH_SLOT_WEIGHTS[: len(ranked)]
    total = sum(raw_weights)
    weights = [weight / total for weight in raw_weights]
    score = sum(
        (_as_float(row.get("max_desirability_score")) or 0.0) * weight
        for row, weight in zip(ranked, weights)
    )
    return _round(_bounded(score)), {
        "slot_weights": list(CHASE_STRENGTH_SLOT_WEIGHTS),
        "effective_slot_weights": [round(weight, 6) for weight in weights],
        "missing_slot_policy": "renormalize_available_slot_weights",
        "top_subjects": [
            _subject_json(row, slot_weight=round(weight, 6),
                          weighted_contribution=_round((_as_float(row.get("max_desirability_score")) or 0.0) * weight))
            for row, weight in zip(ranked, weights)
        ],
    }


# ---------------------------------------------------------------------------
# Component 2 - Chase Subject Depth (HHI / effective subject count)
# ---------------------------------------------------------------------------

def compute_chase_subject_depth_v3(
    subjects: Sequence[Mapping[str, Any]],
    *,
    effective_count_cap: float = DEPTH_EFFECTIVE_COUNT_CAP,
) -> Tuple[float, Dict[str, Any]]:
    """Concentration of meaningful demand across distinct subjects.

    contribution_i = max(subject_demand_i - baseline, 0)
    share_i = contribution_i / sum(contribution)
    HHI = sum(share_i^2);  effective_subject_count = 1 / HHI
    depth = 100 * (min(effective_count, cap) - 1) / (cap - 1)

    The demand baseline (50) mirrors Favorite Hit Coverage's convention:
    depth measures how many *desirable* subjects carry the set, so a set of
    uniformly unloved subjects scores 0 rather than "deep". Reasoned default.
    """
    contributions = [
        (row, max((_as_float(row.get("max_desirability_score")) or 0.0) - FAVORITE_COVERAGE_DEMAND_BASELINE, 0.0))
        for row in subjects
    ]
    contributing = [(row, value) for row, value in contributions if value > 0.0]
    total = sum(value for _, value in contributing)

    if total <= 0.0 or not contributing:
        return 0.0, {
            "method": "hhi_effective_subject_count",
            "demand_baseline": FAVORITE_COVERAGE_DEMAND_BASELINE,
            "effective_count_cap": effective_count_cap,
            "contributing_subject_count": 0,
            "effective_subject_count": 0.0,
            "hhi": None,
            "top1_share": None,
            "top3_share": None,
            "distinct_eligible_subject_count": len(list(subjects)),
        }

    shares = sorted((value / total for _, value in contributing), reverse=True)
    hhi = sum(share * share for share in shares)
    effective_count = 1.0 / hhi if hhi > 0 else 0.0
    depth = 100.0 * (min(effective_count, effective_count_cap) - 1.0) / (effective_count_cap - 1.0)

    return _round(_bounded(depth)), {
        "method": "hhi_effective_subject_count",
        "demand_baseline": FAVORITE_COVERAGE_DEMAND_BASELINE,
        "effective_count_cap": effective_count_cap,
        "contributing_subject_count": len(contributing),
        "effective_subject_count": _round(effective_count),
        "hhi": _round(hhi),
        "top1_share": _round(shares[0]),
        "top3_share": _round(sum(shares[:3])),
        "distinct_eligible_subject_count": len(list(subjects)),
        "counted_subjects": [
            _subject_json(row, contribution=_round(value), share=_round(value / total))
            for row, value in sorted(contributing, key=lambda item: item[1], reverse=True)[:10]
        ],
    }


# ---------------------------------------------------------------------------
# Component 3 - Favorite Hit Coverage (NOT pull accessibility)
# ---------------------------------------------------------------------------

def compute_favorite_hit_coverage_raw(
    subjects: Sequence[Mapping[str, Any]],
) -> Tuple[float, Dict[str, Any]]:
    """Checklist-based coverage of desirable subjects with diminishing returns.

    subject_contribution_i = max((subject_demand_i - 50) / 50, 0)
    raw_coverage = sum(sqrt(subject_contribution_i))

    One many-card subject cannot dominate (subjects are distinct rollups), and
    sqrt keeps large modern checklists from winning on size alone. This is
    checklist *presence*, deliberately not pull probability - pull access
    lives in Simulation Opening Details.
    """
    contributions = []
    above_60 = above_75 = above_90 = 0
    for row in subjects:
        demand = _as_float(row.get("max_desirability_score")) or 0.0
        if demand > 60:
            above_60 += 1
        if demand > 75:
            above_75 += 1
        if demand > 90:
            above_90 += 1
        contribution = max((demand - FAVORITE_COVERAGE_DEMAND_BASELINE) / FAVORITE_COVERAGE_DEMAND_BASELINE, 0.0)
        if contribution > 0:
            contributions.append((row, contribution))
    raw = sum(math.sqrt(value) for _, value in contributions)
    return _round(raw), {
        "formula": "sum(sqrt(max((subject_demand - 50) / 50, 0)))",
        "demand_baseline": FAVORITE_COVERAGE_DEMAND_BASELINE,
        "contributing_subject_count": len(contributions),
        "subjects_above_60": above_60,
        "subjects_above_75": above_75,
        "subjects_above_90": above_90,
        "top_contributors": [
            _subject_json(row, contribution=_round(value), sqrt_contribution=_round(math.sqrt(value)))
            for row, value in sorted(contributions, key=lambda item: item[1], reverse=True)[:10]
        ],
    }


def normalize_favorite_hit_coverage(raw: float, *, saturation_k: float = FAVORITE_COVERAGE_SATURATION_K) -> float:
    """Fixed saturated transform to 0-100: ``100 * (1 - exp(-raw / k))``.

    A fixed transform (rather than cohort percentile scaling) keeps every
    set's score independent of which other sets happen to be in the cohort,
    so adding or removing a set can never move another set's score. k is a
    reasoned default; the cohort-robust variant is kept for diagnostics only.
    """
    if raw <= 0:
        return 0.0
    return _round(_bounded(100.0 * (1.0 - math.exp(-float(raw) / float(saturation_k)))))


def cohort_robust_normalization(raw_values: Sequence[Optional[float]]) -> Dict[str, Any]:
    """Diagnostic cohort normalization (p05->0, p95->100, clamped)."""
    values = sorted(float(value) for value in raw_values if _as_float(value) is not None)
    if not values:
        return {"p05": None, "p95": None, "version": "favorite_hit_coverage_cohort_p05_p95_v1"}
    p05 = _percentile(values, 0.05)
    p95 = _percentile(values, 0.95)
    return {"p05": _round(p05), "p95": _round(p95), "version": "favorite_hit_coverage_cohort_p05_p95_v1"}


def apply_cohort_robust_normalization(raw: Optional[float], cohort: Mapping[str, Any]) -> Optional[float]:
    value = _as_float(raw)
    p05 = _as_float(cohort.get("p05"))
    p95 = _as_float(cohort.get("p95"))
    if value is None or p05 is None or p95 is None or p95 <= p05:
        return None
    return _round(_bounded(100.0 * (value - p05) / (p95 - p05)))


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    index = fraction * (len(sorted_values) - 1)
    low = int(math.floor(index))
    high = int(math.ceil(index))
    if low == high:
        return sorted_values[low]
    weight = index - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


# ---------------------------------------------------------------------------
# Universal Set Desirability composite (Phase 6)
# ---------------------------------------------------------------------------

def compute_universal_set_desirability(
    subject_rollups: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Compute the v3 universal score for one set from its subject rollups."""
    subjects = eligible_subject_rollups(subject_rollups)

    strength, strength_inputs = compute_chase_subject_strength_v3(subjects)
    depth, depth_inputs = compute_chase_subject_depth_v3(subjects)
    coverage_raw, coverage_inputs = compute_favorite_hit_coverage_raw(subjects)
    coverage = normalize_favorite_hit_coverage(coverage_raw)

    components = {
        "chase_subject_strength": strength,
        "chase_subject_depth": depth,
        "favorite_hit_coverage": coverage,
    }
    weights = renormalize_weights(UNIVERSAL_COMPONENT_WEIGHTS)
    score = sum(components[key] * weight for key, weight in weights.items())

    return {
        "score": _round(_bounded(score)),
        "version": UNIVERSAL_SET_DESIRABILITY_VERSION,
        "eligibility_policy_version": UNIVERSAL_ELIGIBILITY_POLICY_VERSION,
        "components": components,
        "component_weights": {key: round(value, 6) for key, value in weights.items()},
        "weights_label": "Reasoned defaults, not empirically fitted values.",
        "favorite_hit_coverage_raw": coverage_raw,
        "favorite_hit_coverage_normalization_version": FAVORITE_COVERAGE_NORMALIZATION_VERSION,
        "distinct_eligible_subject_count": len(subjects),
        "component_inputs": {
            "chase_subject_strength": strength_inputs,
            "chase_subject_depth": depth_inputs,
            "favorite_hit_coverage": coverage_inputs,
        },
        "top_subjects": strength_inputs.get("top_subjects", []),
        "excluded_inputs": [
            "market_price", "set_value", "treatment_score", "card_appeal",
            "scarcity", "pull_probability", "special_pack_mechanics", "simulation_output",
        ],
    }


def rank_universal_scores(rows: List[Dict[str, Any]], *, score_key: str = "score") -> None:
    """Assign all-set rank and percentile in place (rank 1 = highest score)."""
    scored = [row for row in rows if _as_float(row.get(score_key)) is not None]
    scored.sort(key=lambda row: (-(_as_float(row.get(score_key)) or 0.0), str(row.get("set_id") or "")))
    total = len(scored)
    for rank, row in enumerate(scored, start=1):
        row["rank"] = rank
        row["percentile"] = _round(100.0 * (total - rank) / (total - 1)) if total > 1 else 100.0
        row["ranked_set_count"] = total


def _bounded(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _round(value: Any, digits: int = 4) -> float:
    parsed = _as_float(value)
    return round(parsed, digits) if parsed is not None else 0.0
