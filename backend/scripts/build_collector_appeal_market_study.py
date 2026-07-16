"""Collector Appeal + market relationship study (READ-ONLY research).

Three goals, kept deliberately separate:

  1. Can ONE nonfinancial Collector Appeal pillar be built from D, A and M?
     (Construct validity - judged WITHOUT reference to price.)
  2. How do D, A, M, D x M and the Collector Appeal candidates relate to current
     card and set value, once set-size bias is removed? (Explanatory only.)
  3. What is the data actually capable of supporting predictively?

Price is used ONLY as an external validation outcome for goal 2. It never enters
the construction, normalization, internal weighting, or selection of any factor
or candidate. Every candidate and weight is pre-registered in
``backend/desirability/collector_appeal.py``.

Reuses the IO layer of build_opening_appeal_study.py so this study reads exactly
the same cohort as the factorized study it extends.

Nothing is committed, nothing is wired into RIP, nothing is written to the DB.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.desirability.collector_appeal import (  # noqa: E402
    CA4_WEIGHT_GRID,
    CA5_WEIGHT_GRID,
    CA6_DUAL_PATH_FLOOR,
    CA6_DUAL_PATH_GAIN,
    COLLECTOR_APPEAL_CANDIDATE_KEYS,
    COLLECTOR_APPEAL_VERSION,
    COLLECTOR_APPEAL_WEIGHT_GRID,
    LABEL_ACCESSIBILITY_RESTATED,
    LABEL_CHASE_RESTATED,
    LABEL_DEGENERATE,
    LABEL_DESIRABILITY_RESTATED,
    LABEL_DISTINCT,
    LABEL_FINANCIAL_REDUNDANT,
    LABEL_RETAINS_BOTH,
    LABEL_SIZE_DRIVEN,
    axis_position,
    complement_gap,
    compute_collector_appeal_candidates,
    compute_dual_path_depth,
    degeneracy_note,
    profit_funded_rip_weights,
    proportional_rip_weights,
)
from backend.desirability.opening_appeal import build_subjects  # noqa: E402
from backend.desirability.weighted_rip import compute_weighted_rip, spearman  # noqa: E402
from backend.scripts.build_factorized_opening_appeal_study import (  # noqa: E402
    RANDOM_SEED_BOOTSTRAP,
    RANDOM_SEED_UNCERTAINTY,
    BOOTSTRAP_DRAWS,
    UNCERTAINTY_DRAWS,
    RELATIVE_ERROR_SCENARIOS,
    _as_float,
    _pearson,
    _paired,
    bootstrap_spearman,
    build_cohort,
    build_rows,
    loso_sensitivity,
    score_set,
    usable_rows,
)

logger = logging.getLogger(__name__)

STUDY_VERSION = "collector_appeal_market_prediction_v1_research"
REDUNDANCY_FLAG = 0.80
SIZE_FLAG = 0.60

# Value-LEVEL and value-CONCENTRATION outcomes are kept apart on purpose: a
# stronger relationship with concentration is not automatically "better", it is
# a different question about how value is distributed.
LEVEL_OUTCOMES: List[Tuple[str, str]] = [
    ("top_card_value", "Top-1 card value"),
    ("top_3_card_value", "Top-3 total value"),
    ("top_3_avg_value", "Top-3 average value"),
    ("top_10_card_value", "Top-10 total value (PRIMARY)"),
    ("top_10_avg_value", "Top-10 average value"),
    ("median_hit_value", "Median hit value"),
    ("mean_hit_value", "Mean hit value"),
    ("total_hit_value", "Total hit value"),
    ("set_value", "Total set value"),
    ("value_per_eligible_card", "Value per eligible card"),
    ("value_per_hit_card", "Value per hit-eligible card"),
    ("value_per_subject", "Value per distinct desirable subject"),
]
CONCENTRATION_OUTCOMES: List[Tuple[str, str]] = [
    ("top1_value_concentration", "Top-1 value share"),
    ("top3_value_concentration", "Top-3 value share"),
    ("value_hhi", "Value HHI"),
]
SIZE_CONTROLS = ["checklist_size", "eligible_card_count", "distinct_subject_count"]

CORE_CONSTRUCTS = ["D1", "A_star", "M1_star", "D1_M1_F4_market_chase", "dual_path_depth",
                   "complement_gap", "axis_position"]


def _rank(values: Sequence[float]) -> np.ndarray:
    """Average ranks, matching Spearman's tie handling."""
    array = np.asarray(values, dtype=float)
    order = array.argsort()
    ranks = np.empty(len(array), dtype=float)
    ranks[order] = np.arange(1, len(array) + 1, dtype=float)
    # Average ties.
    _vals, inverse, counts = np.unique(array, return_inverse=True, return_counts=True)
    for index in np.where(counts > 1)[0]:
        mask = inverse == index
        ranks[mask] = ranks[mask].mean()
    return ranks


def partial_spearman(
    rows: Sequence[Mapping[str, Any]], x_key: str, y_key: str, control_keys: Sequence[str]
) -> Optional[Dict[str, Any]]:
    """Spearman(x, y) after linearly removing the controls FROM THE RANKS.

    Rank-based partial correlation: rank-transform x, y and each control, then
    correlate the residuals of x and y after regressing each on the controls.
    This is what answers "does chase appeal explain value beyond the number of
    chances a large set has to contain desirable rare cards?"
    """
    keys = [x_key, y_key] + list(control_keys)
    usable = []
    for row in rows:
        values = [_as_float(row.get(k)) for k in keys]
        if any(v is None for v in values):
            continue
        usable.append(values)
    if len(usable) < len(control_keys) + 4:
        return None
    matrix = np.array(usable, dtype=float)
    ranked = np.column_stack([_rank(matrix[:, i]) for i in range(matrix.shape[1])])
    controls = np.hstack([np.ones((len(ranked), 1)), ranked[:, 2:]])

    def residual(column: np.ndarray) -> np.ndarray:
        beta, *_ = np.linalg.lstsq(controls, column, rcond=None)
        return column - controls @ beta

    rx, ry = residual(ranked[:, 0]), residual(ranked[:, 1])
    if np.std(rx) < 1e-12 or np.std(ry) < 1e-12:
        return None
    rho = float(np.corrcoef(rx, ry)[0, 1])
    raw = spearman(matrix[:, 0].tolist(), matrix[:, 1].tolist())
    return {
        "n": len(usable),
        "raw_spearman": round(raw, 4) if raw is not None else None,
        "partial_spearman": round(rho, 4),
        "attenuation": round((raw - rho), 4) if raw is not None else None,
        "controls": list(control_keys),
    }


# ---------------------------------------------------------------------------
# Size-adjusted research variants (expected score estimated WITHOUT price)
# ---------------------------------------------------------------------------

def excess_over_size_expectation(
    rows: Sequence[Mapping[str, Any]], key: str, control_keys: Sequence[str]
) -> Dict[str, Any]:
    """``Excess = observed - expected(observed | size)``.

    The expectation is fitted on the SIZE CONTROLS ONLY - price is never a
    regressor and never an input. This isolates "does this set have more chase
    intensity than its opportunity count alone would predict?"
    """
    usable = [
        row for row in rows
        if _as_float(row.get(key)) is not None
        and all(_as_float(row.get(c)) is not None for c in control_keys)
    ]
    if len(usable) < len(control_keys) + 4:
        return {"available": False}
    X = np.column_stack(
        [np.ones(len(usable))] + [[math.log(max(_as_float(r.get(c)), 1)) for r in usable] for c in control_keys]
    )
    y = np.array([_as_float(r.get(key)) for r in usable], dtype=float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    expected = X @ beta
    residuals = y - expected
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    ss_res = float(np.sum(residuals ** 2))
    by_set = {}
    for row, exp, res in zip(usable, expected, residuals):
        by_set[str(row["set_id"])] = {"expected": round(float(exp), 6), "excess": round(float(res), 6)}
    return {
        "available": True,
        "key": key,
        "controls": list(control_keys),
        "r2_of_size_alone": round(1.0 - ss_res / ss_tot, 4) if ss_tot > 0 else None,
        "by_set": by_set,
        "note": "Expectation fitted on size controls only; price is never a regressor.",
    }


def within_size_band_percentile(rows: Sequence[Mapping[str, Any]], key: str, bands: int = 3) -> Dict[str, str]:
    """Percentile of ``key`` within an eligible-card-count band.

    Cohort-relative BY CONSTRUCTION, so this is a research diagnostic only and
    is never a shippable score: adding a set can move another set's percentile.
    """
    usable = [r for r in rows if _as_float(r.get(key)) is not None
              and _as_float(r.get("eligible_card_count")) is not None]
    if len(usable) < bands * 2:
        return {}
    ordered = sorted(usable, key=lambda r: _as_float(r.get("eligible_card_count")))
    out: Dict[str, str] = {}
    size = max(len(ordered) // bands, 1)
    for index in range(bands):
        chunk = ordered[index * size:] if index == bands - 1 else ordered[index * size:(index + 1) * size]
        values = sorted(_as_float(r.get(key)) for r in chunk)
        for row in chunk:
            value = _as_float(row.get(key))
            pct = 100.0 * sum(1 for v in values if v <= value) / len(values)
            out[str(row["set_id"])] = f"band{index+1}:{pct:.0f}"
    return out


# ---------------------------------------------------------------------------
# Scoring the Collector Appeal candidates onto the factorized rows
# ---------------------------------------------------------------------------

def enrich_rows(cohort: Mapping[str, Any], rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add dual-path depth, gap, axis position and every CA candidate."""
    for row in rows:
        set_data = cohort["sets"].get(str(row["set_id"]))
        subjects = build_subjects(
            [{**c, "pull_probability": c["base_probability"]} for c in set_data["eligible_cards"]]
        ) if set_data and set_data.get("eligible_cards") else []
        depth = compute_dual_path_depth(subjects) if subjects else None
        row["dual_path_depth"] = (depth or {}).get("value")
        row["multi_printing_subject_count"] = (depth or {}).get("multi_printing_subject_count")
        row["complement_gap"] = complement_gap(row.get("A_star"), row.get("M1_star"))
        row["axis_position"] = axis_position(row.get("A_star"), row.get("M1_star"))

        candidates = compute_collector_appeal_candidates(
            d=row.get("D1"), a_star=row.get("A_star"), m_star=row.get("M1_star"),
            dual_path_depth=row.get("dual_path_depth"),
        )
        row.update(candidates)

        # Fixed top-k AVERAGE outcomes do not mechanically reward large sets.
        for k in (3, 10):
            total = _as_float(row.get(f"top_{k}_card_value"))
            row[f"top_{k}_avg_value"] = round(total / k, 4) if total else None
        top10 = _as_float(row.get("top_10_card_value"))
        row["top_card_value"] = None  # filled from cohort below
        set_value = _as_float(row.get("set_value"))
        eligible = _as_float(row.get("eligible_card_count"))
        subjects_n = _as_float(row.get("distinct_subject_count"))
        hits = _as_float(row.get("priced_card_count"))
        row["value_per_eligible_card"] = round(set_value / eligible, 4) if set_value and eligible else None
        row["value_per_hit_card"] = round(_as_float(row.get("total_hit_value")) / hits, 4) if (
            _as_float(row.get("total_hit_value")) and hits) else None
        row["value_per_subject"] = round(set_value / subjects_n, 4) if set_value and subjects_n else None
    return rows


def attach_top_card_value(cohort: Mapping[str, Any], rows: List[Dict[str, Any]], prices_by_set) -> None:
    for row in rows:
        values = prices_by_set.get(str(row["set_id"])) or []
        row["top_card_value"] = round(max(values), 2) if values else None


# ---------------------------------------------------------------------------
# Information retention / redundancy classification
# ---------------------------------------------------------------------------

def information_retention(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    targets = ["D1", "A_star", "M1_star", "D1_M1_F4_market_chase", "dual_path_depth",
               "profit_score", "safety_score", "stability_score",
               "checklist_size", "eligible_card_count", "distinct_subject_count"]
    out: Dict[str, Any] = {}
    for candidate in COLLECTOR_APPEAL_CANDIDATE_KEYS:
        entry: Dict[str, Any] = {"vs": {}}
        variance_zero = False
        values = [_as_float(r.get(candidate)) for r in rows]
        values = [v for v in values if v is not None]
        if values and (max(values) - min(values)) < 1e-9:
            variance_zero = True
        for target in targets:
            xs, ys, _n = _paired(rows, candidate, target)
            rho = spearman(xs, ys) if len(xs) >= 5 else None
            entry["vs"][target] = round(rho, 4) if rho is not None else None
        a_rho = entry["vs"].get("A_star")
        m_rho = entry["vs"].get("M1_star")
        d_rho = entry["vs"].get("D1")
        size_rho = entry["vs"].get("eligible_card_count")
        fin = [entry["vs"].get(k) for k in ("profit_score", "safety_score", "stability_score")]
        fin = [abs(v) for v in fin if v is not None]

        labels: List[str] = []
        if variance_zero:
            labels.append(LABEL_DEGENERATE)
        if d_rho is not None and abs(d_rho) > REDUNDANCY_FLAG:
            labels.append(LABEL_DESIRABILITY_RESTATED)
        if a_rho is not None and abs(a_rho) > REDUNDANCY_FLAG:
            labels.append(LABEL_ACCESSIBILITY_RESTATED)
        if m_rho is not None and abs(m_rho) > REDUNDANCY_FLAG:
            labels.append(LABEL_CHASE_RESTATED)
        if (a_rho is not None and abs(a_rho) >= 0.30) and (m_rho is not None and abs(m_rho) >= 0.30):
            labels.append(LABEL_RETAINS_BOTH)
        if size_rho is not None and abs(size_rho) > REDUNDANCY_FLAG:
            labels.append(LABEL_SIZE_DRIVEN)
        if fin and max(fin) > REDUNDANCY_FLAG:
            labels.append(LABEL_FINANCIAL_REDUNDANT)
        if not labels:
            labels.append(LABEL_DISTINCT)

        entry["retains_accessibility_information"] = bool(a_rho is not None and abs(a_rho) >= 0.30)
        entry["retains_chase_information"] = bool(m_rho is not None and abs(m_rho) >= 0.30)
        entry["size_neutral"] = bool(size_rho is not None and abs(size_rho) <= SIZE_FLAG)
        entry["classification"] = labels
        entry["degeneracy_note"] = degeneracy_note(candidate)
        entry["zero_variance_across_cohort"] = variance_zero
        out[candidate] = entry
    return out


# ---------------------------------------------------------------------------
# Market relationships (raw + size-controlled)
# ---------------------------------------------------------------------------

def market_relationships(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    predictors = CORE_CONSTRUCTS + list(COLLECTOR_APPEAL_CANDIDATE_KEYS) + [
        "profit_score", "safety_score", "stability_score",
        "checklist_size", "eligible_card_count", "distinct_subject_count",
    ]
    out: Dict[str, Any] = {"level_outcomes": {}, "concentration_outcomes": {}}
    for bucket, outcomes in (("level_outcomes", LEVEL_OUTCOMES),
                             ("concentration_outcomes", CONCENTRATION_OUTCOMES)):
        for outcome, label in outcomes:
            entry: Dict[str, Any] = {"label": label, "predictors": {}}
            for predictor in predictors:
                xs, ys, names = _paired(rows, predictor, outcome)
                if len(xs) < 5:
                    entry["predictors"][predictor] = {"n": len(xs), "spearman": None}
                    continue
                rho = spearman(xs, ys)
                log_ys = [math.log(v) for v in ys if v > 0]
                record = {
                    "n": len(xs),
                    "spearman": round(rho, 4) if rho is not None else None,
                    "pearson_log": round(_pearson(xs, log_ys), 4)
                    if len(log_ys) == len(xs) and _pearson(xs, log_ys) is not None else None,
                }
                if outcome == "top_10_card_value":
                    record["bootstrap_ci"] = bootstrap_spearman(xs, ys)
                    record["loso"] = loso_sensitivity(xs, ys, names)
                    for control in SIZE_CONTROLS:
                        record[f"partial_vs_{control}"] = partial_spearman(rows, predictor, outcome, [control])
                    record["partial_vs_all_size_controls"] = partial_spearman(
                        rows, predictor, outcome, SIZE_CONTROLS
                    )
                entry["predictors"][predictor] = record
            out[bucket][outcome] = entry
    out["_note"] = (
        "Value-LEVEL and value-CONCENTRATION outcomes are reported separately. A stronger "
        "relationship with concentration is not automatically better; it answers a different "
        "question (how value is distributed, not how much there is)."
    )
    return out


def size_bias_analysis(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Is D x M still strong after controlling for set size? The decisive test."""
    out: Dict[str, Any] = {"question": (
        "Does Chase Appeal explain market value beyond the number of chances a large set has "
        "to contain desirable rare cards?"
    ), "constructs": {}}
    for key in ["D1", "A_star", "M1_star", "D1_M1_F4_market_chase", "dual_path_depth",
                "CA3_geometric_balance", "CA6_dual_path_utility", "CA0_desirability_only"]:
        entry: Dict[str, Any] = {}
        for control in SIZE_CONTROLS:
            xs, ys, _n = _paired(rows, key, control)
            rho = spearman(xs, ys) if len(xs) >= 5 else None
            entry[f"spearman_vs_{control}"] = round(rho, 4) if rho is not None else None
        entry["partial_top10_all_controls"] = partial_spearman(
            rows, key, "top_10_card_value", SIZE_CONTROLS
        )
        # Fixed top-k AVERAGE: cannot be won by having more cards.
        entry["raw_top10_avg"] = None
        xs, ys, _n = _paired(rows, key, "top_10_avg_value")
        if len(xs) >= 5:
            rho = spearman(xs, ys)
            entry["raw_top10_avg"] = round(rho, 4) if rho is not None else None
        out["constructs"][key] = entry

    out["excess_variants"] = {
        "excess_chase_intensity": excess_over_size_expectation(rows, "M1_star", ["eligible_card_count"]),
        "excess_chase_appeal": excess_over_size_expectation(
            rows, "D1_M1_F4_market_chase", ["eligible_card_count", "distinct_subject_count"]
        ),
    }
    return out


def attach_excess_columns(rows: List[Dict[str, Any]], size_bias: Mapping[str, Any]) -> None:
    for name, key in (("excess_chase_intensity", "M1_star"),
                      ("excess_chase_appeal", "D1_M1_F4_market_chase")):
        variant = size_bias["excess_variants"].get(name) or {}
        by_set = variant.get("by_set") or {}
        for row in rows:
            row[name] = (by_set.get(str(row["set_id"])) or {}).get("excess")


def excess_market_relationship(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Do the size-adjusted variants retain any market signal?"""
    out: Dict[str, Any] = {}
    for key in ("excess_chase_intensity", "excess_chase_appeal"):
        entry: Dict[str, Any] = {}
        for outcome in ("top_10_card_value", "top_10_avg_value", "set_value", "value_per_eligible_card"):
            xs, ys, names = _paired(rows, key, outcome)
            if len(xs) < 5:
                entry[outcome] = {"n": len(xs), "spearman": None}
                continue
            rho = spearman(xs, ys)
            entry[outcome] = {
                "n": len(xs),
                "spearman": round(rho, 4) if rho is not None else None,
                "bootstrap_ci": bootstrap_spearman(xs, ys),
            }
        xs, ys, _n = _paired(rows, key, "eligible_card_count")
        rho = spearman(xs, ys) if len(xs) >= 5 else None
        entry["spearman_vs_eligible_card_count"] = round(rho, 4) if rho is not None else None
        out[key] = entry
    return out


# ---------------------------------------------------------------------------
# RIP weight analysis
# ---------------------------------------------------------------------------

def rip_weight_analysis(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    def rank(values: Dict[str, Optional[float]]) -> Dict[str, Optional[int]]:
        scored = sorted([(k, v) for k, v in values.items() if v is not None], key=lambda i: (-i[1], i[0]))
        ranks: Dict[str, Optional[int]] = {k: None for k in values}
        for position, (k, _v) in enumerate(scored, start=1):
            ranks[k] = position
        return ranks

    def rip(key: str, weights: Mapping[str, float], *, scale: bool) -> Dict[str, Optional[float]]:
        out: Dict[str, Optional[float]] = {}
        for row in rows:
            appeal = _as_float(row.get(key))
            if appeal is not None and scale:
                appeal = 100.0 * appeal
            result = compute_weighted_rip(
                {
                    "profit": row.get("profit_score"),
                    "safety": row.get("safety_score"),
                    "stability": row.get("stability_score"),
                    "desirability": appeal,
                },
                weights=dict(weights),
            )
            out[str(row.get("set_name") or row.get("set_id"))] = result.get("score")
        return out

    baseline = rip("roster_appeal", proportional_rip_weights(0.10), scale=False)
    baseline_ranks = rank(baseline)
    baseline_top10 = {k for k, v in baseline_ranks.items() if v and v <= 10}
    baseline_top5 = {k for k, v in baseline_ranks.items() if v and v <= 5}

    def compare(scores: Dict[str, Optional[float]]) -> Dict[str, Any]:
        ranks = rank(scores)
        deltas, movers, score_deltas = [], [], []
        for name, base_rank in baseline_ranks.items():
            new_rank = ranks.get(name)
            if base_rank is None or new_rank is None:
                continue
            delta = base_rank - new_rank
            deltas.append(delta)
            sd = (scores[name] - baseline[name]) if (
                scores.get(name) is not None and baseline.get(name) is not None) else None
            if sd is not None:
                score_deltas.append(abs(sd))
            movers.append({"set": name, "rank_delta": delta,
                           "score_delta": round(sd, 3) if sd is not None else None})
        top10 = {k for k, v in ranks.items() if v and v <= 10}
        top5 = {k for k, v in ranks.items() if v and v <= 5}
        xs = [scores[n] for n in baseline if baseline.get(n) is not None and scores.get(n) is not None]
        ys = [baseline[n] for n in baseline if baseline.get(n) is not None and scores.get(n) is not None]
        rho = spearman(xs, ys) if len(xs) >= 4 else None
        n = len(deltas) or 1
        return {
            "max_abs_rank_delta": max((abs(d) for d in deltas), default=0),
            "mean_abs_rank_delta": round(float(np.mean([abs(d) for d in deltas])), 3) if deltas else None,
            "median_rank_delta": round(float(np.median(deltas)), 3) if deltas else None,
            "max_abs_score_delta": round(max(score_deltas), 3) if score_deltas else None,
            "spearman_vs_current_rip": round(rho, 4) if rho is not None else None,
            "score_spread": round(float(np.std(xs)), 4) if xs else None,
            "baseline_score_spread": round(float(np.std(ys)), 4) if ys else None,
            "pct_moving_1_plus": round(100.0 * sum(1 for d in deltas if abs(d) >= 1) / n, 1),
            "pct_moving_3_plus": round(100.0 * sum(1 for d in deltas if abs(d) >= 3) / n, 1),
            "pct_moving_5_plus": round(100.0 * sum(1 for d in deltas if abs(d) >= 5) / n, 1),
            "top10_entered": sorted(top10 - baseline_top10),
            "top10_left": sorted(baseline_top10 - top10),
            "top5_entered": sorted(top5 - baseline_top5),
            "top5_left": sorted(baseline_top5 - top5),
            "most_helped": sorted(movers, key=lambda m: -m["rank_delta"])[:3],
            "most_harmed": sorted(movers, key=lambda m: m["rank_delta"])[:3],
        }

    proportional: Dict[str, Any] = {}
    profit_funded: Dict[str, Any] = {}
    for candidate in COLLECTOR_APPEAL_CANDIDATE_KEYS:
        for weight in COLLECTOR_APPEAL_WEIGHT_GRID:
            weights = proportional_rip_weights(weight)
            proportional[f"{candidate}@{int(weight*100)}%"] = {
                "weights": {k: round(v, 4) for k, v in weights.items()},
                "collector_appeal_is_second_largest": bool(weights["desirability"] > weights["safety"]),
                **compare(rip(candidate, weights, scale=True)),
            }
    # Limited sensitivity: fund the increase from Profit only.
    for candidate in ("CA0_desirability_only", "CA2_chase", "CA6_dual_path_utility"):
        for weight in COLLECTOR_APPEAL_WEIGHT_GRID:
            weights = profit_funded_rip_weights(weight)
            profit_funded[f"{candidate}@{int(weight*100)}%"] = {
                "weights": {k: round(v, 4) for k, v in weights.items()},
                **compare(rip(candidate, weights, scale=True)),
            }

    return {
        "baseline": "RIP = 0.58 Profit + 0.20 Safety + 0.12 Stability + 0.10 UniversalRosterAppeal",
        "primary_method": "proportional rescaling of the 58:20:12 financial ratio",
        "second_largest_crossover_weight": round((0.20 / 0.90) / (1.0 + 0.20 / 0.90), 6),
        "second_largest_crossover_note": (
            "Under proportional rescaling Safety shrinks as Collector Appeal grows, so they cross "
            "at w = (20/90)/(1 + 20/90) = 2/11 = 18.18%, NOT at 25% as the brief assumed. "
            "Collector Appeal is already the second-largest pillar at a 20% weight."
        ),
        "note": "Research-only variants. Canonical RIP is unchanged.",
        "proportional_rescaling": proportional,
        "profit_funded_sensitivity": profit_funded,
    }


# ---------------------------------------------------------------------------
# Uncertainty: does the recommendation survive input error?
# ---------------------------------------------------------------------------

def candidate_uncertainty(cohort: Mapping[str, Any], base_rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Pull-rate and desirability uncertainty on the Collector Appeal candidates."""
    tracked = ["CA0_desirability_only", "CA2_chase", "CA3_geometric_balance",
               "CA4_linear_50_50", "CA6_dual_path_utility", "dual_path_depth"]
    base_by_set = {row["set_id"]: row for row in base_rows}
    pairs_index = sorted({
        (set_id, card["rarity_key"])
        for set_id, data in cohort["sets"].items()
        for card in data["eligible_cards"]
    })

    out: Dict[str, Any] = {}
    for name, config in RELATIVE_ERROR_SCENARIOS.items():
        sigma, set_corr = config["sigma"], config["set_correlation"]
        rng = np.random.default_rng(RANDOM_SEED_UNCERTAINTY)
        rhos: Dict[str, List[float]] = {key: [] for key in tracked}
        draws = 0
        for _ in range(UNCERTAINTY_DRAWS):
            set_z = {set_id: rng.standard_normal() for set_id in cohort["sets"]}
            shocks = {}
            for set_id, rarity_key in pairs_index:
                z = math.sqrt(set_corr) * set_z[set_id] + math.sqrt(1.0 - set_corr) * rng.standard_normal()
                shocks[(set_id, rarity_key)] = math.exp(sigma * z - 0.5 * sigma * sigma)
            rows = usable_rows(build_rows(cohort, shocks=shocks))
            if len(rows) < 4:
                continue
            rows = enrich_rows(cohort, rows)
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
        if draws == 0:
            continue
        entry = {"sigma_log_space": sigma, "set_level_correlation": set_corr,
                 "draws": draws, "seed": RANDOM_SEED_UNCERTAINTY, "by_candidate": {}}
        for key in tracked:
            if not rhos[key]:
                continue
            array = np.array(rhos[key])
            entry["by_candidate"][key] = {
                "median_rank_spearman_vs_base": round(float(np.median(array)), 4),
                "p05_rank_spearman_vs_base": round(float(np.percentile(array, 5)), 4),
                "min_rank_spearman_vs_base": round(float(array.min()), 4),
            }
        out[name] = entry
    out["_note"] = (
        "Uncertainty SCENARIOS, not empirically estimated confidence bounds: the modeled pull "
        "rates are config-derived and carry no source sample counts to propagate."
    )
    return out


def desirability_uncertainty(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Perturb D itself and re-rank. D has no measured error, so this is a scenario."""
    rng = np.random.default_rng(RANDOM_SEED_UNCERTAINTY)
    out: Dict[str, Any] = {}
    for sigma in (0.05, 0.10, 0.20):
        rhos: Dict[str, List[float]] = defaultdict(list)
        for _ in range(UNCERTAINTY_DRAWS):
            perturbed = []
            for row in rows:
                d = _as_float(row.get("D1"))
                if d is None:
                    continue
                shocked = min(max(d * math.exp(sigma * rng.standard_normal() - 0.5 * sigma ** 2), 0.0), 1.0)
                candidates = compute_collector_appeal_candidates(
                    d=shocked, a_star=row.get("A_star"), m_star=row.get("M1_star"),
                    dual_path_depth=row.get("dual_path_depth"),
                )
                perturbed.append({"set_id": row["set_id"], **candidates})
            base_by = {r["set_id"]: r for r in rows}
            for key in ("CA0_desirability_only", "CA2_chase", "CA6_dual_path_utility"):
                pairs = [
                    (_as_float(p.get(key)), _as_float(base_by[p["set_id"]].get(key)))
                    for p in perturbed if p["set_id"] in base_by
                ]
                pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
                if len(pairs) >= 4:
                    rho = spearman([p[0] for p in pairs], [p[1] for p in pairs])
                    if rho is not None:
                        rhos[key].append(rho)
        out[f"desirability_lognormal_sigma_{sigma}"] = {
            key: {
                "median_rank_spearman_vs_base": round(float(np.median(values)), 4),
                "p05_rank_spearman_vs_base": round(float(np.percentile(values, 5)), 4),
            }
            for key, values in rhos.items() if values
        }
    out["_note"] = (
        "Desirability carries no measured uncertainty (it is a single snapshot with no repeated "
        "observations), so these are assumption scenarios, not estimated bounds."
    )
    return out


# ---------------------------------------------------------------------------
# CSV emission
# ---------------------------------------------------------------------------

def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c) for c in columns})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(Path("docs") / "research" / "collector_appeal_market_prediction_study.json"))
    parser.add_argument("--csv-dir", default=str(Path("docs") / "research" / "collector_appeal_tables"))
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
        row["set_age_days"] = age

    scored = usable_rows(rows)
    scored = enrich_rows(cohort, scored)

    # Top-1 card value needs the raw price list, which build_cohort does not keep.
    from backend.scripts.build_opening_appeal_study import load_prices
    prices = load_prices(public_read_client, [str(r["set_id"]) for r in scored])
    by_set: Dict[str, List[float]] = defaultdict(list)
    card_sets = {}
    for set_id, data in cohort["sets"].items():
        for card in data["eligible_cards"]:
            card_sets[card.get("card_name")] = set_id
    from backend.scripts.build_opening_appeal_study import load_cards
    all_cards = load_cards(public_read_client, [str(r["set_id"]) for r in scored])
    for card in all_cards:
        price = prices.get(str(card.get("id")))
        if price is not None:
            by_set[str(card.get("set_id"))].append(price)
    attach_top_card_value(cohort, scored, by_set)

    logger.info("Sets scored: %s", len(scored))

    logger.info("Information retention...")
    retention = information_retention(scored)
    logger.info("Market relationships...")
    market = market_relationships(scored)
    logger.info("Size bias...")
    size_bias = size_bias_analysis(scored)
    attach_excess_columns(scored, size_bias)
    excess_market = excess_market_relationship(scored)
    logger.info("RIP weights...")
    rip = rip_weight_analysis(scored)
    logger.info("Desirability uncertainty...")
    d_uncertainty = desirability_uncertainty(scored)
    logger.info("Pull-rate uncertainty (seeded, slow)...")
    pull_uncertainty = candidate_uncertainty(cohort, scored)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "study": STUDY_VERSION,
        "module_version": COLLECTOR_APPEAL_VERSION,
        "rules": [
            "Price is an external validation outcome ONLY; it never enters construction, normalization, weighting, or selection.",
            "Every candidate and weight is pre-registered in backend/desirability/collector_appeal.py.",
            "Desirability is applied exactly once, in D.",
            "Fixed normalization only; no cohort percentiles in any shippable construct.",
            "Canonical RIP is unchanged. Nothing is wired into production. No database writes occur.",
        ],
        "config": {
            "seeds": {"bootstrap": RANDOM_SEED_BOOTSTRAP, "uncertainty": RANDOM_SEED_UNCERTAINTY},
            "bootstrap_draws": BOOTSTRAP_DRAWS,
            "uncertainty_draws": UNCERTAINTY_DRAWS,
            "ca4_weight_grid": [list(w) for w in CA4_WEIGHT_GRID],
            "ca5_weight_grid": [list(w) for w in CA5_WEIGHT_GRID],
            "ca6_dual_path_floor": CA6_DUAL_PATH_FLOOR,
            "ca6_dual_path_gain": CA6_DUAL_PATH_GAIN,
            "collector_appeal_weight_grid": list(COLLECTOR_APPEAL_WEIGHT_GRID),
            "candidate_keys": list(COLLECTOR_APPEAL_CANDIDATE_KEYS),
        },
        "cohort": {
            "sets_scored": len(scored),
            "era_counts": {
                era: sum(1 for r in scored if str(r.get("era")) == era)
                for era in sorted({str(r.get("era")) for r in scored})
            },
            "exclusions": cohort["exclusions"],
        },
        "degeneracy_notes": {k: degeneracy_note(k) for k in COLLECTOR_APPEAL_CANDIDATE_KEYS},
        "set_rows": [
            {k: v for k, v in row.items()
             if k not in {"a_star_detail", "m1_detail", "m2_detail", "roster_demands"}}
            for row in sorted(scored, key=lambda r: -(r.get("CA0_desirability_only") or 0))
        ],
        "information_retention": retention,
        "market_relationships": market,
        "size_bias": size_bias,
        "excess_market_relationship": excess_market,
        "rip_weight_analysis": rip,
        "desirability_uncertainty": d_uncertainty,
        "pull_rate_uncertainty": pull_uncertainty,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    # --- supporting CSVs ---
    csv_dir = Path(args.csv_dir)
    write_csv(
        csv_dir / "collector_appeal_candidate_rankings.csv",
        [
            {
                "candidate": key,
                "classification": "; ".join(retention[key]["classification"]),
                "retains_accessibility": retention[key]["retains_accessibility_information"],
                "retains_chase": retention[key]["retains_chase_information"],
                "size_neutral": retention[key]["size_neutral"],
                "vs_D": retention[key]["vs"]["D1"],
                "vs_A": retention[key]["vs"]["A_star"],
                "vs_M": retention[key]["vs"]["M1_star"],
                "vs_eligible_cards": retention[key]["vs"]["eligible_card_count"],
                "top10_spearman": (market["level_outcomes"]["top_10_card_value"]["predictors"]
                                   .get(key) or {}).get("spearman"),
                "degeneracy": retention[key]["degeneracy_note"],
            }
            for key in COLLECTOR_APPEAL_CANDIDATE_KEYS
        ],
        ["candidate", "classification", "retains_accessibility", "retains_chase", "size_neutral",
         "vs_D", "vs_A", "vs_M", "vs_eligible_cards", "top10_spearman", "degeneracy"],
    )
    write_csv(
        csv_dir / "rip_weight_sensitivity.csv",
        [{"scenario": k, **{kk: vv for kk, vv in v.items() if not isinstance(vv, (list, dict))}}
         for k, v in rip["proportional_rescaling"].items()],
        ["scenario", "collector_appeal_is_second_largest", "max_abs_rank_delta", "mean_abs_rank_delta",
         "median_rank_delta", "max_abs_score_delta", "spearman_vs_current_rip",
         "pct_moving_1_plus", "pct_moving_3_plus", "pct_moving_5_plus", "score_spread"],
    )
    write_csv(
        csv_dir / "set_level_market_relationships.csv",
        [
            {"predictor": p, "outcome": outcome,
             "spearman": (entry["predictors"].get(p) or {}).get("spearman"),
             "pearson_log": (entry["predictors"].get(p) or {}).get("pearson_log")}
            for bucket in ("level_outcomes", "concentration_outcomes")
            for outcome, entry in market[bucket].items()
            for p in entry["predictors"]
        ],
        ["predictor", "outcome", "spearman", "pearson_log"],
    )
    write_csv(
        csv_dir / "set_size_adjusted_analysis.csv",
        [
            {
                "construct": key,
                "vs_checklist_size": entry.get("spearman_vs_checklist_size"),
                "vs_eligible_cards": entry.get("spearman_vs_eligible_card_count"),
                "vs_subjects": entry.get("spearman_vs_distinct_subject_count"),
                "raw_top10": (entry.get("partial_top10_all_controls") or {}).get("raw_spearman"),
                "partial_top10": (entry.get("partial_top10_all_controls") or {}).get("partial_spearman"),
                "attenuation": (entry.get("partial_top10_all_controls") or {}).get("attenuation"),
                "raw_top10_avg": entry.get("raw_top10_avg"),
            }
            for key, entry in size_bias["constructs"].items()
        ],
        ["construct", "vs_checklist_size", "vs_eligible_cards", "vs_subjects",
         "raw_top10", "partial_top10", "attenuation", "raw_top10_avg"],
    )
    write_csv(
        csv_dir / "per_set_metrics.csv",
        sorted(scored, key=lambda r: -(r.get("CA0_desirability_only") or 0)),
        ["set_name", "era", "release_date", "checklist_size", "eligible_card_count",
         "distinct_subject_count", "D1", "A_star", "M1_star", "dual_path_depth",
         "complement_gap", "axis_position", "multi_printing_subject_count",
         "D1_M1_F4_market_chase", "excess_chase_appeal", "excess_chase_intensity",
         *COLLECTOR_APPEAL_CANDIDATE_KEYS,
         "profit_score", "safety_score", "stability_score",
         "top_card_value", "top_10_card_value", "top_10_avg_value", "set_value"],
    )

    _print_summary(report)
    print(f"\nReport written to {out_path}")
    print(f"CSV tables written to {csv_dir}")
    return 0


def _print_summary(report: Dict[str, Any]) -> None:
    print(f"\nCohort: {report['cohort']['sets_scored']} sets")
    print("\n--- Information retention (does the candidate keep BOTH A and M?) ---")
    print(f"{'candidate':<34}{'vs D':>8}{'vs A':>8}{'vs M':>8}{'vs size':>9}  classification")
    for key, entry in report["information_retention"].items():
        v = entry["vs"]
        print(f"{key:<34}{str(v['D1']):>8}{str(v['A_star']):>8}{str(v['M1_star']):>8}"
              f"{str(v['eligible_card_count']):>9}  {'; '.join(entry['classification'])}")

    print("\n--- Size bias: raw vs partial (controlling checklist/eligible/subjects) ---")
    print(f"{'construct':<28}{'raw top10':>11}{'partial':>10}{'attenuation':>13}{'top10 AVG':>11}")
    for key, entry in report["size_bias"]["constructs"].items():
        p = entry.get("partial_top10_all_controls") or {}
        print(f"{key:<28}{str(p.get('raw_spearman')):>11}{str(p.get('partial_spearman')):>10}"
              f"{str(p.get('attenuation')):>13}{str(entry.get('raw_top10_avg')):>11}")

    print("\n--- Excess (size-adjusted) variants vs market ---")
    for key, entry in report["excess_market_relationship"].items():
        top10 = entry.get("top_10_card_value") or {}
        ci = top10.get("bootstrap_ci") or {}
        print(f"  {key:<26} top10 rho={top10.get('spearman')} CI=[{ci.get('ci_low')}, {ci.get('ci_high')}] "
              f"zero_in_CI={ci.get('includes_zero')} vs_size={entry.get('spearman_vs_eligible_card_count')}")

    print("\n--- RIP weight influence (proportional rescaling) ---")
    print(f"{'scenario':<44}{'max_d':>6}{'mean_d':>8}{'rho':>8}{'2nd?':>6}")
    for key, entry in report["rip_weight_analysis"]["proportional_rescaling"].items():
        if not any(key.startswith(c) for c in ("CA0_", "CA2_", "CA3_", "CA6_", "CA4_linear_50_50")):
            continue
        print(f"{key:<44}{entry['max_abs_rank_delta']:>6}{entry['mean_abs_rank_delta']:>8}"
              f"{str(entry['spearman_vs_current_rip']):>8}"
              f"{str(entry['collector_appeal_is_second_largest']):>6}")


if __name__ == "__main__":
    raise SystemExit(main())
