"""Universal Set Desirability v3 + weighted RIP study runner (READ-ONLY).

Computes, against live data and without writing anything to the database:

- Universal Set Desirability v3 for every set (from the persisted V2
  subject rollups), with the two independent coverage axes and all-set ranks.
- The Phase 7 set-value gate (v3 vs set value, Spearman primary), plus the
  prior shipped-desirability benchmark on the same cohort.
- Phase 9 pillar diagnostics (redundancy matrix, weight sensitivity).
- Phase 10 weighted RIP v3 + the desirability-influence report for the
  full-simulation cohort.
- Phase 11 all-set stress tests and Phase 12 simulation-cohort tests.

Output: a JSON report (default docs/research/universal_set_desirability_v3_report.json)
plus a printed summary. This script never writes to Supabase.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.calculations.utils.rarity_classification import normalize_rarity_key  # noqa: E402
from backend.desirability.scoring_config import (  # noqa: E402
    DEFAULT_RIP_WEIGHTS,
    DEPTH_EFFECTIVE_COUNT_SENSITIVITY_CAPS,
    UNIVERSAL_SET_DESIRABILITY_VERSION,
)
from backend.desirability.set_components import SCORING_VERSION as V2_SCORING_VERSION  # noqa: E402
from backend.desirability.simulation_opening_details import (  # noqa: E402
    compute_simulation_opening_details,
)
from backend.desirability.universal_set_desirability import (  # noqa: E402
    COVERAGE_FULL,
    apply_cohort_robust_normalization,
    assess_desirability_coverage,
    assess_simulation_coverage,
    cohort_robust_normalization,
    compute_chase_subject_depth_v3,
    compute_universal_set_desirability,
    eligible_subject_rollups,
    rank_universal_scores,
)
from backend.desirability.weighted_rip import (  # noqa: E402
    build_desirability_influence_report,
    evaluate_set_value_association,
    pillar_redundancy_matrix,
    spearman,
    weight_sensitivity_report,
)

logger = logging.getLogger(__name__)

SET_VALUE_SCOPE = "standard"
PULL_RATE_MIN_CARD_SHARE = 0.5


# ---------------------------------------------------------------------------
# Supabase helpers (read-only)
# ---------------------------------------------------------------------------

def _client():
    from backend.db.clients.supabase_client import public_read_client

    return public_read_client


def _paged_select(query: Any, *, page_size: int = 1000) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        response = query.range(start, start + page_size - 1).execute()
        page_rows = list(response.data or [])
        rows.extend(page_rows)
        if len(page_rows) < page_size:
            break
        start += page_size
    return rows


def _chunked(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_latest_v2_rows(client) -> Dict[str, Dict[str, Any]]:
    """Latest V2 component row per set (preferring the current scoring version)."""
    rows = _paged_select(
        client.table("pokemon_set_desirability_component_scores")
        .select(
            "id,set_id,set_name,set_canonical_key,scoring_version,hit_policy_version,"
            "composite_scoring_version,set_desirability_score,chase_subject_strength,"
            "chase_subject_depth,accessible_favorite_hits,special_pack_chase_appeal,"
            "hit_eligible_card_count,scored_hit_eligible_card_count,unique_subject_count,"
            "duplicate_subject_count,unmatched_hit_count,subject_rollups_json,"
            "special_pack_summary_json,diagnostics_json,built_at"
        )
        .order("built_at", desc=True)
    )
    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        set_id = str(row.get("set_id") or "")
        if not set_id:
            continue
        current = latest.get(set_id)
        if current is None:
            latest[set_id] = row
            continue
        row_is_current_version = row.get("scoring_version") == V2_SCORING_VERSION
        kept_is_current_version = current.get("scoring_version") == V2_SCORING_VERSION
        if row_is_current_version and not kept_is_current_version:
            latest[set_id] = row
    return latest


def load_sets_and_eras(client) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    sets = {
        str(row["id"]): row
        for row in _paged_select(
            client.table("sets").select("id,name,canonical_key,release_date,era_id")
        )
        if row.get("id")
    }
    eras = {
        str(row["id"]): str(row.get("name") or "")
        for row in _paged_select(client.table("eras").select("id,name"))
        if row.get("id")
    }
    return sets, eras


def load_latest_set_values(client, set_ids: Sequence[str]) -> Dict[str, float]:
    latest: Dict[str, float] = {}
    for chunk in _chunked(sorted(set_ids), 50):
        rows = (
            client.table("pokemon_set_value_daily_history")
            .select("set_id,snapshot_date,set_value")
            .in_("set_id", list(chunk))
            .eq("value_scope", SET_VALUE_SCOPE)
            .order("snapshot_date", desc=True)
            .limit(len(chunk) * 45)
            .execute()
        )
        for row in rows.data or []:
            set_id = str(row.get("set_id") or "")
            value = _as_float(row.get("set_value"))
            if set_id and set_id not in latest and value is not None and value > 0:
                latest[set_id] = value
    return latest


def load_simulation_rows(client) -> Dict[str, Dict[str, Any]]:
    rows = _paged_select(client.table("explore_rip_statistics_latest").select("*"))
    return {str(row.get("set_id")): row for row in rows if row.get("set_id")}


def load_pull_rate_tables(client) -> Dict[str, Dict[str, float]]:
    """set_id -> {normalized_rarity_key: specific-card pull probability}.

    The snapshot cards' own ``pullRate`` field is null across the board, so
    card-level pull probability is derived from the set's modeled pull-rate
    assumptions (``specific_card_odds_denominator`` per rarity) instead. Same
    source the card-level amplification study uses.
    """
    rows = _paged_select(
        client.table("pokemon_set_page_snapshot_latest").select("set_id,payload_json")
    )
    group_priority = {"hit_rarity_model": 0, "pack_structure": 1}
    by_set: Dict[str, Dict[str, float]] = {}
    for row in rows:
        payload = row.get("payload_json")
        if not isinstance(payload, dict):
            continue
        assumptions = payload.get("pull_rate_assumptions") or payload.get("pullRateAssumptions")
        if not isinstance(assumptions, dict):
            continue
        best: Dict[str, Tuple[int, float]] = {}
        for entry in assumptions.get("rows") or []:
            if not isinstance(entry, dict):
                continue
            denominator = _as_float(entry.get("specific_card_odds_denominator"))
            rarity_key = normalize_rarity_key(str(entry.get("rarity") or ""))
            if not rarity_key or denominator is None or denominator <= 0:
                continue
            priority = group_priority.get(str(entry.get("group") or ""), 9)
            current = best.get(rarity_key)
            if current is None or priority < current[0]:
                best[rarity_key] = (priority, 1.0 / denominator)
        if best:
            by_set[str(row.get("set_id"))] = {key: value for key, (_p, value) in best.items()}
    return by_set


def load_snapshot_cards(client, set_ids: Sequence[str]) -> Dict[str, List[Dict[str, Any]]]:
    """One set per request with retries.

    ``cards_json`` blobs are large (200+ cards each), so batching several sets
    per request reliably read-times-out against Supabase. A failed set is
    reported rather than silently treated as "no cards".
    """
    cards_by_set: Dict[str, List[Dict[str, Any]]] = {}
    failed: List[str] = []
    for set_id in sorted(set_ids):
        for attempt in range(3):
            try:
                rows = (
                    client.table("pokemon_set_cards_snapshot_latest")
                    .select("set_id,cards_json")
                    .eq("set_id", set_id)
                    .execute()
                )
            except Exception as exc:
                if attempt == 2:
                    logger.warning("[v3] snapshot cards load failed set_id=%s: %s", set_id, exc)
                    failed.append(set_id)
                    break
                time.sleep(1.5 * (attempt + 1))
                continue
            for row in rows.data or []:
                cards = row.get("cards_json")
                if isinstance(cards, dict):
                    cards = cards.get("cards")
                if isinstance(cards, list):
                    cards_by_set[str(row.get("set_id") or "")] = [
                        card for card in cards if isinstance(card, dict)
                    ]
            break
    if failed:
        logger.warning("[v3] %s set(s) could not load snapshot cards: %s", len(failed), failed)
    return cards_by_set


# ---------------------------------------------------------------------------
# Per-set v3 computation
# ---------------------------------------------------------------------------

def build_v3_row(set_id: str, v2_row: Dict[str, Any], sets: Dict[str, Dict[str, Any]], eras: Dict[str, str]) -> Dict[str, Any]:
    rollups = v2_row.get("subject_rollups_json") or []
    diagnostics = v2_row.get("diagnostics_json") or {}
    coverage_audit = diagnostics.get("coverage_audit") or {}
    link_counts = diagnostics.get("hit_link_category_counts") or {}

    v3 = compute_universal_set_desirability(rollups)
    coverage = assess_desirability_coverage(
        canonical_card_count=coverage_audit.get("canonical_card_count") or diagnostics.get("canonical_cards_seen"),
        hit_eligible_card_count=v2_row.get("hit_eligible_card_count"),
        scored_hit_eligible_card_count=v2_row.get("scored_hit_eligible_card_count"),
        unique_subject_count=v2_row.get("unique_subject_count"),
        unmatched_pokemon_hit_count=link_counts.get("unmatched_pokemon_hit_count"),
        true_missing_link_count=link_counts.get("true_missing_link_count"),
    )
    set_row = sets.get(set_id) or {}
    return {
        "set_id": set_id,
        "set_name": v2_row.get("set_name") or set_row.get("name"),
        "set_canonical_key": v2_row.get("set_canonical_key") or set_row.get("canonical_key"),
        "era": eras.get(str(set_row.get("era_id") or "")) or None,
        "release_date": set_row.get("release_date"),
        "score": v3["score"],
        "components": v3["components"],
        "favorite_hit_coverage_raw": v3["favorite_hit_coverage_raw"],
        "distinct_eligible_subject_count": v3["distinct_eligible_subject_count"],
        "top_subjects": v3["top_subjects"],
        "component_inputs": v3["component_inputs"],
        "desirability_coverage": coverage,
        "v2_score": _as_float(v2_row.get("set_desirability_score")),
        "v2_components": {
            "chase_subject_strength": _as_float(v2_row.get("chase_subject_strength")),
            "chase_subject_depth": _as_float(v2_row.get("chase_subject_depth")),
            "accessible_favorite_hits": _as_float(v2_row.get("accessible_favorite_hits")),
            "special_pack_chase_appeal": _as_float(v2_row.get("special_pack_chase_appeal")),
        },
        "counts": {
            "canonical_card_count": coverage_audit.get("canonical_card_count"),
            "hit_eligible_card_count": v2_row.get("hit_eligible_card_count"),
            "scored_hit_eligible_card_count": v2_row.get("scored_hit_eligible_card_count"),
            "unique_subject_count": v2_row.get("unique_subject_count"),
            "duplicate_subject_count": v2_row.get("duplicate_subject_count"),
            "unmatched_hit_count": v2_row.get("unmatched_hit_count"),
            "hit_link_category_counts": link_counts,
        },
        "_rollups": rollups,
    }


def recompute_score_with_rollups(rollups: Sequence[Dict[str, Any]]) -> float:
    return compute_universal_set_desirability(rollups)["score"]


def override_demand(rollups: Sequence[Dict[str, Any]], fan_weight: float, trend_weight: float) -> List[Dict[str, Any]]:
    adjusted: List[Dict[str, Any]] = []
    for row in rollups:
        if not isinstance(row, dict):
            continue
        copied = dict(row)
        fan = _as_float(row.get("max_fan_score"))
        trend = _as_float(row.get("max_trend_score"))
        if fan is None:
            adjusted.append(copied)
            continue
        demand = fan if trend is None else fan_weight * fan + trend_weight * trend
        copied["max_desirability_score"] = round(demand, 4)
        adjusted.append(copied)
    return adjusted


# ---------------------------------------------------------------------------
# Stress tests (Phase 11)
# ---------------------------------------------------------------------------

def rank_map(rows: Sequence[Dict[str, Any]], key: str = "score") -> Dict[str, int]:
    scored = [row for row in rows if _as_float(row.get(key)) is not None]
    scored = sorted(scored, key=lambda row: (-(_as_float(row.get(key)) or 0.0), str(row.get("set_id"))))
    return {str(row["set_id"]): rank for rank, row in enumerate(scored, start=1)}


def stress_fan_trend_sensitivity(v3_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    configs = {"fan_100_trend_0": (1.0, 0.0), "fan_75_trend_25": (0.75, 0.25), "fan_50_trend_50": (0.5, 0.5)}
    scores: Dict[str, Dict[str, float]] = {name: {} for name in configs}
    for row in v3_rows:
        for name, (fan_weight, trend_weight) in configs.items():
            scores[name][row["set_id"]] = recompute_score_with_rollups(
                override_demand(row["_rollups"], fan_weight, trend_weight)
            )
    set_ids = [row["set_id"] for row in v3_rows]
    baseline = scores["fan_75_trend_25"]
    correlations = {}
    for name in configs:
        xs = [baseline[set_id] for set_id in set_ids]
        ys = [scores[name][set_id] for set_id in set_ids]
        correlations[f"spearman_75_25_vs_{name}"] = round(spearman(xs, ys) or 0.0, 4)
    deltas = sorted(
        (
            {
                "set_name": row["set_name"],
                "score_75_25": scores["fan_75_trend_25"][row["set_id"]],
                "score_100_0": scores["fan_100_trend_0"][row["set_id"]],
                "score_50_50": scores["fan_50_trend_50"][row["set_id"]],
                "max_abs_delta": round(
                    max(
                        abs(scores["fan_100_trend_0"][row["set_id"]] - scores["fan_75_trend_25"][row["set_id"]]),
                        abs(scores["fan_50_trend_50"][row["set_id"]] - scores["fan_75_trend_25"][row["set_id"]]),
                    ),
                    4,
                ),
            }
            for row in v3_rows
        ),
        key=lambda item: -item["max_abs_delta"],
    )
    return {
        "rank_correlations": correlations,
        "most_trend_sensitive_sets": deltas[:10],
        "median_max_abs_delta": round(statistics.median(item["max_abs_delta"] for item in deltas), 4) if deltas else None,
    }


def stress_single_top_subject_removal(v3_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    results = []
    for row in v3_rows:
        subjects = eligible_subject_rollups(row["_rollups"])
        if not subjects:
            continue
        top_key = subjects[0].get("subject_key")
        remaining = [r for r in row["_rollups"] if isinstance(r, dict) and r.get("subject_key") != top_key]
        reduced = recompute_score_with_rollups(remaining)
        delta = round(row["score"] - reduced, 4)
        results.append(
            {
                "set_name": row["set_name"],
                "top_subject": subjects[0].get("subject_name"),
                "score": row["score"],
                "score_without_top_subject": reduced,
                "delta": delta,
                "classification": (
                    "single_subject_dependent" if delta > 15
                    else "moderately_concentrated" if delta > 5
                    else "broad"
                ),
            }
        )
    counts = defaultdict(int)
    for item in results:
        counts[item["classification"]] += 1
    return {
        "classification_counts": dict(counts),
        "classification_thresholds": {"broad": "<=5", "moderately_concentrated": "5-15", "single_subject_dependent": ">15"},
        "most_dependent": sorted(results, key=lambda item: -item["delta"])[:10],
        "rows": results,
    }


def stress_set_size_bias(v3_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    def corr_against(count_key: str, score_key: str = "score", component: Optional[str] = None) -> Optional[float]:
        xs, ys = [], []
        for row in v3_rows:
            size = _as_float((row.get("counts") or {}).get(count_key))
            value = _as_float(row["components"].get(component)) if component else _as_float(row.get(score_key))
            if size is not None and value is not None:
                xs.append(size)
                ys.append(value)
        rho = spearman(xs, ys)
        return round(rho, 4) if rho is not None else None

    return {
        "score_vs_canonical_card_count": corr_against("canonical_card_count"),
        "score_vs_hit_eligible_card_count": corr_against("hit_eligible_card_count"),
        "score_vs_distinct_subject_count": corr_against("unique_subject_count"),
        "components_vs_distinct_subject_count": {
            component: corr_against("unique_subject_count", component=component)
            for component in ("chase_subject_strength", "chase_subject_depth", "favorite_hit_coverage")
        },
    }


def stress_iconic_subjects(v3_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    demand_by_reference: Dict[Any, Tuple[str, float]] = {}
    for row in v3_rows:
        for rollup in row["_rollups"]:
            if not isinstance(rollup, dict):
                continue
            reference = rollup.get("pokemon_reference_id")
            demand = _as_float(rollup.get("max_desirability_score"))
            if reference is None or demand is None:
                continue
            if reference not in demand_by_reference or demand > demand_by_reference[reference][1]:
                demand_by_reference[reference] = (str(rollup.get("subject_name") or ""), demand)
    ranked_species = sorted(demand_by_reference.items(), key=lambda item: -item[1][1])
    top10 = {reference for reference, _ in ranked_species[:10]}
    top20 = {reference for reference, _ in ranked_species[:20]}

    result: Dict[str, Any] = {
        "top_10_species": [name for _, (name, _demand) in ranked_species[:10]],
        "top_20_species": [name for _, (name, _demand) in ranked_species[:20]],
    }
    baseline_ranks = rank_map(v3_rows)
    for label, excluded in (("excluding_top_10", top10), ("excluding_top_20", top20)):
        variant_rows = []
        for row in v3_rows:
            filtered = [
                rollup for rollup in row["_rollups"]
                if not (isinstance(rollup, dict) and rollup.get("pokemon_reference_id") in excluded)
            ]
            variant_rows.append({"set_id": row["set_id"], "set_name": row["set_name"], "score": recompute_score_with_rollups(filtered)})
        variant_ranks = rank_map(variant_rows)
        shared = [set_id for set_id in baseline_ranks if set_id in variant_ranks]
        rho = spearman(
            [float(baseline_ranks[set_id]) for set_id in shared],
            [float(variant_ranks[set_id]) for set_id in shared],
        )
        movers = sorted(
            (
                {"set_id": set_id, "rank_delta": baseline_ranks[set_id] - variant_ranks[set_id]}
                for set_id in shared
            ),
            key=lambda item: abs(item["rank_delta"]),
            reverse=True,
        )[:10]
        result[label] = {"rank_spearman_vs_baseline": round(rho, 4) if rho is not None else None, "largest_rank_movers": movers}
    return result


def stress_era_distribution(v3_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_era: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in v3_rows:
        by_era[str(row.get("era") or "unknown")].append(row)
    output = []
    for era, rows in sorted(by_era.items()):
        scores = [row["score"] for row in rows if _as_float(row.get("score")) is not None]
        if not scores:
            continue
        output.append(
            {
                "era": era,
                "set_count": len(scores),
                "mean": round(statistics.mean(scores), 2),
                "median": round(statistics.median(scores), 2),
                "stdev": round(statistics.stdev(scores), 2) if len(scores) > 1 else 0.0,
                "min": round(min(scores), 2),
                "max": round(max(scores), 2),
                "share_above_60": round(sum(1 for score in scores if score >= 60) / len(scores), 3),
            }
        )
    return output


def stress_normalization_stability(v3_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    raws = [row["favorite_hit_coverage_raw"] for row in v3_rows]
    full_cohort = cohort_robust_normalization(raws)
    baseline = {
        row["set_id"]: apply_cohort_robust_normalization(row["favorite_hit_coverage_raw"], full_cohort)
        for row in v3_rows
    }
    max_shift = 0.0
    shifts: List[float] = []
    for left_out_index in range(len(v3_rows)):
        cohort = cohort_robust_normalization(
            [raw for index, raw in enumerate(raws) if index != left_out_index]
        )
        for index, row in enumerate(v3_rows):
            if index == left_out_index:
                continue
            value = apply_cohort_robust_normalization(row["favorite_hit_coverage_raw"], cohort)
            base = baseline.get(row["set_id"])
            if value is not None and base is not None:
                shift = abs(value - base)
                shifts.append(shift)
                max_shift = max(max_shift, shift)

    depth_sensitivity = {}
    baseline_ranks = rank_map(v3_rows)
    for cap in DEPTH_EFFECTIVE_COUNT_SENSITIVITY_CAPS:
        variant_rows = []
        for row in v3_rows:
            subjects = eligible_subject_rollups(row["_rollups"])
            depth, _ = compute_chase_subject_depth_v3(subjects, effective_count_cap=cap)
            weights = {"chase_subject_strength": 30 / 90, "chase_subject_depth": 25 / 90, "favorite_hit_coverage": 35 / 90}
            score = (
                weights["chase_subject_strength"] * row["components"]["chase_subject_strength"]
                + weights["chase_subject_depth"] * depth
                + weights["favorite_hit_coverage"] * row["components"]["favorite_hit_coverage"]
            )
            variant_rows.append({"set_id": row["set_id"], "score": round(score, 4)})
        variant_ranks = rank_map(variant_rows)
        shared = [set_id for set_id in baseline_ranks if set_id in variant_ranks]
        rho = spearman(
            [float(baseline_ranks[set_id]) for set_id in shared],
            [float(variant_ranks[set_id]) for set_id in shared],
        )
        depth_sensitivity[f"cap_{int(cap)}"] = round(rho, 4) if rho is not None else None

    return {
        "shipping_normalization": "fixed saturated transform (cohort-independent; leave-one-set-out shift is 0 by construction)",
        "cohort_robust_variant_loso": {
            "median_abs_shift": round(statistics.median(shifts), 4) if shifts else None,
            "max_abs_shift": round(max_shift, 4),
        },
        "depth_cap_rank_spearman_vs_default": depth_sensitivity,
    }


def stress_existing_rank_comparison(v3_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    v3_ranks = rank_map(v3_rows, "score")
    v2_rows = [{"set_id": row["set_id"], "score": row["v2_score"]} for row in v3_rows if row.get("v2_score") is not None]
    v2_ranks = rank_map(v2_rows, "score")
    shared = [set_id for set_id in v3_ranks if set_id in v2_ranks]
    rho = spearman(
        [float(v3_ranks[set_id]) for set_id in shared],
        [float(v2_ranks[set_id]) for set_id in shared],
    )
    by_id = {row["set_id"]: row for row in v3_rows}
    movers = []
    for set_id in shared:
        row = by_id[set_id]
        delta = v2_ranks[set_id] - v3_ranks[set_id]
        reasons = []
        v2_components = row.get("v2_components") or {}
        if (v2_components.get("special_pack_chase_appeal") or 0) > 0:
            reasons.append("special_pack_component_removed_from_universal_score")
        depth_delta = (row["components"]["chase_subject_depth"] or 0) - (v2_components.get("chase_subject_depth") or 0)
        if abs(depth_delta) >= 10:
            reasons.append(f"depth_method_change_tier_points_to_hhi ({depth_delta:+.1f})")
        coverage_delta = (row["components"]["favorite_hit_coverage"] or 0) - (v2_components.get("accessible_favorite_hits") or 0)
        if abs(coverage_delta) >= 10:
            reasons.append(f"favorite_hit_coverage_reshaped ({coverage_delta:+.1f})")
        strength_delta = (row["components"]["chase_subject_strength"] or 0) - (v2_components.get("chase_subject_strength") or 0)
        if abs(strength_delta) >= 5:
            reasons.append(f"strength_eligibility_and_renormalization_change ({strength_delta:+.1f})")
        movers.append(
            {
                "set_name": row["set_name"],
                "v2_rank": v2_ranks[set_id],
                "v3_rank": v3_ranks[set_id],
                "rank_delta": delta,
                "v2_score": row.get("v2_score"),
                "v3_score": row["score"],
                "reasons": reasons or ["component_weight_renormalization_30_25_35_over_90"],
            }
        )
    movers.sort(key=lambda item: abs(item["rank_delta"]), reverse=True)
    return {"rank_spearman_v3_vs_v2": round(rho, 4) if rho is not None else None, "largest_movers": movers[:15]}


# ---------------------------------------------------------------------------
# Phase 12 - simulation cohort details
# ---------------------------------------------------------------------------

def build_simulation_details(
    v3_by_set: Dict[str, Dict[str, Any]],
    cards_by_set: Dict[str, List[Dict[str, Any]]],
    v2_rows: Dict[str, Dict[str, Any]],
    pull_rates: Dict[str, Dict[str, float]],
) -> Dict[str, Any]:
    per_set: Dict[str, Any] = {}
    comparison_rows: List[Dict[str, Any]] = []
    for set_id, cards in cards_by_set.items():
        v3_row = v3_by_set.get(set_id)
        if v3_row is None:
            continue
        card_to_subject: Dict[str, Dict[str, Any]] = {}
        for rollup in v3_row["_rollups"]:
            if not isinstance(rollup, dict):
                continue
            for card_ref in rollup.get("all_card_names") or []:
                card_id = str((card_ref or {}).get("pokemon_canonical_card_id") or "")
                if card_id:
                    card_to_subject[card_id] = rollup
        rarity_probabilities = pull_rates.get(set_id) or {}
        card_rows = []
        eligible_card_count = 0
        for card in cards:
            card_id = str(card.get("id") or card.get("canonical_card_id") or card.get("pokemon_canonical_card_id") or "")
            rollup = card_to_subject.get(card_id)
            if rollup is None:
                continue
            eligible_card_count += 1
            probability = _as_float(card.get("pullRate") or card.get("pull_rate"))
            if probability is None:
                probability = rarity_probabilities.get(normalize_rarity_key(str(card.get("rarity") or "")))
            if probability is None:
                continue
            if probability > 1:
                probability = 1.0 / probability
            card_rows.append(
                {
                    "subject_key": rollup.get("subject_key"),
                    "subject_name": rollup.get("subject_name"),
                    "subject_demand": rollup.get("max_desirability_score"),
                    "pull_probability": probability,
                    "hit_family": rollup.get("best_rarity_bucket"),
                    "card_name": card.get("name"),
                }
            )
        share = (len(card_rows) / eligible_card_count) if eligible_card_count else 0.0
        if share < PULL_RATE_MIN_CARD_SHARE or not card_rows:
            per_set[set_id] = {
                "set_name": v3_row["set_name"],
                "status": "missing_pull_rates",
                "eligible_cards_seen": eligible_card_count,
                "cards_with_pull_rate": len(card_rows),
            }
            continue

        special_pack = None
        v2_row = v2_rows.get(set_id) or {}
        special_summary = v2_row.get("special_pack_summary_json") or {}
        for mechanic in special_summary.get("mechanics") or []:
            if mechanic.get("enabled"):
                rate = _as_float(mechanic.get("pull_rate"))
                probability = (1.0 / rate) if rate and rate > 1 else rate
                quality = _as_float(mechanic.get("subject_quality"))
                if probability and quality is not None:
                    special_pack = {"probability": probability, "expected_demand_exposure": quality}
                break

        details = compute_simulation_opening_details(card_rows, special_pack=special_pack)
        exposure = details["pull_accessible_favorite_exposure"]
        magnetism = details.get("chase_magnetism")
        per_set[set_id] = {
            "set_name": v3_row["set_name"],
            "status": "computed",
            "eligible_cards_seen": eligible_card_count,
            "cards_with_pull_rate": len(card_rows),
            "raw_accessible_demand": exposure["raw_accessible_demand"],
            "top_subject_encounter_probability": exposure["top_subject_encounter_probability"],
            "any_top3_encounter_probability": exposure["any_top3_encounter_probability"],
            "p_subject_above_75": exposure.get("p_subject_above_75"),
            "opening_experience": details["opening_experience"]["label"],
            "special_pack_appeal": details["special_pack_appeal"],
            "chase_magnetism": magnetism,
            "desirable_but_inaccessible": [
                row.get("subject_name") for row in exposure["desirable_but_inaccessible_subjects"]
            ],
        }
        comparison_rows.append(
            {
                "set_id": set_id,
                "set_name": v3_row["set_name"],
                "favorite_hit_coverage": v3_row["components"]["favorite_hit_coverage"],
                "raw_accessible_demand": exposure["raw_accessible_demand"],
                "chase_magnetism": (magnetism or {}).get("score"),
                "universal_desirability": v3_row["score"],
            }
        )

    xs = [row["favorite_hit_coverage"] for row in comparison_rows]
    ys = [row["raw_accessible_demand"] for row in comparison_rows]
    rho = spearman(xs, ys)
    coverage_ranks = rank_map(comparison_rows, "favorite_hit_coverage")
    access_ranks = rank_map(comparison_rows, "raw_accessible_demand")
    disagreements = sorted(
        (
            {
                "set_name": row["set_name"],
                "coverage_rank": coverage_ranks.get(row["set_id"]),
                "access_rank": access_ranks.get(row["set_id"]),
                "rank_gap": (coverage_ranks.get(row["set_id"]) or 0) - (access_ranks.get(row["set_id"]) or 0),
            }
            for row in comparison_rows
        ),
        key=lambda item: abs(item["rank_gap"]),
        reverse=True,
    )[:10]
    return {
        "per_set": per_set,
        "universal_vs_pull_access": {
            "n": len(comparison_rows),
            "spearman_coverage_vs_access": round(rho, 4) if rho is not None else None,
            "largest_disagreements": disagreements,
            "note": "User-facing insight only; never a reason to alter the universal rank.",
        },
        "chase_magnetism_rows": comparison_rows,
    }


def audit_chase_magnetism_redundancy(
    comparison_rows: Sequence[Dict[str, Any]],
    simulation_rows: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Required precondition before Chase Magnetism could ever enter RIP.

    Profit/Safety/Stability already contain pull-distribution and price
    information, so a simulation-only chase metric may be redundant with them.
    Report-only: nothing here admits the metric into RIP.
    """
    paired: List[Dict[str, Any]] = []
    for row in comparison_rows:
        magnetism = _as_float(row.get("chase_magnetism"))
        sim_row = simulation_rows.get(str(row.get("set_id"))) or {}
        if magnetism is None:
            continue
        paired.append(
            {
                "set_name": row.get("set_name"),
                "chase_magnetism": magnetism,
                "universal_desirability": _as_float(row.get("universal_desirability")),
                "profit_score": _as_float(sim_row.get("profit_score")),
                "safety_score": _as_float(sim_row.get("safety_score")),
                "stability_score": _as_float(sim_row.get("stability_score")),
            }
        )

    correlations: Dict[str, Any] = {}
    for other in ("profit_score", "safety_score", "stability_score", "universal_desirability"):
        xs = [row["chase_magnetism"] for row in paired if row.get(other) is not None]
        ys = [row[other] for row in paired if row.get(other) is not None]
        rho = spearman(xs, ys)
        correlations[f"chase_magnetism_vs_{other}"] = {
            "n": len(xs),
            "spearman": round(rho, 4) if rho is not None else None,
            "redundancy_flag": bool(rho is not None and abs(rho) > 0.8),
        }
    return {
        "n_sets": len(paired),
        "correlations": correlations,
        "verdict": (
            "Report-only redundancy audit. Chase Magnetism is NOT admitted to RIP "
            "in this pass. Admitting it would require this audit to show it is not "
            "largely restating Profit/Safety/Stability, plus a product decision "
            "about what RIP is meant to reward."
        ),
        "rows": sorted(paired, key=lambda row: -(row["chase_magnetism"] or 0.0)),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(Path("docs") / "research" / "universal_set_desirability_v3_report.json"))
    parser.add_argument("--skip-simulation-details", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

    client = _client()
    logger.info("Loading V2 component rows, sets, eras, set values, simulation rows...")
    v2_rows = load_latest_v2_rows(client)
    sets, eras = load_sets_and_eras(client)
    set_values = load_latest_set_values(client, list(v2_rows.keys()))
    simulation_rows = load_simulation_rows(client)

    logger.info("Computing v3 for %s sets...", len(v2_rows))
    v3_rows = [build_v3_row(set_id, row, sets, eras) for set_id, row in sorted(v2_rows.items())]
    for row in v3_rows:
        row["set_value"] = set_values.get(row["set_id"])
        row["simulation_coverage"] = assess_simulation_coverage(simulation_rows.get(row["set_id"]))

    full_rows = [row for row in v3_rows if row["desirability_coverage"]["status"] == COVERAGE_FULL]
    rank_universal_scores(full_rows)

    # Set-value association: DESCRIPTIVE ONLY (never a gate). Reported next to
    # the prior shipped score's correlation on the same cohort for context.
    association_cohort = [row for row in full_rows if row.get("set_value") is not None]
    prior_rho = spearman(
        [row["v2_score"] for row in association_cohort if row.get("v2_score") is not None],
        [row["set_value"] for row in association_cohort if row.get("v2_score") is not None],
    )
    set_value_association = evaluate_set_value_association(
        association_cohort,
        prior_benchmark_spearman=round(prior_rho, 4) if prior_rho is not None else None,
    )

    # Simulation cohort with v3 desirability merged in.
    sim_cohort = []
    v3_by_set = {row["set_id"]: row for row in v3_rows}
    for set_id, sim_row in simulation_rows.items():
        merged = dict(sim_row)
        v3_row = v3_by_set.get(set_id)
        merged["set_name"] = (sets.get(set_id) or {}).get("name") or set_id
        merged["desirability_score"] = (
            v3_row["score"]
            if v3_row is not None and v3_row["desirability_coverage"]["status"] == COVERAGE_FULL
            else None
        )
        sim_cohort.append(merged)
    sim_cohort.sort(key=lambda row: str(row.get("set_name")))

    redundancy = pillar_redundancy_matrix(sim_cohort)
    sensitivity = weight_sensitivity_report(sim_cohort)
    influence = build_desirability_influence_report(sim_cohort)

    logger.info("Running Phase 11 stress tests...")
    stress = {
        "fan_trend_sensitivity": stress_fan_trend_sensitivity(full_rows),
        "single_top_subject_removal": stress_single_top_subject_removal(full_rows),
        "set_size_bias": stress_set_size_bias(full_rows),
        "iconic_subject_stress": stress_iconic_subjects(full_rows),
        "era_distribution": stress_era_distribution(full_rows),
        "normalization_stability": stress_normalization_stability(full_rows),
        "existing_rank_comparison": stress_existing_rank_comparison(full_rows),
    }

    simulation_details = None
    chase_magnetism_audit = None
    if not args.skip_simulation_details:
        logger.info("Loading snapshot cards for the simulation cohort (%s sets)...", len(simulation_rows))
        cards_by_set = load_snapshot_cards(client, list(simulation_rows.keys()))
        pull_rates = load_pull_rate_tables(client)
        simulation_details = build_simulation_details(v3_by_set, cards_by_set, v2_rows, pull_rates)
        chase_magnetism_audit = audit_chase_magnetism_redundancy(
            simulation_details.pop("chase_magnetism_rows", []), simulation_rows
        )

    coverage_counts = defaultdict(int)
    for row in v3_rows:
        coverage_counts[row["desirability_coverage"]["status"]] += 1
    sim_coverage_counts = defaultdict(int)
    for row in v3_rows:
        sim_coverage_counts[row["simulation_coverage"]["status"]] += 1

    manual_audit = {
        "top_10": [_public_row(row) for row in sorted(full_rows, key=lambda r: r.get("rank") or 10**6)[:10]],
        "bottom_10": [_public_row(row) for row in sorted(full_rows, key=lambda r: -(r.get("rank") or 0))[:10]],
    }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": UNIVERSAL_SET_DESIRABILITY_VERSION,
        "default_rip_weights": dict(DEFAULT_RIP_WEIGHTS),
        "cohort": {
            "sets_total": len(v3_rows),
            "desirability_coverage_counts": dict(coverage_counts),
            "simulation_coverage_counts": dict(sim_coverage_counts),
            "full_coverage_ranked": len(full_rows),
            "set_value_association_cohort_n": len(association_cohort),
            "simulation_cohort_n": len(sim_cohort),
        },
        "set_value_association": set_value_association,
        "pillar_redundancy": redundancy,
        "weight_sensitivity": sensitivity,
        "desirability_influence": {
            "largest_movers": influence["largest_movers"],
            "note": influence["note"],
        },
        "stress_tests": stress,
        "simulation_details": simulation_details,
        "chase_magnetism_redundancy_audit": chase_magnetism_audit,
        "manual_audit": manual_audit,
        "all_set_ranking": [_public_row(row) for row in sorted(full_rows, key=lambda r: r.get("rank") or 10**6)],
        "non_full_sets": [
            {
                "set_name": row["set_name"],
                "coverage": row["desirability_coverage"],
                "score_if_partial": row["score"] if row["desirability_coverage"]["status"] == "partial" else None,
            }
            for row in v3_rows
            if row["desirability_coverage"]["status"] != COVERAGE_FULL
        ],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=False, default=str), encoding="utf-8")

    print(f"Sets: {len(v3_rows)} | full desirability coverage: {len(full_rows)} | simulation full: {sim_coverage_counts.get('full', 0)}")
    print(
        f"SET-VALUE ASSOCIATION (diagnostic only, NOT a gate)  n={set_value_association['n']}  "
        f"spearman={set_value_association['spearman']}  pearson={set_value_association['pearson']}  "
        f"prior_shipped_score_spearman={set_value_association['priorScoreBenchmarkSpearman']}"
    )
    for pair in redundancy["pairs"]:
        print(f"REDUNDANCY {pair['pillars']}: rho={pair['spearman']} flag={pair['redundancy_flag']}")
    for comparison in sensitivity["comparisons"]:
        print(f"SENSITIVITY {comparison['alternative']}: rank_spearman={comparison['rank_spearman_vs_default']}")
    print(f"Report written to {out_path}")
    return 0


def _public_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "rank": row.get("rank"),
        "set_name": row["set_name"],
        "era": row.get("era"),
        "score": row["score"],
        "components": row["components"],
        "distinct_eligible_subject_count": row["distinct_eligible_subject_count"],
        "top_subjects": [subject.get("subject_name") for subject in row.get("top_subjects") or []],
        "set_value": row.get("set_value"),
        "v2_score": row.get("v2_score"),
        "coverage": row["desirability_coverage"]["status"],
        "simulation_coverage": row["simulation_coverage"]["status"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
