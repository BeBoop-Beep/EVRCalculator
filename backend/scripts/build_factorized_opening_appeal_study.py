"""Factorized Opening Appeal study (READ-ONLY research).

Tests whether the previously rejected merged Opening Appeal failed because
desirability was embedded repeatedly across Universal Roster Appeal, Accessible
Appeal, and Elite Chase Magnetism - and whether a factorized rebuild

    Opening Appeal = Desirability x Opening Structure

applying desirability exactly once does any better.

Approached as an attempted FALSIFICATION of the factorized hypothesis. The
prior "do not merge" recommendation is not protected; neither is the
factorization proposal.

Price is used ONLY as an external validation outcome. It never enters the
construction, normalization, internal weighting, or selection of any factor or
candidate. No weight in this study is fitted to price.

Nothing is committed, nothing is wired into RIP, and nothing is written to the
database.

Reuses the IO layer of build_opening_appeal_study.py so the two studies read
exactly the same cohort.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.calculations.utils.rarity_classification import normalize_rarity_key  # noqa: E402
from backend.desirability.card_appeal import get_treatment_score  # noqa: E402
from backend.desirability.factorized_opening_appeal import (  # noqa: E402
    ANCHOR_VARIANTS,
    A_STAR_VARIANTS,
    D_SATURATION_K_DEFAULT,
    D_SATURATION_K_VARIANTS,
    FACTORIZED_CANDIDATE_KEYS,
    FACTORIZED_OPENING_APPEAL_VERSION,
    LABEL_ACCESSIBLE_OPENING,
    LABEL_BALANCED_OPENING,
    LABEL_MARKET_CHASE,
    LABEL_NOT_RECOMMENDED,
    LABEL_UNIVERSAL_ROSTER,
    M_STAR_TOP_N_VARIANTS,
    TOP3_MODE_ACCESS,
    TOP3_MODE_PROBABILITY,
    accessibility_interpretations,
    complement_error,
    compute_a_star,
    compute_d1,
    compute_d2,
    compute_factorized_candidates,
    compute_m_star_m1,
    compute_m_star_m2,
    f3_degeneracy_note,
)
from backend.desirability.opening_appeal import (  # noqa: E402
    build_subjects,
    compute_accessible_appeal,
    compute_elite_chase_magnetism,
)
from backend.desirability.rarity_buckets import HIT_BUCKETS, classify_rarity  # noqa: E402
from backend.desirability.scoring_config import DEFAULT_RIP_WEIGHTS  # noqa: E402
from backend.desirability.universal_set_desirability import (  # noqa: E402
    COVERAGE_FULL,
    assess_desirability_coverage,
    compute_universal_set_desirability,
    eligible_subject_rollups,
)
from backend.desirability.weighted_rip import compute_weighted_rip, spearman  # noqa: E402
from backend.scripts.build_opening_appeal_study import (  # noqa: E402
    _paged_select,
    load_appeal_by_card,
    load_cards,
    load_latest_v2_rows,
    load_prices,
    load_pull_rate_model,
    load_set_values,
    load_simulation_rows,
)

logger = logging.getLogger(__name__)

# --- Fixed seeds and configuration (emitted into the JSON report) ------------
RANDOM_SEED_BOOTSTRAP = 20260716
RANDOM_SEED_UNCERTAINTY = 20260717
BOOTSTRAP_DRAWS = 500
UNCERTAINTY_DRAWS = 200
REDUNDANCY_FLAG = 0.80
RANK_STABILITY_BAND = 3

# Uniform calibration scenarios (rank-preserving by construction).
UNIFORM_PULL_SCENARIOS: Dict[str, float] = {
    "base": 1.0,
    "easier_15pct": 1.15,
    "harder_15pct": 1.0 / 1.15,
    "easier_25pct": 1.25,
    "harder_25pct": 1.0 / 1.25,
}

# Relative-error scenarios: independent / partially correlated multiplicative
# log-normal shocks on each set x rarity odds. sigma is the log-space standard
# deviation. These are UNCERTAINTY SCENARIOS, not empirically estimated bounds -
# no source sample counts exist for the modeled pull rates.
RELATIVE_ERROR_SCENARIOS: Dict[str, Dict[str, float]] = {
    "relative_10pct_independent": {"sigma": 0.10, "set_correlation": 0.0},
    "relative_20pct_independent": {"sigma": 0.20, "set_correlation": 0.0},
    "relative_30pct_independent": {"sigma": 0.30, "set_correlation": 0.0},
    "relative_20pct_correlated": {"sigma": 0.20, "set_correlation": 0.5},
}

# Column names are prefixed by the D and M variant in use, so this must be the
# fully qualified column, not the bare formula key.
PRIMARY_CANDIDATE = "D1_M1_F1_balanced_multiplicative"
# The market-chase candidate is tracked through uncertainty too: it is the one
# that survives external validation, so its stability is the decision-relevant
# question.
SECONDARY_CANDIDATE = "D1_M1_F4_market_chase"


def _as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


# ---------------------------------------------------------------------------
# Cohort assembly
# ---------------------------------------------------------------------------

def build_cohort(client) -> Dict[str, Any]:
    """Load every input once. Scenarios then re-score in memory."""
    pull_model = load_pull_rate_model(client)
    v2_rows = load_latest_v2_rows(client)
    set_rows_raw = _paged_select(client.table("sets").select("id,name,canonical_key,release_date,era_id"))
    eras = {str(r["id"]): str(r.get("name") or "") for r in _paged_select(client.table("eras").select("id,name"))}
    sets_by_id = {str(r["id"]): {**r, "era_name": eras.get(str(r.get("era_id") or ""))} for r in set_rows_raw}
    simulation_rows = load_simulation_rows(client)

    covered = sorted(set(pull_model) & set(v2_rows))
    cards = load_cards(client, covered)
    prices = load_prices(client, covered)
    appeal_by_card = load_appeal_by_card(client, [str(c["id"]) for c in cards])
    set_values = load_set_values(client, covered)

    cards_by_set: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for card in cards:
        cards_by_set[str(card.get("set_id"))].append(card)

    sets: Dict[str, Any] = {}
    exclusions: List[Dict[str, Any]] = []
    for set_id in covered:
        v2_row = v2_rows[set_id]
        diagnostics = v2_row.get("diagnostics_json") or {}
        coverage_audit = diagnostics.get("coverage_audit") or {}
        link_counts = diagnostics.get("hit_link_category_counts") or {}
        rollups = v2_row.get("subject_rollups_json") or []
        coverage = assess_desirability_coverage(
            canonical_card_count=coverage_audit.get("canonical_card_count") or diagnostics.get("canonical_cards_seen"),
            hit_eligible_card_count=v2_row.get("hit_eligible_card_count"),
            scored_hit_eligible_card_count=v2_row.get("scored_hit_eligible_card_count"),
            unique_subject_count=v2_row.get("unique_subject_count"),
            unmatched_pokemon_hit_count=link_counts.get("unmatched_pokemon_hit_count"),
            true_missing_link_count=link_counts.get("true_missing_link_count"),
        )
        v3 = compute_universal_set_desirability(rollups)
        roster = v3["score"] if coverage["status"] == COVERAGE_FULL else None

        rarity_model = pull_model.get(set_id) or {}
        set_cards = cards_by_set.get(set_id, [])

        eligible: List[Dict[str, Any]] = []
        hit_prices: List[float] = []
        all_prices: List[float] = []
        approximate_slots = 0
        for card in set_cards:
            card_id = str(card.get("id") or "")
            price = prices.get(card_id)
            if price is not None:
                all_prices.append(price)
            classification = classify_rarity(card.get("rarity"))
            is_hit = classification.bucket in HIT_BUCKETS
            if is_hit and price is not None:
                hit_prices.append(price)
            appeal_row = appeal_by_card.get(card_id)
            if appeal_row is None or not is_hit:
                continue
            model = rarity_model.get(classification.normalized_key)
            if model is None:
                continue
            if str(model.get("slot_group") or "unknown") in {"unknown", "__unknown__"}:
                approximate_slots += 1
            eligible.append(
                {
                    "subject_key": f"ref:{appeal_row['primary_reference_id']}",
                    "subject_name": appeal_row.get("primary_species"),
                    "subject_demand": appeal_row["appeal"],
                    "rarity_key": classification.normalized_key,
                    "base_probability": model["probability"],
                    "slot_group": model["slot_group"],
                    "card_name": card.get("name"),
                    "rarity": card.get("rarity"),
                    "treatment_prestige": get_treatment_score(card.get("rarity")) / 100.0,
                }
            )

        if roster is None:
            exclusions.append({"set_id": set_id, "set_name": v2_row.get("set_name"),
                               "reason": f"desirability coverage={coverage['status']}"})
        if not eligible:
            exclusions.append({"set_id": set_id, "set_name": v2_row.get("set_name"),
                               "reason": "no hit-eligible card with both an appeal link and a modeled pull rate"})

        set_row = sets_by_id.get(set_id) or {}
        simulation = simulation_rows.get(set_id) or {}
        sorted_prices = sorted(all_prices, reverse=True)
        total_priced = sum(all_prices) or None
        # Value concentration (HHI) over priced cards.
        value_hhi = None
        if total_priced:
            shares = [p / total_priced for p in all_prices]
            value_hhi = sum(s * s for s in shares)

        # Roster-side distinct subjects (D1/D2 population) - independent of
        # pull coverage, exactly like Universal Roster Appeal itself.
        roster_subjects = eligible_subject_rollups(rollups)
        roster_demands = [r.get("max_desirability_score") for r in roster_subjects]

        sets[set_id] = {
            "set_id": set_id,
            "set_name": v2_row.get("set_name") or set_row.get("name"),
            "era": set_row.get("era_name"),
            "release_date": set_row.get("release_date"),
            "roster_appeal": roster,
            "coverage": coverage["status"],
            "roster_demands": roster_demands,
            "roster_subject_count": len(roster_subjects),
            "eligible_cards": eligible,
            "checklist_size": len(set_cards),
            "eligible_card_count": len(eligible),
            "approximate_slot_card_count": approximate_slots,
            "treatment_prestige_mean": (
                round(statistics.mean([c["treatment_prestige"] for c in eligible]), 4) if eligible else None
            ),
            "profit_score": _as_float(simulation.get("profit_score")),
            "safety_score": _as_float(simulation.get("safety_score")),
            "stability_score": _as_float(simulation.get("stability_score")),
            # --- external outcomes (never inputs) ---
            "top_10_card_value": round(sum(sorted_prices[:10]), 2) if sorted_prices else None,
            "top_3_card_value": round(sum(sorted_prices[:3]), 2) if sorted_prices else None,
            "median_hit_value": round(statistics.median(hit_prices), 2) if hit_prices else None,
            "mean_hit_value": round(statistics.mean(hit_prices), 2) if hit_prices else None,
            "total_hit_value": round(sum(hit_prices), 2) if hit_prices else None,
            "set_value": set_values.get(set_id),
            "top1_value_concentration": (
                round(sorted_prices[0] / total_priced, 6) if sorted_prices and total_priced else None
            ),
            "top3_value_concentration": (
                round(sum(sorted_prices[:3]) / total_priced, 6) if sorted_prices and total_priced else None
            ),
            "value_hhi": round(value_hhi, 6) if value_hhi is not None else None,
            "priced_card_count": len(all_prices),
        }

    return {
        "sets": sets,
        "exclusions": exclusions,
        "sets_with_pull_model": len(pull_model),
        "sets_with_rollups": len(v2_rows),
        "covered": covered,
    }


# ---------------------------------------------------------------------------
# Scoring one set under a configuration
# ---------------------------------------------------------------------------

def score_set(
    set_data: Mapping[str, Any],
    *,
    saturation_k: float = D_SATURATION_K_DEFAULT,
    broad_weight: float = 0.60,
    top3_weight: float = 0.40,
    slot_weights: Sequence[float] = (0.50, 0.30, 0.20),
    easy_probability: float = 0.1,
    elite_probability: float = 0.001,
    top3_mode: str = TOP3_MODE_PROBABILITY,
    shocks: Optional[Mapping[Tuple[str, str], float]] = None,
) -> Dict[str, Any]:
    """Compute D1, D2, A*, M1, M2 and every candidate for one set."""
    set_id = str(set_data["set_id"])
    cards = []
    for card in set_data["eligible_cards"]:
        multiplier = 1.0
        if shocks is not None:
            multiplier = shocks.get((set_id, card["rarity_key"]), 1.0)
        cards.append({**card, "pull_probability": min(card["base_probability"] * multiplier, 1.0)})
    subjects = build_subjects(cards) if cards else []

    anchors = {"easy_probability": easy_probability, "elite_probability": elite_probability}
    a_star = compute_a_star(
        subjects, broad_weight=broad_weight, top3_weight=top3_weight,
        top3_mode=top3_mode, **anchors
    ) if subjects else None
    m1 = compute_m_star_m1(subjects, slot_weights=slot_weights, **anchors) if subjects else None
    m2 = compute_m_star_m2(subjects, **anchors) if subjects else None

    d1 = compute_d1(set_data.get("roster_appeal"))
    d2_detail = compute_d2(set_data.get("roster_demands") or [], saturation_k=saturation_k)
    d2 = d2_detail["value"] if (set_data.get("roster_demands") and set_data.get("roster_appeal") is not None) else None

    result: Dict[str, Any] = {
        "set_id": set_id,
        "set_name": set_data.get("set_name"),
        "D1": d1,
        "D2": d2,
        "D2_raw_mass": d2_detail["raw_mass"],
        "A_star": (a_star or {}).get("value"),
        "M1_star": (m1 or {}).get("value"),
        "M2_star": (m2 or {}).get("value"),
        "broad_access_structure": (a_star or {}).get("broad_access_structure"),
        "top3_access_structure": (a_star or {}).get("top3_access_structure"),
        "distinct_subject_count": len(subjects),
        "a_star_detail": a_star,
        "m1_detail": m1,
        "m2_detail": m2,
    }
    # Prior (non-factorized) constructs on the same inputs, for comparison.
    prior_accessible = compute_accessible_appeal(subjects, **anchors) if subjects else None
    prior_magnetism = compute_elite_chase_magnetism(subjects, slot_weights=slot_weights, **anchors) if subjects else None
    result["prior_accessible_appeal"] = (prior_accessible or {}).get("score")
    result["prior_elite_chase_magnetism"] = (prior_magnetism or {}).get("score")

    for d_label, d_value in (("D1", d1), ("D2", d2)):
        for m_label, m_value in (("M1", (m1 or {}).get("value")), ("M2", (m2 or {}).get("value"))):
            candidates = compute_factorized_candidates(
                d=d_value, a_star=(a_star or {}).get("value"), m_star=m_value
            )
            for key, value in candidates.items():
                result[f"{d_label}_{m_label}_{key}"] = value
    result["complement_error_M1"] = complement_error((a_star or {}).get("value"), (m1 or {}).get("value"))
    result["complement_error_M2"] = complement_error((a_star or {}).get("value"), (m2 or {}).get("value"))
    result["complement_error_broad_M2"] = complement_error(
        (a_star or {}).get("broad_access_structure"), (m2 or {}).get("value")
    )
    return result


def candidate_columns() -> List[str]:
    return [
        f"{d}_{m}_{key}"
        for d in ("D1", "D2")
        for m in ("M1", "M2")
        for key in FACTORIZED_CANDIDATE_KEYS
    ]


def build_rows(cohort: Mapping[str, Any], **config: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for set_id, set_data in cohort["sets"].items():
        scored = score_set(set_data, **config)
        merged = {**{k: v for k, v in set_data.items() if k != "eligible_cards"}, **scored}
        rows.append(merged)
    return rows


def usable_rows(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Sets with sufficient modeled pull data for BOTH corrected A* and M*."""
    return [
        row for row in rows
        if row.get("D1") is not None
        and row.get("A_star") is not None
        and row.get("M1_star") is not None
    ]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def _paired(rows: Sequence[Mapping[str, Any]], x_key: str, y_key: str):
    xs, ys, names = [], [], []
    for row in rows:
        x = _as_float(row.get(x_key)) if not isinstance(row.get(x_key), dict) else None
        y = _as_float(row.get(y_key)) if not isinstance(row.get(y_key), dict) else None
        if x is None or y is None:
            continue
        xs.append(x)
        ys.append(y)
        names.append(str(row.get("set_name") or row.get("set_id")))
    return xs, ys, names


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3:
        return None
    x, y = np.array(xs, dtype=float), np.array(ys, dtype=float)
    if np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def bootstrap_spearman(xs, ys, *, draws=BOOTSTRAP_DRAWS, seed=RANDOM_SEED_BOOTSTRAP):
    """Whole-set bootstrap: the set is the unit, so resample sets."""
    if len(xs) < 4:
        return {"ci_low": None, "ci_high": None, "draws": 0}
    rng = np.random.default_rng(seed)
    x, y = np.array(xs, dtype=float), np.array(ys, dtype=float)
    values = []
    for _ in range(draws):
        pick = rng.choice(len(x), size=len(x), replace=True)
        rho = spearman(x[pick].tolist(), y[pick].tolist())
        if rho is not None:
            values.append(rho)
    if len(values) < 20:
        return {"ci_low": None, "ci_high": None, "draws": len(values)}
    array = np.array(values)
    return {
        "ci_low": round(float(np.percentile(array, 2.5)), 4),
        "ci_high": round(float(np.percentile(array, 97.5)), 4),
        "draws": len(values),
        "includes_zero": bool(np.percentile(array, 2.5) <= 0 <= np.percentile(array, 97.5)),
    }


def loso_sensitivity(xs, ys, names) -> Dict[str, Any]:
    if len(xs) < 5:
        return {"min": None, "median": None, "max": None, "most_influential": None}
    baseline = spearman(list(xs), list(ys)) or 0.0
    results = []
    for index in range(len(xs)):
        sub_x = [v for i, v in enumerate(xs) if i != index]
        sub_y = [v for i, v in enumerate(ys) if i != index]
        rho = spearman(sub_x, sub_y)
        if rho is not None:
            results.append((rho, names[index]))
    if not results:
        return {"min": None, "median": None, "max": None, "most_influential": None}
    values = [r for r, _n in results]
    most = max(results, key=lambda item: abs(item[0] - baseline))
    sign_flips = sum(1 for v in values if baseline != 0 and (v * baseline) < 0)
    below_030 = sum(1 for v in values if abs(v) < 0.30)
    return {
        "full_sample": round(baseline, 4),
        "min": round(min(values), 4),
        "median": round(statistics.median(values), 4),
        "max": round(max(values), 4),
        "most_influential": {
            "set": most[1],
            "rho_without": round(most[0], 4),
            "shift": round(most[0] - baseline, 4),
        },
        "removals_reversing_sign": sign_flips,
        "removals_dropping_below_0.30": below_030,
    }


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

MARKET_OUTCOMES: List[Tuple[str, str]] = [
    ("top_10_card_value", "Top-10 card value (PRIMARY)"),
    ("top_3_card_value", "Top-3 card value (PRIMARY)"),
    ("median_hit_value", "Median hit-eligible card value"),
    ("mean_hit_value", "Mean hit-eligible card value"),
    ("total_hit_value", "Total hit-eligible card value"),
    ("set_value", "Total checklist set value"),
    ("top1_value_concentration", "Top-1 value share"),
    ("top3_value_concentration", "Top-3 value share"),
    ("value_hhi", "Value concentration (HHI)"),
]

COMPARATORS = [
    "roster_appeal", "D1", "D2", "prior_accessible_appeal",
    "prior_elite_chase_magnetism", "A_star", "M1_star", "M2_star",
]


def d1_vs_d2(rows: Sequence[Mapping[str, Any]], cohort: Mapping[str, Any]) -> Dict[str, Any]:
    """Is D2 a defensible alternative to the shipping roster score?"""
    out: Dict[str, Any] = {
        "identity_note": (
            "D2 at K_D = 3.0 is algebraically identical to Universal Roster Appeal's own "
            "favorite_hit_coverage component / 100 (asserted in the unit tests). D2 is therefore "
            "not an independent alternative to D1 - it is one of D1's three components promoted "
            "to stand alone, discarding Chase Subject Strength and Chase Subject Depth."
        ),
        "by_saturation_k": {},
    }
    for k in D_SATURATION_K_VARIANTS:
        scored = [
            {
                **row,
                "D2_k": compute_d2(row.get("roster_demands") or [], saturation_k=k)["value"]
                if row.get("roster_appeal") is not None else None,
            }
            for row in rows
        ]
        xs, ys, names = _paired(scored, "D1", "D2_k")
        rho = spearman(xs, ys)
        # Rank differences
        def ranks(key):
            valid = [(r, _as_float(r.get(key))) for r in scored if _as_float(r.get(key)) is not None]
            valid.sort(key=lambda item: -item[1])
            return {str(r.get("set_name")): i + 1 for i, (r, _v) in enumerate(valid)}
        r1, r2 = ranks("D1"), ranks("D2_k")
        shared = sorted(set(r1) & set(r2))
        movers = sorted(
            ({"set": s, "d1_rank": r1[s], "d2_rank": r2[s], "rank_delta": r1[s] - r2[s]} for s in shared),
            key=lambda m: -abs(m["rank_delta"]),
        )
        size_xs, size_ys, _n = _paired(scored, "D2_k", "checklist_size")
        subj_xs, subj_ys, _n2 = _paired(scored, "D2_k", "roster_subject_count")
        d1_size_xs, d1_size_ys, _n3 = _paired(scored, "D1", "checklist_size")
        out["by_saturation_k"][f"K_D={k}"] = {
            "n": len(xs),
            "spearman_D1_vs_D2": round(rho, 4) if rho is not None else None,
            "pearson_D1_vs_D2": round(_pearson(xs, ys), 4) if _pearson(xs, ys) is not None else None,
            "max_abs_rank_delta": max((abs(m["rank_delta"]) for m in movers), default=0),
            "mean_abs_rank_delta": round(float(np.mean([abs(m["rank_delta"]) for m in movers])), 3) if movers else None,
            "largest_movers": movers[:5],
            "D2_vs_checklist_size_spearman": round(spearman(size_xs, size_ys), 4) if len(size_xs) > 4 else None,
            "D2_vs_distinct_subject_count_spearman": round(spearman(subj_xs, subj_ys), 4) if len(subj_xs) > 4 else None,
            "D1_vs_checklist_size_spearman": round(spearman(d1_size_xs, d1_size_ys), 4) if len(d1_size_xs) > 4 else None,
        }
    return out


def complement_analysis(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Do A* and M* remain complements? If so, additive blends are uninformative."""
    out: Dict[str, Any] = {}
    for label, key in (
        ("A_star_vs_M1", "complement_error_M1"),
        ("A_star_vs_M2", "complement_error_M2"),
        ("broad_access_vs_M2", "complement_error_broad_M2"),
    ):
        errors = [_as_float(row.get(key)) for row in rows]
        errors = [e for e in errors if e is not None]
        if not errors:
            continue
        m_key = "M1_star" if "M1" in label else "M2_star"
        a_key = "broad_access_structure" if "broad" in label else "A_star"
        xs, ys, _n = _paired(rows, a_key, m_key)
        rho = spearman(xs, ys)
        out[label] = {
            "n": len(errors),
            "mean_complement_error": round(float(np.mean(errors)), 6),
            "median_complement_error": round(float(np.median(errors)), 6),
            "min_complement_error": round(min(errors), 6),
            "max_complement_error": round(max(errors), 6),
            "pct_sets_error_below_0.01": round(100.0 * sum(1 for e in errors if e < 0.01) / len(errors), 1),
            "spearman_A_vs_M": round(rho, 4) if rho is not None else None,
        }
    out["algebraic_explanation"] = (
        "access_transform(p) = 1 - scarcity_transform(p) at shared anchors. With ONE card per "
        "subject, subject_probability == p_card, so broad = sum(q*access(p)) and "
        "M2 = sum(q*(1-access(p))) = 1 - broad EXACTLY. Complementarity is broken only by "
        "(a) multi-card subjects, where the union probability exceeds the rarest card's "
        "probability while M* takes the max scarcity, (b) A*'s top3 term, and (c) M1's top-3 "
        "truncation vs M2's all-subject aggregation. Independence must NOT be claimed merely "
        "because the observed correlation is not exactly -1."
    )
    out["f3_degeneracy"] = {f"alpha={a:.2f}": f3_degeneracy_note(a) for a in (0.25, 0.50, 0.75)}
    return out


def external_validation(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    predictors = COMPARATORS + candidate_columns()
    results: Dict[str, Any] = {}
    for outcome, label in MARKET_OUTCOMES:
        entry: Dict[str, Any] = {"label": label, "predictors": {}}
        for predictor in predictors:
            xs, ys, names = _paired(rows, predictor, outcome)
            if len(xs) < 5:
                entry["predictors"][predictor] = {"n": len(xs), "spearman": None}
                continue
            rho = spearman(xs, ys)
            log_ys = [math.log(v) for v in ys if v > 0]
            pearson_log = _pearson(xs, log_ys) if len(log_ys) == len(xs) else None
            entry["predictors"][predictor] = {
                "n": len(xs),
                "spearman": round(rho, 4) if rho is not None else None,
                "pearson_log": round(pearson_log, 4) if pearson_log is not None else None,
                "bootstrap_ci": bootstrap_spearman(xs, ys),
                "loso": loso_sensitivity(xs, ys, names),
            }
        roster_rho = (entry["predictors"].get("roster_appeal") or {}).get("spearman")
        magnetism_rho = (entry["predictors"].get("prior_elite_chase_magnetism") or {}).get("spearman")
        entry["improvement_over_roster_appeal"] = {
            c: round((entry["predictors"].get(c) or {}).get("spearman") - roster_rho, 4)
            for c in candidate_columns()
            if roster_rho is not None and (entry["predictors"].get(c) or {}).get("spearman") is not None
        }
        entry["improvement_over_elite_chase_magnetism"] = {
            c: round((entry["predictors"].get(c) or {}).get("spearman") - magnetism_rho, 4)
            for c in candidate_columns()
            if magnetism_rho is not None and (entry["predictors"].get(c) or {}).get("spearman") is not None
        }
        results[outcome] = entry
    return results


def redundancy_matrix(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    targets = [
        "roster_appeal", "D1", "D2", "A_star", "M1_star", "M2_star",
        "prior_accessible_appeal", "prior_elite_chase_magnetism",
        "profit_score", "safety_score", "stability_score",
        "checklist_size", "eligible_card_count", "distinct_subject_count",
        "top1_value_concentration", "top3_value_concentration",
    ]
    out: Dict[str, Any] = {}
    for predictor in ["D1", "D2", "A_star", "M1_star", "M2_star"] + candidate_columns():
        entry = {}
        for target in targets:
            if target == predictor:
                continue
            xs, ys, _n = _paired(rows, predictor, target)
            rho = spearman(xs, ys) if len(xs) >= 5 else None
            entry[target] = {
                "n": len(xs),
                "spearman": round(rho, 4) if rho is not None else None,
                "redundancy_flag": bool(rho is not None and abs(rho) > REDUNDANCY_FLAG),
            }
        out[predictor] = entry
    return out


# ---------------------------------------------------------------------------
# Sparse incremental models B0..B4
# ---------------------------------------------------------------------------

def _design(rows, columns, eras) -> np.ndarray:
    pieces = [np.ones((len(rows), 1))]
    if columns:
        pieces.append(np.column_stack([[float(row[c]) for row in rows] for c in columns]))
    for era in eras[1:]:
        pieces.append(np.array([[1.0 if str(row.get("era")) == era else 0.0] for row in rows]))
    return np.hstack(pieces)


def sparse_model(rows, *, outcome: str, predictor: Optional[str]) -> Optional[Dict[str, Any]]:
    """Leave-whole-set-out validated sparse model. n ~ 21 sets: deliberately tiny."""
    usable = [
        row for row in rows
        if (_as_float(row.get(outcome)) or 0) > 0
        and row.get("log_release_age") is not None
        and row.get("log_checklist_size") is not None
        and (predictor is None or _as_float(row.get(predictor)) is not None)
    ]
    if len(usable) < 8:
        return None
    eras = sorted({str(row.get("era")) for row in usable})
    columns = ["log_release_age", "log_checklist_size"] + ([predictor] if predictor else [])

    predictions, actuals, per_set = [], [], []
    for held_out in sorted({str(row["set_id"]) for row in usable}):
        train = [row for row in usable if str(row["set_id"]) != held_out]
        test = [row for row in usable if str(row["set_id"]) == held_out]
        if len(train) < len(columns) + 3 or not test:
            continue
        X = _design(train, columns, eras)
        y = np.array([math.log(float(row[outcome])) for row in train])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        y_test = np.array([math.log(float(row[outcome])) for row in test])
        y_hat = _design(test, columns, eras) @ beta
        predictions.extend(y_hat.tolist())
        actuals.extend(y_test.tolist())
        per_set.append({"set_name": test[0].get("set_name"), "mae": float(np.mean(np.abs(y_test - y_hat)))})
    if len(predictions) < 5:
        return None
    predicted, actual = np.array(predictions), np.array(actuals)
    errors = actual - predicted
    tss = float(np.sum((actual - actual.mean()) ** 2))
    rss = float(np.sum(errors ** 2))
    return {
        "n_sets": len(per_set),
        "mae": round(float(np.mean(np.abs(errors))), 5),
        "rmse": round(float(np.sqrt(np.mean(errors ** 2))), 5),
        "spearman": round(spearman(predicted.tolist(), actual.tolist()) or 0.0, 4),
        "held_out_r2": round(1.0 - rss / tss, 4) if tss > 0 else None,
        "beats_predicting_the_mean": bool(tss > 0 and (1.0 - rss / tss) > 0),
        "macro_avg_per_set_mae": round(float(np.mean([p["mae"] for p in per_set])), 5),
        "median_per_set_mae": round(float(np.median([p["mae"] for p in per_set])), 5),
        "per_set": per_set,
    }


def compare_models(base, richer) -> Dict[str, Any]:
    if not base or not richer:
        return {"available": False}
    base_by = {p["set_name"]: p["mae"] for p in base["per_set"]}
    rich_by = {p["set_name"]: p["mae"] for p in richer["per_set"]}
    shared = sorted(set(base_by) & set(rich_by))
    deltas = [(base_by[s] - rich_by[s], s) for s in shared]
    improved = [d for d, _s in deltas if d > 0]
    mae_reduction = (base["mae"] - richer["mae"]) / base["mae"] if base["mae"] else None
    return {
        "available": True,
        "mae_reduction_pct": round(100.0 * mae_reduction, 3) if mae_reduction is not None else None,
        "spearman_gain": round(richer["spearman"] - base["spearman"], 4),
        "sets_improved": len(improved),
        "sets_harmed": len(deltas) - len(improved),
        "sets_total": len(deltas),
        "both_models_have_negative_held_out_r2": bool(
            (base.get("held_out_r2") or 0) < 0 and (richer.get("held_out_r2") or 0) < 0
        ),
    }


def incremental_models(rows: Sequence[Mapping[str, Any]], best_opening: str) -> Dict[str, Any]:
    outcome = "top_10_card_value"
    b0 = sparse_model(rows, outcome=outcome, predictor=None)
    specs = {
        "B0_controls": (b0, None),
        "B1_plus_D": (sparse_model(rows, outcome=outcome, predictor="D1"), "D1"),
        "B2_plus_M_star": (sparse_model(rows, outcome=outcome, predictor="M1_star"), "M1_star"),
        "B3_plus_D_x_M": (sparse_model(rows, outcome=outcome, predictor="D1_M1_F4_market_chase"),
                          "D1_M1_F4_market_chase"),
        "B4_plus_best_opening_experience": (sparse_model(rows, outcome=outcome, predictor=best_opening),
                                            best_opening),
    }
    out: Dict[str, Any] = {
        "outcome": "log(top_10_card_value)",
        "validation": "leave-whole-set-out",
        "models": {},
        "warning": (
            "Secondary evidence only. A candidate cannot be recommended from incremental lift "
            "when all compared models have negative held-out R2 - a lift between two models that "
            "both predict worse than the sample mean is not evidence."
        ),
    }
    for name, (model, predictor) in specs.items():
        out["models"][name] = {
            "predictor": predictor,
            "model": model,
            "vs_B0": compare_models(b0, model) if name != "B0_controls" else {"available": False},
        }
    negatives = [
        name for name, entry in out["models"].items()
        if entry["model"] and (entry["model"].get("held_out_r2") or 0) < 0
    ]
    out["models_with_negative_held_out_r2"] = negatives
    out["all_models_fail_to_beat_the_mean"] = len(negatives) == len(
        [n for n, e in out["models"].items() if e["model"]]
    )
    return out


# ---------------------------------------------------------------------------
# Structural sensitivity
# ---------------------------------------------------------------------------

def structural_sensitivity(cohort: Mapping[str, Any], base_rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    base_by_set = {row["set_id"]: row for row in base_rows}

    def rank_corr(new_rows, key, base_key=None) -> Optional[float]:
        base_key = base_key or key
        pairs = []
        for row in new_rows:
            base = base_by_set.get(row["set_id"])
            if not base:
                continue
            x, y = _as_float(row.get(key)), _as_float(base.get(base_key))
            if x is not None and y is not None:
                pairs.append((x, y))
        if len(pairs) < 4:
            return None
        rho = spearman([p[0] for p in pairs], [p[1] for p in pairs])
        return round(rho, 4) if rho is not None else None

    out: Dict[str, Any] = {"a_star_weights": {}, "m_star_top_n": {}, "anchors": {}, "top3_mode": {}}

    for name, (broad_w, top3_w) in A_STAR_VARIANTS.items():
        rows = usable_rows(build_rows(cohort, broad_weight=broad_w, top3_weight=top3_w))
        out["a_star_weights"][name] = {
            "weights": {"broad": broad_w, "top3": top3_w},
            "A_star_rank_spearman_vs_default": rank_corr(rows, "A_star"),
            "F1_rank_spearman_vs_default": rank_corr(rows, "D1_M1_F1_balanced_multiplicative"),
            "mean_A_star": round(float(np.mean([r["A_star"] for r in rows])), 4) if rows else None,
        }

    for name, slot_weights in M_STAR_TOP_N_VARIANTS.items():
        rows = usable_rows(build_rows(cohort, slot_weights=slot_weights))
        out["m_star_top_n"][name] = {
            "slot_weights": list(slot_weights),
            "M1_rank_spearman_vs_default": rank_corr(rows, "M1_star"),
            "mean_M1_star": round(float(np.mean([r["M1_star"] for r in rows])), 4) if rows else None,
        }

    for name, anchors in ANCHOR_VARIANTS.items():
        rows = usable_rows(build_rows(cohort, **anchors))
        out["anchors"][name] = {
            "anchors": anchors,
            "A_star_rank_spearman_vs_default": rank_corr(rows, "A_star"),
            "M1_rank_spearman_vs_default": rank_corr(rows, "M1_star"),
            "F4_rank_spearman_vs_default": rank_corr(rows, "D1_M1_F4_market_chase"),
        }

    for mode in (TOP3_MODE_PROBABILITY, TOP3_MODE_ACCESS):
        rows = usable_rows(build_rows(cohort, top3_mode=mode))
        out["top3_mode"][mode] = {
            "A_star_rank_spearman_vs_default": rank_corr(rows, "A_star"),
            "mean_top3_access_structure": round(
                float(np.mean([r["top3_access_structure"] for r in rows])), 6
            ) if rows else None,
            "mean_A_star": round(float(np.mean([r["A_star"] for r in rows])), 4) if rows else None,
        }
    return out


# ---------------------------------------------------------------------------
# Pull-rate uncertainty
# ---------------------------------------------------------------------------

def uniform_pull_scenarios(cohort: Mapping[str, Any], base_rows) -> Dict[str, Any]:
    base_by_set = {row["set_id"]: row for row in base_rows}
    keys = ["A_star", "M1_star", "D1_M1_F1_balanced_multiplicative", "D1_M1_F4_market_chase"]
    out: Dict[str, Any] = {}
    for name, multiplier in UNIFORM_PULL_SCENARIOS.items():
        rows = usable_rows(build_rows(cohort, shocks=_ConstantShocks(multiplier)))
        entry = {"multiplier": multiplier}
        for key in keys:
            pairs = []
            for row in rows:
                base = base_by_set.get(row["set_id"])
                if not base:
                    continue
                x, y = _as_float(row.get(key)), _as_float(base.get(key))
                if x is not None and y is not None:
                    pairs.append((x, y))
            rho = spearman([p[0] for p in pairs], [p[1] for p in pairs]) if len(pairs) >= 4 else None
            entry[f"{key}_rank_spearman_vs_base"] = round(rho, 4) if rho is not None else None
        out[name] = entry
    out["_note"] = (
        "A uniform multiplier shifts every set together, so rank ordering barely moves. This "
        "tests CALIBRATION error, not RELATIVE error between sets - see relative_error_scenarios "
        "for the harsher test."
    )
    return out


class _ConstantShocks(dict):
    """Mapping that returns the same multiplier for every (set, rarity)."""

    def __init__(self, multiplier: float):
        super().__init__()
        self._multiplier = multiplier

    def get(self, _key, _default=None):  # type: ignore[override]
        return self._multiplier


def relative_error_scenarios(cohort: Mapping[str, Any], base_rows) -> Dict[str, Any]:
    """Seeded log-normal multiplicative shocks on each set x rarity odds.

    These are UNCERTAINTY SCENARIOS, not empirically estimated confidence
    bounds: the modeled pull rates carry no source sample counts.
    """
    base_by_set = {row["set_id"]: row for row in base_rows}
    tracked = [PRIMARY_CANDIDATE, SECONDARY_CANDIDATE, "A_star", "M1_star"]
    base_ranks = {
        key: {
            row["set_id"]: i + 1
            for i, row in enumerate(sorted(base_rows, key=lambda r: -(r.get(key) or 0)))
        }
        for key in tracked
    }

    pairs_index = sorted({
        (set_id, card["rarity_key"])
        for set_id, data in cohort["sets"].items()
        for card in data["eligible_cards"]
    })

    out: Dict[str, Any] = {}
    for name, config in RELATIVE_ERROR_SCENARIOS.items():
        sigma = config["sigma"]
        set_corr = config["set_correlation"]
        rng = np.random.default_rng(RANDOM_SEED_UNCERTAINTY)
        rhos: Dict[str, List[float]] = {key: [] for key in tracked}
        within_band: Dict[str, Dict[str, int]] = {key: defaultdict(int) for key in tracked}
        rank_shifts: Dict[str, Dict[str, List[int]]] = {key: defaultdict(list) for key in tracked}
        draws = 0
        for _ in range(UNCERTAINTY_DRAWS):
            set_z = {set_id: rng.standard_normal() for set_id in cohort["sets"]}
            shocks: Dict[Tuple[str, str], float] = {}
            for set_id, rarity_key in pairs_index:
                z = math.sqrt(set_corr) * set_z[set_id] + math.sqrt(1.0 - set_corr) * rng.standard_normal()
                # Log-normal, median-preserving: positive-only by construction.
                shocks[(set_id, rarity_key)] = math.exp(sigma * z - 0.5 * sigma * sigma)
            rows = usable_rows(build_rows(cohort, shocks=shocks))
            if len(rows) < 4:
                continue
            draws += 1
            for key in tracked:
                pairs = []
                for row in rows:
                    base = base_by_set.get(row["set_id"])
                    if not base:
                        continue
                    x, y = _as_float(row.get(key)), _as_float(base.get(key))
                    if x is not None and y is not None:
                        pairs.append((x, y))
                if len(pairs) >= 4:
                    rho = spearman([p[0] for p in pairs], [p[1] for p in pairs])
                    if rho is not None:
                        rhos[key].append(rho)
                ranked = sorted(rows, key=lambda r: -(r.get(key) or 0))
                for position, row in enumerate(ranked, start=1):
                    base_rank = base_ranks[key].get(row["set_id"])
                    if base_rank is None:
                        continue
                    shift = abs(position - base_rank)
                    rank_shifts[key][str(row.get("set_name"))].append(shift)
                    if shift <= RANK_STABILITY_BAND:
                        within_band[key][str(row.get("set_name"))] += 1
        if draws == 0 or not any(rhos.values()):
            continue

        entry: Dict[str, Any] = {
            "sigma_log_space": sigma,
            "set_level_correlation": set_corr,
            "draws": draws,
            "seed": RANDOM_SEED_UNCERTAINTY,
            "by_candidate": {},
        }
        for key in tracked:
            if not rhos[key]:
                continue
            array = np.array(rhos[key])
            stability = {n: c / draws for n, c in within_band[key].items()}
            entry["by_candidate"][key] = {
                "median_rank_spearman_vs_base": round(float(np.median(array)), 4),
                "p05_rank_spearman_vs_base": round(float(np.percentile(array, 5)), 4),
                "p95_rank_spearman_vs_base": round(float(np.percentile(array, 95)), 4),
                "min_rank_spearman_vs_base": round(float(array.min()), 4),
                "pct_sets_within_3_ranks": round(100.0 * float(np.mean(list(stability.values()))), 1)
                if stability else None,
                "most_unstable_sets": sorted(
                    ({"set": s, "mean_abs_rank_shift": round(float(np.mean(v)), 2),
                      "max_abs_rank_shift": int(max(v))} for s, v in rank_shifts[key].items()),
                    key=lambda item: -item["mean_abs_rank_shift"],
                )[:5],
            }
        out[name] = entry
    out["_note"] = (
        "Uncertainty scenarios, NOT empirically estimated confidence bounds. The modeled pull "
        "rates are config-derived and carry no source sample counts to propagate."
    )
    return out


# ---------------------------------------------------------------------------
# RIP consequence
# ---------------------------------------------------------------------------

def rip_effect(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    def rank(values: Dict[str, Optional[float]]) -> Dict[str, Optional[int]]:
        scored = sorted([(k, v) for k, v in values.items() if v is not None], key=lambda i: (-i[1], i[0]))
        ranks: Dict[str, Optional[int]] = {k: None for k in values}
        for position, (k, _v) in enumerate(scored, start=1):
            ranks[k] = position
        return ranks

    def rip_scores(key: str, weight: float, *, scale_to_100: bool) -> Dict[str, Optional[float]]:
        out: Dict[str, Optional[float]] = {}
        for row in rows:
            appeal = _as_float(row.get(key))
            if appeal is not None and scale_to_100:
                appeal = 100.0 * appeal
            weights = dict(DEFAULT_RIP_WEIGHTS)
            weights["desirability"] = weight
            result = compute_weighted_rip(
                {
                    "profit": row.get("profit_score"),
                    "safety": row.get("safety_score"),
                    "stability": row.get("stability_score"),
                    "desirability": appeal,
                },
                weights=weights,
            )
            out[str(row.get("set_name") or row.get("set_id"))] = result.get("score")
        return out

    baseline = rip_scores("roster_appeal", 0.10, scale_to_100=False)
    baseline_ranks = rank(baseline)
    baseline_top10 = {k for k, v in baseline_ranks.items() if v and v <= 10}

    comparisons: Dict[str, Any] = {}
    for candidate in candidate_columns():
        for weight in (0.05, 0.10, 0.15):
            scores = rip_scores(candidate, weight, scale_to_100=True)
            ranks = rank(scores)
            deltas, movers = [], []
            for name, base_rank in baseline_ranks.items():
                new_rank = ranks.get(name)
                if base_rank is None or new_rank is None:
                    continue
                delta = base_rank - new_rank
                deltas.append(delta)
                score_delta = (
                    scores[name] - baseline[name]
                    if scores.get(name) is not None and baseline.get(name) is not None else None
                )
                movers.append({
                    "set": name, "rank_delta": delta,
                    "score_delta": round(score_delta, 3) if score_delta is not None else None,
                })
            top10 = {k for k, v in ranks.items() if v and v <= 10}
            xs, ys, _n = [], [], None
            for name in baseline:
                if baseline.get(name) is not None and scores.get(name) is not None:
                    xs.append(scores[name])
                    ys.append(baseline[name])
            rho = spearman(xs, ys) if len(xs) >= 4 else None
            comparisons[f"{candidate}@{int(weight*100)}%"] = {
                "max_abs_rank_delta": max((abs(d) for d in deltas), default=0),
                "mean_abs_rank_delta": round(float(np.mean([abs(d) for d in deltas])), 3) if deltas else None,
                "max_abs_score_delta": round(
                    max((abs(m["score_delta"]) for m in movers if m["score_delta"] is not None), default=0.0), 3
                ),
                "spearman_vs_current_rip": round(rho, 4) if rho is not None else None,
                "top10_entered": sorted(top10 - baseline_top10),
                "top10_left": sorted(baseline_top10 - top10),
                "largest_movers": sorted(movers, key=lambda m: -abs(m["rank_delta"]))[:3],
            }
    return {
        "baseline": "RIP = 0.58 Profit + 0.20 Safety + 0.12 Stability + 0.10 UniversalRosterAppeal",
        "note": "Research-only variants. Canonical RIP is unchanged.",
        "comparisons": comparisons,
    }


# ---------------------------------------------------------------------------
# Product classification
# ---------------------------------------------------------------------------

def classify_candidates(rows: Sequence[Mapping[str, Any]], redundancy: Mapping[str, Any]) -> Dict[str, Any]:
    """Assign each candidate a product label from its measured behaviour."""
    out: Dict[str, Any] = {}
    for candidate in candidate_columns():
        entry = redundancy.get(candidate) or {}
        roster_rho = (entry.get("roster_appeal") or {}).get("spearman")
        a_rho = (entry.get("A_star") or {}).get("spearman")
        m_rho = (entry.get("M1_star") or {}).get("spearman")
        size_rho = (entry.get("eligible_card_count") or {}).get("spearman")

        reasons: List[str] = []
        if roster_rho is not None and abs(roster_rho) > REDUNDANCY_FLAG:
            reasons.append(f"mostly Roster Appeal restated (rho={roster_rho})")
        if m_rho is not None and abs(m_rho) > REDUNDANCY_FLAG:
            reasons.append(f"mostly Magnetism restated (rho={m_rho})")
        if a_rho is not None and abs(a_rho) < 0.30:
            reasons.append(f"retains little A* information (rho={a_rho})")
        if size_rho is not None and abs(size_rho) > REDUNDANCY_FLAG:
            reasons.append(f"materially size-driven (rho={size_rho})")

        if candidate.endswith("F6_roster_baseline"):
            label = LABEL_UNIVERSAL_ROSTER
        elif candidate.endswith("F4_market_chase"):
            label = LABEL_MARKET_CHASE
        elif candidate.endswith("F5_accessible_roster"):
            label = LABEL_ACCESSIBLE_OPENING
        elif candidate.endswith("F1_balanced_multiplicative"):
            label = LABEL_BALANCED_OPENING
        else:
            label = LABEL_NOT_RECOMMENDED
        if roster_rho is not None and abs(roster_rho) > 0.95 and not candidate.endswith("F6_roster_baseline"):
            label = LABEL_NOT_RECOMMENDED
            reasons.append("effectively identical to the roster baseline it would replace")

        out[candidate] = {
            "label": label,
            "spearman_vs_roster_appeal": roster_rho,
            "spearman_vs_A_star": a_rho,
            "spearman_vs_M1_star": m_rho,
            "spearman_vs_eligible_card_count": size_rho,
            "notes": reasons,
        }
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(Path("docs") / "research" / "factorized_opening_appeal_study.json"))
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

    from backend.db.clients.supabase_client import public_read_client

    logger.info("Loading cohort...")
    cohort = build_cohort(public_read_client)

    rows = build_rows(cohort)
    for row in rows:
        row["log_checklist_size"] = math.log(max(row["checklist_size"], 1))
        try:
            release = datetime.fromisoformat(str(row.get("release_date"))).date()
            age = max((datetime.now(timezone.utc).date() - release).days, 1)
        except (TypeError, ValueError):
            age = None
        row["log_release_age"] = math.log(age) if age else None

    scored = usable_rows(rows)
    logger.info("Sets scored with A* and M*: %s", len(scored))

    logger.info("External validation...")
    validation = external_validation(scored)
    logger.info("Redundancy...")
    redundancy = redundancy_matrix(scored)

    # The "best opening-experience candidate" for B4 is chosen by CONSTRUCT
    # (F1 balanced, which claims to represent both A* and M*), never by
    # scanning outcomes for the strongest correlation.
    best_opening = "D1_M1_F1_balanced_multiplicative"

    logger.info("Sparse incremental models...")
    incremental = incremental_models(scored, best_opening)
    logger.info("Structural sensitivity...")
    structural = structural_sensitivity(cohort, scored)
    logger.info("Uniform pull scenarios...")
    uniform = uniform_pull_scenarios(cohort, scored)
    logger.info("Relative pull-rate uncertainty (seeded)...")
    relative = relative_error_scenarios(cohort, scored)
    logger.info("RIP consequence...")
    rip = rip_effect(scored)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "study": FACTORIZED_OPENING_APPEAL_VERSION,
        "rules": [
            "Price is an external validation outcome ONLY; it never enters construction, normalization, weighting, or selection.",
            "No weight, anchor, or alpha in this study is fitted to price.",
            "Desirability is applied exactly once, in D. A*/M* may select and prioritize subjects but never re-apply magnitude.",
            "Fixed normalization only; no cohort percentiles. Adding/removing a set cannot move another set's score.",
            "Canonical RIP is unchanged. Nothing is wired into production. No database writes occur.",
            "Pull input is modeledPullScarcity (config-derived pack model), never observed scarcity.",
        ],
        "config": {
            "seeds": {
                "bootstrap": RANDOM_SEED_BOOTSTRAP,
                "uncertainty": RANDOM_SEED_UNCERTAINTY,
            },
            "bootstrap_draws": BOOTSTRAP_DRAWS,
            "uncertainty_draws": UNCERTAINTY_DRAWS,
            "redundancy_flag": REDUNDANCY_FLAG,
            "rank_stability_band": RANK_STABILITY_BAND,
            "d_saturation_k_default": D_SATURATION_K_DEFAULT,
            "d_saturation_k_variants": list(D_SATURATION_K_VARIANTS),
            "a_star_variants": {k: list(v) for k, v in A_STAR_VARIANTS.items()},
            "m_star_top_n_variants": {k: list(v) for k, v in M_STAR_TOP_N_VARIANTS.items()},
            "anchor_variants": ANCHOR_VARIANTS,
            "f3_alphas_pre_registered": [0.25, 0.50, 0.75],
            "uniform_pull_scenarios": UNIFORM_PULL_SCENARIOS,
            "relative_error_scenarios": RELATIVE_ERROR_SCENARIOS,
            "primary_candidate_for_uncertainty": PRIMARY_CANDIDATE,
        },
        "audit": {
            "factorization_validity": (
                "The final 0-100 scores CANNOT be algebraically factored: Universal Roster Appeal "
                "contains top-k selection, an HHI depth term, and a saturating exponential; "
                "Accessible Appeal contains normalized subject weights and slot-aware probability "
                "unions; Elite Chase Magnetism contains a per-subject max. No symbolic "
                "factorization of the final scores is performed anywhere in this study. The "
                "factorized model is CONSTRUCTED from shared lower-level subject/card inputs."
            ),
            "repeated_desirability_finding": (
                "The repeated-desirability premise is only HALF true. compute_accessible_appeal "
                "weights by appeal_excess/total_excess - a NORMALIZED share whose absolute "
                "magnitude already cancels - so Accessible Appeal was ALREADY factor-free. "
                "compute_elite_chase_magnetism uses appeal_excess * scarcity, genuinely "
                "multiplying absolute desirability a second time. Magnetism is the only real "
                "offender, which is why it correlates ~0.75 with Roster Appeal while "
                "Accessibility correlates ~-0.15."
            ),
            "d2_identity": (
                "D2 at K_D=3.0 is algebraically identical to Universal Roster Appeal's own "
                "favorite_hit_coverage component / 100 (asserted in the unit tests)."
            ),
        },
        "cohort": {
            "sets_with_pull_model": cohort["sets_with_pull_model"],
            "sets_with_rollups": cohort["sets_with_rollups"],
            "sets_with_both": len(cohort["covered"]),
            "sets_scored": len(scored),
            "cards_total": sum(r["checklist_size"] for r in scored),
            "eligible_cards_total": sum(r["eligible_card_count"] for r in scored),
            "distinct_subjects_total": sum(r["distinct_subject_count"] for r in scored),
            "approximate_slot_card_count": sum(r["approximate_slot_card_count"] for r in scored),
            "exact_slot_calculation": all(r["approximate_slot_card_count"] == 0 for r in scored),
            "era_counts": {
                era: sum(1 for r in scored if str(r.get("era")) == era)
                for era in sorted({str(r.get("era")) for r in scored})
            },
            "exclusions": cohort["exclusions"],
        },
        "set_rows": [
            {k: v for k, v in row.items()
             if k not in {"a_star_detail", "m1_detail", "m2_detail", "roster_demands"}}
            for row in sorted(scored, key=lambda r: -(r.get(PRIMARY_CANDIDATE) or 0))
        ],
        "d1_vs_d2": d1_vs_d2(scored, cohort),
        "complement_analysis": complement_analysis(scored),
        "external_validation": validation,
        "incremental_models": incremental,
        "redundancy": redundancy,
        "product_classification": classify_candidates(scored, redundancy),
        "structural_sensitivity": structural,
        "uniform_pull_scenarios": uniform,
        "relative_error_scenarios": relative,
        "rip_effect": rip,
        "accessibility_interpretations": {
            row["set_name"]: accessibility_interpretations(
                build_subjects([
                    {**c, "pull_probability": c["base_probability"]}
                    for c in cohort["sets"][row["set_id"]]["eligible_cards"]
                ])
            )
            for row in sorted(scored, key=lambda r: -(r.get("A_star") or 0))[:8]
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _print_summary(report)
    print(f"\nReport written to {out_path}")
    return 0


def _print_summary(report: Dict[str, Any]) -> None:
    cohort = report["cohort"]
    print(f"\nCohort: {cohort['sets_scored']} sets | eras: {cohort['era_counts']}")

    print("\n--- Complement analysis (are A* and M* the same axis?) ---")
    for label, entry in report["complement_analysis"].items():
        if not isinstance(entry, dict) or "mean_complement_error" not in entry:
            continue
        print(f"  {label:<22} mean|A+M-1|={entry['mean_complement_error']:<10} "
              f"pct<0.01={entry['pct_sets_error_below_0.01']}% rho={entry['spearman_A_vs_M']}")

    print("\n--- Primary outcome (top-10 card value): Spearman ---")
    primary = report["external_validation"]["top_10_card_value"]["predictors"]
    for key in COMPARATORS:
        entry = primary.get(key) or {}
        ci = entry.get("bootstrap_ci") or {}
        print(f"  {key:<32} rho={entry.get('spearman')} CI=[{ci.get('ci_low')}, {ci.get('ci_high')}] "
              f"zero_in_CI={ci.get('includes_zero')}")
    print("  --- factorized candidates ---")
    ranked = sorted(
        ((k, (primary.get(k) or {}).get("spearman")) for k in candidate_columns()),
        key=lambda i: -(i[1] if i[1] is not None else -9),
    )
    for key, rho in ranked:
        ci = (primary.get(key) or {}).get("bootstrap_ci") or {}
        print(f"  {key:<40} rho={rho} CI=[{ci.get('ci_low')}, {ci.get('ci_high')}]")

    print("\n--- Held-out R2 (sparse models) ---")
    for name, entry in report["incremental_models"]["models"].items():
        model = entry.get("model") or {}
        print(f"  {name:<34} R2={model.get('held_out_r2')} mae={model.get('mae')} "
              f"beats_mean={model.get('beats_predicting_the_mean')}")

    print("\n--- Relative pull-rate uncertainty ---")
    for name, entry in report["relative_error_scenarios"].items():
        if not isinstance(entry, dict) or "by_candidate" not in entry:
            continue
        print(f"  {name} (draws={entry['draws']})")
        for key, stats in entry["by_candidate"].items():
            print(f"      {key:<38} median_rho={stats['median_rank_spearman_vs_base']} "
                  f"p05={stats['p05_rank_spearman_vs_base']} within3ranks={stats['pct_sets_within_3_ranks']}%")

    print("\n--- Redundancy flags ---")
    for predictor, entry in report["redundancy"].items():
        flagged = [f"{k}({v['spearman']})" for k, v in entry.items() if v.get("redundancy_flag")]
        if flagged:
            print(f"  {predictor:<40} {flagged}")


if __name__ == "__main__":
    raise SystemExit(main())
