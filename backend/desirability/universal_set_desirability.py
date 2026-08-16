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
    UNIVERSAL_SET_DESIRABILITY_V4_VERSION,
    CONTEXTUAL_CHASE_PRIORITY_VERSION,
    renormalize_weights,
)

CONTEXTUAL_CHASE_MIN_CARD_SHARE = 0.01
CONTEXTUAL_CHASE_MAX_UNRESOLVED_EV_SHARE = 1.0  # audit first; finalized after cohort distribution
CONTEXTUAL_CHASE_DENOMINATOR = "all_positive_modeled_card_ev"


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


def build_contextual_chase_subjects(
    subject_rollups: Sequence[Mapping[str, Any]],
    card_evidence: Sequence[Mapping[str, Any]],
    *,
    min_subject_share: float = CONTEXTUAL_CHASE_MIN_CARD_SHARE,
    minimum_subject_fallback: int = 0,
    denominator: str = CONTEXTUAL_CHASE_DENOMINATOR,
    max_unresolved_ev_share: float = CONTEXTUAL_CHASE_MAX_UNRESOLVED_EV_SHARE,
) -> Dict[str, Any]:
    """Aggregate the exact run's card evidence, then classify Pokemon subjects.

    EV answers only whether a canonical Pokemon meaningfully represents this
    set. Membership is evaluated on the *aggregated subject share*, never on an
    individual printing. The strength component later reorders qualifying
    subjects by Pokemon desirability, so EV cannot assign the 50/30/20 slots.
    """
    if denominator not in {"all_positive_modeled_card_ev", "mapped_pokemon_positive_ev"}:
        raise ValueError(f"unsupported contextual chase denominator: {denominator}")
    eligible = eligible_subject_rollups(subject_rollups)
    by_ref: Dict[int, Dict[str, Any]] = {}
    for row in eligible:
        try:
            by_ref[int(row.get("pokemon_reference_id"))] = dict(row)
        except (TypeError, ValueError):
            continue

    normalized: List[Tuple[Mapping[str, Any], Optional[int], float]] = []
    for card in card_evidence:
        try:
            reference_id = int(card.get("pokemon_reference_id"))
        except (TypeError, ValueError):
            reference_id = None
        ev = _as_float(card.get("ev_contribution"))
        if ev is None or ev <= 0:
            continue
        normalized.append((card, reference_id, ev))
    normalized.sort(
        key=lambda item: (item[2], _as_float(item[0].get("market_value")) or 0.0),
        reverse=True,
    )
    total_ev = sum(item[2] for item in normalized)
    mapped_eligible_ev = non_pokemon_ev = unresolved_ev = ineligible_pokemon_ev = 0.0
    mapped_count = non_pokemon_count = unresolved_count = ineligible_pokemon_count = 0
    aggregated: Dict[int, Dict[str, Any]] = {}
    for rank, (card, reference_id, ev) in enumerate(normalized, start=1):
        mapping_status = str(card.get("mapping_status") or "")
        is_hit_eligible = card.get("is_hit_eligible") is not False
        if mapping_status == "intentional_non_pokemon":
            non_pokemon_ev += ev
            non_pokemon_count += 1
            continue
        if reference_id is None or mapping_status == "unresolved":
            unresolved_ev += ev
            unresolved_count += 1
            continue
        if reference_id not in by_ref or not is_hit_eligible:
            ineligible_pokemon_ev += ev
            ineligible_pokemon_count += 1
            continue
        mapped_eligible_ev += ev
        mapped_count += 1
        current = aggregated.setdefault(reference_id, {
            **by_ref[reference_id],
            "subject_ev_contribution": 0.0,
            "subject_ev_share": 0.0,
            "eligible_card_count": 0,
            "representative_chase_card": None,
        })
        current["subject_ev_contribution"] += ev
        current["eligible_card_count"] += 1
        if current["representative_chase_card"] is None:
            current["representative_chase_card"] = {
                "card_id": card.get("card_id"),
                "card_name": card.get("card_name"),
                "rarity": card.get("rarity") or card.get("rarity_bucket"),
                "rarity_bucket": card.get("rarity_bucket"),
                "market_value": _as_float(card.get("market_value")),
                "modeled_probability": _as_float(card.get("modeled_probability")),
                "ev_contribution": _round(ev),
                "ev_share": None,
                "card_chase_rank": rank,
            }

    denominator_ev = total_ev if denominator == "all_positive_modeled_card_ev" else mapped_eligible_ev
    contextual = list(aggregated.values())
    for row in contextual:
        row["subject_ev_share"] = (
            row["subject_ev_contribution"] / denominator_ev if denominator_ev > 0 else 0.0
        )
    contextual.sort(
        key=lambda row: (
            row["subject_ev_contribution"],
            _as_float(row.get("max_desirability_score")) or 0.0,
        ),
        reverse=True,
    )
    for rank, row in enumerate(contextual, start=1):
        row["chase_priority_rank"] = rank
        row["role"] = "meaningful_chase" if row["subject_ev_share"] >= min_subject_share else "supporting_roster"
        row["subject_ev_contribution"] = _round(row["subject_ev_contribution"])
        row["subject_ev_share"] = _round(row["subject_ev_share"])
        representative = row.get("representative_chase_card") or {}
        representative["ev_share"] = _round(
            (representative.get("ev_contribution") or 0.0) / denominator_ev
        ) if denominator_ev > 0 else None

    if minimum_subject_fallback > 0:
        for row in contextual[:minimum_subject_fallback]:
            row["role"] = "meaningful_chase"

    evidenced_refs = set(aggregated)
    supporting = []
    for row in eligible:
        try:
            reference_id = int(row.get("pokemon_reference_id"))
        except (TypeError, ValueError):
            continue
        if reference_id not in evidenced_refs:
            supporting.append({**row, "role": "supporting_roster", "chase_priority_rank": None,
                               "representative_chase_card": None})
    meaningful_subjects = [row for row in contextual if row["role"] == "meaningful_chase"]
    unresolved_share = unresolved_ev / total_ev if total_ev > 0 else 0.0
    evidence_status = "available"
    evidence_reason = None
    if not normalized:
        evidence_status, evidence_reason = "unavailable", "missing_canonical_chase_evidence"
    elif unresolved_share > max_unresolved_ev_share:
        evidence_status, evidence_reason = "unavailable", "insufficient_canonical_mapping_coverage"
    elif not meaningful_subjects:
        evidence_status, evidence_reason = "unavailable", "no_meaningful_chase_subjects"
    diagnostics = {
        "denominator": denominator,
        "denominator_ev": _round(denominator_ev),
        "total_positive_modeled_card_ev": _round(total_ev),
        "mapped_eligible_pokemon_ev": _round(mapped_eligible_ev),
        "intentional_non_pokemon_ev": _round(non_pokemon_ev),
        "resolved_ineligible_pokemon_ev": _round(ineligible_pokemon_ev),
        "unresolved_ev": _round(unresolved_ev),
        "mapped_pokemon_ev_share": _round(mapped_eligible_ev / total_ev) if total_ev else 0.0,
        "unresolved_ev_share": _round(unresolved_share),
        "positive_ev_card_count": len(normalized),
        "mapped_eligible_pokemon_card_count": mapped_count,
        "intentional_non_pokemon_card_count": non_pokemon_count,
        "resolved_ineligible_pokemon_card_count": ineligible_pokemon_count,
        "unresolved_card_count": unresolved_count,
        "max_unresolved_ev_share": max_unresolved_ev_share,
    }
    return {
        "meaningful_subjects": meaningful_subjects,
        "all_subjects": meaningful_subjects + [row for row in contextual if row["role"] != "meaningful_chase"] + supporting,
        "total_card_ev": _round(total_ev),
        "priority_version": CONTEXTUAL_CHASE_PRIORITY_VERSION,
        "evidence_status": evidence_status,
        "evidence_reason": evidence_reason,
        "evidence_diagnostics": diagnostics,
    }


def compute_universal_set_desirability_v4(
    subject_rollups: Sequence[Mapping[str, Any]],
    card_evidence: Sequence[Mapping[str, Any]],
    *,
    min_subject_share: float = CONTEXTUAL_CHASE_MIN_CARD_SHARE,
    minimum_subject_fallback: int = 0,
    denominator: str = CONTEXTUAL_CHASE_DENOMINATOR,
    max_unresolved_ev_share: float = CONTEXTUAL_CHASE_MAX_UNRESOLVED_EV_SHARE,
) -> Dict[str, Any]:
    """Contextual V4; V3 entry points remain untouched and reproducible."""
    context = build_contextual_chase_subjects(
        subject_rollups, card_evidence,
        min_subject_share=min_subject_share,
        minimum_subject_fallback=minimum_subject_fallback,
        denominator=denominator,
        max_unresolved_ev_share=max_unresolved_ev_share,
    )
    if context["evidence_status"] != "available":
        return {
            "score": None, "version": UNIVERSAL_SET_DESIRABILITY_V4_VERSION,
            "eligibility_policy_version": UNIVERSAL_ELIGIBILITY_POLICY_VERSION,
            "status": "unavailable", "reason": context.get("evidence_reason"),
            "chase_priority_version": CONTEXTUAL_CHASE_PRIORITY_VERSION,
            "top_subjects": [], "modeled_subjects": context["all_subjects"],
            "chase_evidence": context.get("evidence_diagnostics"),
        }
    meaningful = sorted(
        context["meaningful_subjects"],
        key=lambda row: (
            -(_as_float(row.get("max_desirability_score")) or 0.0),
            -(_as_float(row.get("subject_ev_contribution")) or 0.0),
            _as_int(row.get("pokemon_reference_id"), 2**31 - 1),
        ),
    )
    strength, strength_inputs = compute_chase_subject_strength_v3(meaningful)
    depth, depth_inputs = compute_chase_subject_depth_v3(meaningful)
    all_eligible = eligible_subject_rollups(subject_rollups)
    coverage_raw, coverage_inputs = compute_favorite_hit_coverage_raw(all_eligible)
    coverage = normalize_favorite_hit_coverage(coverage_raw)
    components = {"contextual_chase_subject_strength": strength,
                  "contextual_chase_subject_depth": depth,
                  "supporting_roster_breadth": coverage}
    legacy_weights = renormalize_weights(UNIVERSAL_COMPONENT_WEIGHTS)
    weights = {
        "contextual_chase_subject_strength": legacy_weights["chase_subject_strength"],
        "contextual_chase_subject_depth": legacy_weights["chase_subject_depth"],
        "supporting_roster_breadth": legacy_weights["favorite_hit_coverage"],
    }
    score = sum(components[key] * weights[key] for key in components)
    top_refs = {row.get("pokemon_reference_id") for row in strength_inputs.get("top_subjects", [])}
    for row in context["all_subjects"]:
        row["set_roster_position"] = next((i for i, item in enumerate(context["all_subjects"], 1) if item is row), None)
        row["strength_slot"] = row.get("pokemon_reference_id") in top_refs
    return {
        "score": _round(_bounded(score)), "version": UNIVERSAL_SET_DESIRABILITY_V4_VERSION,
        "status": "available", "eligibility_policy_version": UNIVERSAL_ELIGIBILITY_POLICY_VERSION,
        "chase_priority_version": CONTEXTUAL_CHASE_PRIORITY_VERSION,
        "components": components, "component_weights": {k: round(v, 6) for k, v in weights.items()},
        "weights_label": "V3 component weights retained; card EV establishes subject priority only.",
        "favorite_hit_coverage_raw": coverage_raw,
        "distinct_eligible_subject_count": len(all_eligible),
        "component_inputs": {"contextual_chase_subject_strength": strength_inputs,
                             "contextual_chase_subject_depth": depth_inputs,
                             "supporting_roster_breadth": coverage_inputs},
        "top_subjects": strength_inputs.get("top_subjects", []),
        "modeled_subjects": context["all_subjects"],
        "chase_evidence": {**context["evidence_diagnostics"],
                           "same_canonical_distribution_required": True},
        "direct_score_inputs": ["pokemon_desirability", "component_transforms", "component_weights"],
        "chase_priority_inputs": ["card_ev_contribution", "subject_ev_share", "authoritative_run_identity", "canonical_card_to_pokemon_mapping"],
        "directly_excluded_inputs": ["raw_market_price", "pull_probability", "ev_contribution"],
        "priority_input_note": "EV contribution identifies meaningful chase representation; it is not multiplied into Pokemon desirability or directly added to the roster score.",
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
