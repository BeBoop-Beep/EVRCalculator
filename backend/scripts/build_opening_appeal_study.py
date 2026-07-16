"""Opening Appeal study (READ-ONLY research).

Evaluates whether RIP's 10% Desirability component should become a broader
simulation-covered **Opening Appeal** pillar built from:

    1. Universal Roster Appeal   (universal_set_desirability_v3, unchanged)
    2. Accessible Appeal         (slot-aware reachability of the roster)
    3. Elite Chase Magnetism     (card appeal x card modeled scarcity)

Covers: candidate formulas + sensitivity (Phase 2), pull-rate uncertainty
scenarios (Phase 6), redundancy + RIP effect (Phase 8), Treatment Prestige
diagnostics (Phase 9), and the Opening Appeal external validation phase
(market-outcome association + sparse incremental models with leave-whole-set-out
validation, whole-set bootstrap, and leave-one-set-out sensitivity).

Price is used ONLY as an external outcome. It never enters the construction,
normalization, internal weighting, or selection of Opening Appeal. No weight
here is fitted to price.

Nothing is committed and nothing is written to the database.
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
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.calculations.utils.rarity_classification import normalize_rarity_key  # noqa: E402
from backend.desirability.card_appeal import get_treatment_score  # noqa: E402
from backend.desirability.composite import COMPOSITE_SCORING_VERSION  # noqa: E402
from backend.desirability.opening_appeal import (  # noqa: E402
    OA_BALANCED_KEY,
    OPENING_APPEAL_CANDIDATES,
    build_subjects,
    compute_accessible_appeal,
    compute_elite_chase_magnetism,
    compute_opening_appeal_candidates,
)
from backend.desirability.rarity_buckets import HIT_BUCKETS, classify_rarity  # noqa: E402
from backend.desirability.scoring_config import DEFAULT_RIP_WEIGHTS  # noqa: E402
from backend.desirability.set_components import SCORING_VERSION as V2_SCORING_VERSION  # noqa: E402
from backend.desirability.universal_set_desirability import (  # noqa: E402
    COVERAGE_FULL,
    assess_desirability_coverage,
    compute_universal_set_desirability,
)
from backend.desirability.weighted_rip import compute_weighted_rip, spearman  # noqa: E402

logger = logging.getLogger(__name__)

BOOTSTRAP_DRAWS = 500
RANDOM_SEED = 20260716
PULL_RATE_SCENARIOS = {
    "base": 1.0,
    "easier_15pct": 1.15,
    "harder_15pct": 1.0 / 1.15,
    "easier_25pct": 1.25,
    "harder_25pct": 1.0 / 1.25,
}
REDUNDANCY_FLAG = 0.80
DIRECTIONAL_MAE_GATE = 0.02      # >= 2% held-out MAE reduction
DIRECTIONAL_SPEARMAN_GATE = 0.02  # or >= +0.02 held-out Spearman


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------

def _client():
    from backend.db.clients.supabase_client import public_read_client

    return public_read_client


def _paged_select(query: Any, *, page_size: int = 1000, attempts: int = 4) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        page: Optional[List[Dict[str, Any]]] = None
        last_error: Optional[Exception] = None
        for attempt in range(attempts):
            try:
                response = query.range(start, start + page_size - 1).execute()
                page = list(response.data or [])
                break
            except Exception as exc:
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(2.0 * (attempt + 1))
        if page is None:
            raise RuntimeError(f"read failed after {attempts} attempts at offset {start}") from last_error
        rows.extend(page)
        if len(page) < page_size:
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


def load_pull_rate_model(client) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """set_id -> {rarity_key: {probability, slot_group}} from the modeled pack model.

    ``slot_label`` is the mutually-exclusive slot; cards sharing it must have
    their probabilities added, never combined by an independence formula.
    """
    rows = _paged_select(
        client.table("pokemon_set_page_snapshot_latest").select("set_id,payload_json")
    )
    group_priority = {"hit_rarity_model": 0, "pack_structure": 1}
    by_set: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in rows:
        payload = row.get("payload_json")
        if not isinstance(payload, dict):
            continue
        assumptions = payload.get("pull_rate_assumptions") or payload.get("pullRateAssumptions")
        if not isinstance(assumptions, dict):
            continue
        best: Dict[str, Tuple[int, Dict[str, Any]]] = {}
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
                best[rarity_key] = (
                    priority,
                    {
                        "probability": 1.0 / denominator,
                        "slot_group": str(entry.get("slot_label") or entry.get("group") or "unknown"),
                        "card_count": entry.get("card_count"),
                        "expected_cards_per_pack": entry.get("expected_cards_per_pack"),
                    },
                )
        if best:
            by_set[str(row.get("set_id"))] = {key: value for key, (_p, value) in best.items()}
    return by_set


def load_latest_v2_rows(client) -> Dict[str, Dict[str, Any]]:
    rows = _paged_select(
        client.table("pokemon_set_desirability_component_scores")
        .select(
            "set_id,set_name,set_canonical_key,scoring_version,set_desirability_score,"
            "hit_eligible_card_count,scored_hit_eligible_card_count,unique_subject_count,"
            "subject_rollups_json,diagnostics_json,built_at"
        )
        .order("built_at", desc=True)
    )
    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        set_id = str(row.get("set_id") or "")
        if not set_id:
            continue
        kept = latest.get(set_id)
        if kept is None:
            latest[set_id] = row
        elif row.get("scoring_version") == V2_SCORING_VERSION and kept.get("scoring_version") != V2_SCORING_VERSION:
            latest[set_id] = row
    return latest


def load_cards(client, set_ids: Sequence[str]) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    for chunk in _chunked(sorted(set_ids), 5):
        cards.extend(
            _paged_select(
                client.table("pokemon_canonical_cards")
                .select("id,set_id,name,supertype,subtypes,rarity,number,printed_number")
                .in_("set_id", list(chunk))
            )
        )
    return cards


def load_prices(client, set_ids: Sequence[str]) -> Dict[str, float]:
    prices: Dict[str, float] = {}
    for chunk in _chunked(sorted(set_ids), 5):
        for row in _paged_select(
            client.table("pokemon_canonical_card_market_prices_latest")
            .select("canonical_card_id,market_price")
            .in_("set_id", list(chunk))
        ):
            price = _as_float(row.get("market_price"))
            card_id = str(row.get("canonical_card_id") or "")
            if card_id and price is not None and price > 0:
                prices[card_id] = price
    return prices


def load_appeal_by_card(client, card_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    scores = {
        int(row["pokemon_reference_id"]): row
        for row in _paged_select(
            client.table("pokemon_desirability_composite_scores")
            .select("pokemon_reference_id,pokemon_name,desirability_score")
            .eq("scoring_version", COMPOSITE_SCORING_VERSION)
        )
        if row.get("pokemon_reference_id") is not None
    }
    links_by_card: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for chunk in _chunked(sorted(card_ids), 200):
        for link in _paged_select(
            client.table("pokemon_card_desirability_links")
            .select("pokemon_canonical_card_id,pokemon_reference_id,contribution_weight")
            .in_("pokemon_canonical_card_id", list(chunk))
        ):
            links_by_card[str(link.get("pokemon_canonical_card_id"))].append(link)

    appeal: Dict[str, Dict[str, Any]] = {}
    for card_id, links in links_by_card.items():
        weighted: List[Tuple[float, float, int]] = []
        for link in links:
            try:
                reference_id = int(link.get("pokemon_reference_id"))
            except (TypeError, ValueError):
                continue
            score = _as_float((scores.get(reference_id) or {}).get("desirability_score"))
            if score is None:
                continue
            weight = _as_float(link.get("contribution_weight"))
            weight = 1.0 if weight is None else weight
            if weight <= 0:
                continue
            weighted.append((score, weight, reference_id))
        total = sum(w for _s, w, _r in weighted)
        if total <= 0:
            continue
        primary = max(weighted, key=lambda item: item[1])
        appeal[card_id] = {
            "appeal": sum(s * w for s, w, _r in weighted) / total,
            "primary_reference_id": primary[2],
            "primary_species": (scores.get(primary[2]) or {}).get("pokemon_name"),
        }
    return appeal


def load_simulation_rows(client) -> Dict[str, Dict[str, Any]]:
    rows = _paged_select(client.table("explore_rip_statistics_latest").select("*"))
    return {str(row.get("set_id")): row for row in rows if row.get("set_id")}


def load_set_values(client, set_ids: Sequence[str]) -> Dict[str, float]:
    latest: Dict[str, float] = {}
    for chunk in _chunked(sorted(set_ids), 50):
        rows = (
            client.table("pokemon_set_value_daily_history")
            .select("set_id,snapshot_date,set_value")
            .in_("set_id", list(chunk))
            .eq("value_scope", "standard")
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


# ---------------------------------------------------------------------------
# Per-set construction
# ---------------------------------------------------------------------------

def build_set_rows(
    *,
    v2_rows: Dict[str, Dict[str, Any]],
    cards: Sequence[Dict[str, Any]],
    prices: Dict[str, float],
    appeal_by_card: Dict[str, Dict[str, Any]],
    pull_model: Dict[str, Dict[str, Dict[str, Any]]],
    sets_by_id: Dict[str, Dict[str, Any]],
    simulation_rows: Dict[str, Dict[str, Any]],
    set_values: Dict[str, float],
    probability_multiplier: float = 1.0,
) -> List[Dict[str, Any]]:
    cards_by_set: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for card in cards:
        cards_by_set[str(card.get("set_id"))].append(card)

    rows: List[Dict[str, Any]] = []
    for set_id, v2_row in v2_rows.items():
        diagnostics = v2_row.get("diagnostics_json") or {}
        coverage_audit = diagnostics.get("coverage_audit") or {}
        link_counts = diagnostics.get("hit_link_category_counts") or {}
        rollups = v2_row.get("subject_rollups_json") or []
        v3 = compute_universal_set_desirability(rollups)
        coverage = assess_desirability_coverage(
            canonical_card_count=coverage_audit.get("canonical_card_count") or diagnostics.get("canonical_cards_seen"),
            hit_eligible_card_count=v2_row.get("hit_eligible_card_count"),
            scored_hit_eligible_card_count=v2_row.get("scored_hit_eligible_card_count"),
            unique_subject_count=v2_row.get("unique_subject_count"),
            unmatched_pokemon_hit_count=link_counts.get("unmatched_pokemon_hit_count"),
            true_missing_link_count=link_counts.get("true_missing_link_count"),
        )

        rarity_model = pull_model.get(set_id) or {}
        set_cards = cards_by_set.get(set_id, [])
        eligible_cards: List[Dict[str, Any]] = []
        hit_prices: List[float] = []
        all_prices: List[float] = []
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
            probability = model["probability"] * probability_multiplier
            eligible_cards.append(
                {
                    "subject_key": f"ref:{appeal_row['primary_reference_id']}",
                    "subject_name": appeal_row.get("primary_species"),
                    "subject_demand": appeal_row["appeal"],
                    "pull_probability": min(probability, 1.0),
                    "slot_group": model["slot_group"],
                    "card_name": card.get("name"),
                    "rarity": card.get("rarity"),
                    "treatment_prestige": get_treatment_score(card.get("rarity")) / 100.0,
                    "market_price": price,
                }
            )

        subjects = build_subjects(eligible_cards) if eligible_cards else []
        accessible = compute_accessible_appeal(subjects) if subjects else None
        magnetism = compute_elite_chase_magnetism(subjects) if subjects else None
        roster = v3["score"] if coverage["status"] == COVERAGE_FULL else None
        candidates = compute_opening_appeal_candidates(
            roster_appeal=roster,
            accessible_appeal=(accessible or {}).get("score"),
            elite_chase_magnetism=(magnetism or {}).get("score"),
        )

        set_row = sets_by_id.get(set_id) or {}
        simulation = simulation_rows.get(set_id) or {}
        sorted_prices = sorted(all_prices, reverse=True)
        total_priced = sum(all_prices) or None
        rows.append(
            {
                "set_id": set_id,
                "set_name": v2_row.get("set_name") or set_row.get("name"),
                "era": set_row.get("era_name"),
                "release_date": set_row.get("release_date"),
                "roster_appeal": roster,
                "accessible_appeal": (accessible or {}).get("score"),
                "elite_chase_magnetism": (magnetism or {}).get("score"),
                "accessible_detail": accessible,
                "magnetism_detail": magnetism,
                "candidates": candidates,
                "coverage": coverage["status"],
                "has_pull_model": bool(rarity_model),
                # structural
                "checklist_size": len(set_cards),
                "eligible_card_count": len(eligible_cards),
                "distinct_subject_count": len(subjects),
                "pull_rate_hit_count": len(
                    [c for c in eligible_cards if (c["pull_probability"] or 1) < 0.05]
                ),
                "treatment_prestige_mean": (
                    round(statistics.mean([c["treatment_prestige"] for c in eligible_cards]), 4)
                    if eligible_cards else None
                ),
                # financial pillars
                "profit_score": _as_float(simulation.get("profit_score")),
                "safety_score": _as_float(simulation.get("safety_score")),
                "stability_score": _as_float(simulation.get("stability_score")),
                # market outcomes (external only)
                "top_10_card_value": round(sum(sorted_prices[:10]), 2) if sorted_prices else None,
                "top_3_card_value": round(sum(sorted_prices[:3]), 2) if sorted_prices else None,
                "top_1_card_value": round(sorted_prices[0], 2) if sorted_prices else None,
                "median_hit_value": round(statistics.median(hit_prices), 2) if hit_prices else None,
                "mean_hit_value": round(statistics.mean(hit_prices), 2) if hit_prices else None,
                "set_value": set_values.get(set_id),
                "top1_value_concentration": (
                    round(sorted_prices[0] / total_priced, 6) if sorted_prices and total_priced else None
                ),
                "top3_value_concentration": (
                    round(sum(sorted_prices[:3]) / total_priced, 6) if sorted_prices and total_priced else None
                ),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def _paired(rows: Sequence[Mapping[str, Any]], x_key: str, y_key: str) -> Tuple[List[float], List[float], List[str]]:
    xs, ys, names = [], [], []
    for row in rows:
        x = _as_float(row.get(x_key)) if not isinstance(row.get(x_key), dict) else None
        y = _as_float(row.get(y_key))
        if x is None or y is None:
            continue
        xs.append(x)
        ys.append(y)
        names.append(str(row.get("set_name") or row.get("set_id")))
    return xs, ys, names


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3:
        return None
    x = np.array(xs, dtype=float)
    y = np.array(ys, dtype=float)
    if np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def bootstrap_spearman(
    xs: Sequence[float], ys: Sequence[float], *, draws: int = BOOTSTRAP_DRAWS, seed: int = RANDOM_SEED
) -> Dict[str, Optional[float]]:
    """Whole-set bootstrap: sets are the unit, so resample sets with replacement."""
    if len(xs) < 4:
        return {"ci_low": None, "ci_high": None, "draws": 0}
    rng = np.random.default_rng(seed)
    x = np.array(xs, dtype=float)
    y = np.array(ys, dtype=float)
    values: List[float] = []
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
    }


def leave_one_set_out_correlation_sensitivity(
    xs: Sequence[float], ys: Sequence[float], names: Sequence[str]
) -> Dict[str, Any]:
    """Recompute the correlation with each set removed - a tiny cohort can be
    driven entirely by one or two sets, and that must be visible."""
    if len(xs) < 5:
        return {"min": None, "median": None, "max": None, "most_influential": None}
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
    baseline = spearman(list(xs), list(ys)) or 0.0
    most = max(results, key=lambda item: abs(item[0] - baseline))
    return {
        "min": round(min(values), 4),
        "median": round(statistics.median(values), 4),
        "max": round(max(values), 4),
        "most_influential": {
            "set": most[1],
            "rho_without": round(most[0], 4),
            "shift": round(most[0] - baseline, 4),
        },
    }


# ---------------------------------------------------------------------------
# Sparse incremental models B0 / B1 / B2 with leave-whole-set-out validation
# ---------------------------------------------------------------------------

def _design_matrix(rows: Sequence[Mapping[str, Any]], columns: Sequence[str], eras: Sequence[str]) -> np.ndarray:
    pieces = [np.ones((len(rows), 1))]
    if columns:
        pieces.append(np.column_stack([[float(row[c]) for row in rows] for c in columns]))
    for era in eras[1:]:
        pieces.append(np.array([[1.0 if str(row.get("era")) == era else 0.0] for row in rows]))
    return np.hstack(pieces)


def sparse_incremental_model(
    rows: Sequence[Mapping[str, Any]],
    *,
    outcome: str,
    predictor: Optional[str],
) -> Optional[Dict[str, Any]]:
    """B0: log(Y) ~ log_release_age + log_checklist_size  (+ pooled-modern era)
       B1/B2 add exactly one appeal predictor. Deliberately sparse: n is ~20 sets.
    """
    usable = [
        row for row in rows
        if _as_float(row.get(outcome)) is not None
        and (_as_float(row.get(outcome)) or 0) > 0
        and row.get("log_release_age") is not None
        and row.get("log_checklist_size") is not None
        and (predictor is None or _as_float(row.get(predictor)) is not None)
    ]
    if len(usable) < 8:
        return None
    eras = sorted({str(row.get("era")) for row in usable})
    columns = ["log_release_age", "log_checklist_size"] + ([predictor] if predictor else [])

    set_ids = [str(row["set_id"]) for row in usable]
    predictions: List[float] = []
    actuals: List[float] = []
    per_set: List[Dict[str, Any]] = []
    for held_out in sorted(set(set_ids)):
        train = [row for row in usable if str(row["set_id"]) != held_out]
        test = [row for row in usable if str(row["set_id"]) == held_out]
        if len(train) < len(columns) + 3 or not test:
            continue
        X = _design_matrix(train, columns, eras)
        y = np.array([math.log(float(row[outcome])) for row in train])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        X_test = _design_matrix(test, columns, eras)
        y_test = np.array([math.log(float(row[outcome])) for row in test])
        y_hat = X_test @ beta
        predictions.extend(y_hat.tolist())
        actuals.extend(y_test.tolist())
        per_set.append(
            {
                "set_name": test[0].get("set_name"),
                "mae": float(np.mean(np.abs(y_test - y_hat))),
            }
        )
    if len(predictions) < 5:
        return None
    predicted = np.array(predictions)
    actual = np.array(actuals)
    errors = actual - predicted
    tss = float(np.sum((actual - actual.mean()) ** 2))
    rss = float(np.sum(errors ** 2))
    return {
        "n_sets": len(per_set),
        "mae": round(float(np.mean(np.abs(errors))), 5),
        "rmse": round(float(np.sqrt(np.mean(errors ** 2))), 5),
        "spearman": round(spearman(predicted.tolist(), actual.tolist()) or 0.0, 4),
        "r2": round(1.0 - rss / tss, 4) if tss > 0 else None,
        "macro_avg_per_set_mae": round(float(np.mean([p["mae"] for p in per_set])), 5),
        "median_per_set_mae": round(float(np.median([p["mae"] for p in per_set])), 5),
        "per_set": per_set,
    }


def compare_models(base: Optional[Dict[str, Any]], richer: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not base or not richer:
        return {"available": False}
    base_by_set = {p["set_name"]: p["mae"] for p in base["per_set"]}
    rich_by_set = {p["set_name"]: p["mae"] for p in richer["per_set"]}
    shared = sorted(set(base_by_set) & set(rich_by_set))
    deltas = [(base_by_set[s] - rich_by_set[s], s) for s in shared]
    improved = [d for d, _s in deltas if d > 0]
    mae_reduction = (base["mae"] - richer["mae"]) / base["mae"] if base["mae"] else None
    spearman_gain = richer["spearman"] - base["spearman"]
    return {
        "available": True,
        "mae_reduction_pct": round(100.0 * mae_reduction, 3) if mae_reduction is not None else None,
        "spearman_gain": round(spearman_gain, 4),
        "macro_mae_reduction_pct": round(
            100.0 * (base["macro_avg_per_set_mae"] - richer["macro_avg_per_set_mae"]) / base["macro_avg_per_set_mae"], 3
        ) if base["macro_avg_per_set_mae"] else None,
        "median_per_set_improvement": round(float(np.median([d for d, _s in deltas])), 5) if deltas else None,
        "sets_improved": len(improved),
        "sets_total": len(deltas),
        "pct_sets_improved": round(100.0 * len(improved) / len(deltas), 1) if deltas else None,
        "most_improved": [
            {"set": s, "mae_delta": round(d, 4)} for d, s in sorted(deltas, reverse=True)[:5]
        ],
        "most_harmed": [
            {"set": s, "mae_delta": round(d, 4)} for d, s in sorted(deltas)[:5]
        ],
        "meets_directional_gate": bool(
            (mae_reduction is not None and mae_reduction >= DIRECTIONAL_MAE_GATE)
            or spearman_gain >= DIRECTIONAL_SPEARMAN_GATE
        ),
    }


# ---------------------------------------------------------------------------
# Study sections
# ---------------------------------------------------------------------------

MARKET_OUTCOMES = [
    ("top_10_card_value", "Top-10 card value (primary)"),
    ("top_3_card_value", "Top-3 card value"),
    ("median_hit_value", "Median hit-eligible card value"),
    ("mean_hit_value", "Mean hit-eligible card value"),
    ("set_value", "Total checklist set value (size-sensitive)"),
    ("top1_value_concentration", "Top-1 value concentration"),
    ("top3_value_concentration", "Top-3 value concentration"),
]


def candidate_columns() -> List[str]:
    return list(OPENING_APPEAL_CANDIDATES) + [OA_BALANCED_KEY]


def flatten_candidates(rows: Sequence[Dict[str, Any]]) -> None:
    for row in rows:
        for name, value in (row.get("candidates") or {}).items():
            row[name] = value


def external_validation(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Market association of each component and candidate. Price is an OUTCOME
    only - it never entered construction, weighting, or selection."""
    predictors = ["roster_appeal", "accessible_appeal", "elite_chase_magnetism"] + candidate_columns()
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
                "loso_sensitivity": leave_one_set_out_correlation_sensitivity(xs, ys, names),
            }
        # Does any candidate beat Roster Appeal alone on this outcome?
        roster_rho = (entry["predictors"].get("roster_appeal") or {}).get("spearman")
        improvements = {}
        for candidate in candidate_columns():
            candidate_rho = (entry["predictors"].get(candidate) or {}).get("spearman")
            if roster_rho is not None and candidate_rho is not None:
                improvements[candidate] = round(candidate_rho - roster_rho, 4)
        entry["improvement_over_roster_appeal"] = improvements
        results[outcome] = entry
    return results


def incremental_market_models(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    for outcome, label in MARKET_OUTCOMES:
        b0 = sparse_incremental_model(rows, outcome=outcome, predictor=None)
        b1 = sparse_incremental_model(rows, outcome=outcome, predictor="roster_appeal")
        entry = {
            "label": label,
            "B0_controls": b0,
            "B1_roster_appeal": b1,
            "B1_vs_B0": compare_models(b0, b1),
            "B2_by_candidate": {},
        }
        for candidate in candidate_columns():
            b2 = sparse_incremental_model(rows, outcome=outcome, predictor=candidate)
            entry["B2_by_candidate"][candidate] = {
                "model": b2,
                "vs_B0": compare_models(b0, b2),
                "vs_B1_roster": compare_models(b1, b2),
            }
        results[outcome] = entry
    return results


def redundancy_matrix(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    targets = [
        "roster_appeal", "accessible_appeal", "elite_chase_magnetism",
        "profit_score", "safety_score", "stability_score",
        "checklist_size", "eligible_card_count", "distinct_subject_count",
        "pull_rate_hit_count",
    ]
    out: Dict[str, Any] = {}
    for predictor in ["accessible_appeal", "elite_chase_magnetism"] + candidate_columns():
        entry = {}
        for target in targets:
            if target == predictor:
                continue
            xs, ys, _n = _paired(rows, predictor, target)
            rho = spearman(xs, ys)
            entry[target] = {
                "n": len(xs),
                "spearman": round(rho, 4) if rho is not None else None,
                "redundancy_flag": bool(rho is not None and abs(rho) > REDUNDANCY_FLAG),
            }
        out[predictor] = entry
    return out


def rip_effect(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Current RIP (10% universal desirability) vs RIP with Opening Appeal at
    5 / 10 / 15%, for every candidate."""
    def rank(values: Dict[str, Optional[float]]) -> Dict[str, Optional[int]]:
        scored = sorted(
            [(k, v) for k, v in values.items() if v is not None], key=lambda item: (-item[1], item[0])
        )
        ranks = {k: None for k in values}
        for position, (k, _v) in enumerate(scored, start=1):
            ranks[k] = position
        return ranks

    def rip_scores(appeal_key: Optional[str], weight: float) -> Dict[str, Optional[float]]:
        out: Dict[str, Optional[float]] = {}
        for row in rows:
            appeal = _as_float(row.get(appeal_key)) if appeal_key else None
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

    baseline = rip_scores("roster_appeal", 0.10)
    baseline_ranks = rank(baseline)
    baseline_top10 = {k for k, v in baseline_ranks.items() if v and v <= 10}

    comparisons: Dict[str, Any] = {}
    for candidate in candidate_columns():
        for weight in (0.05, 0.10, 0.15):
            scores = rip_scores(candidate, weight)
            ranks = rank(scores)
            movers = []
            deltas = []
            for name, base_rank in baseline_ranks.items():
                new_rank = ranks.get(name)
                if base_rank is None or new_rank is None:
                    continue
                delta = base_rank - new_rank
                deltas.append(delta)
                score_delta = (
                    (scores[name] - baseline[name])
                    if scores.get(name) is not None and baseline.get(name) is not None
                    else None
                )
                movers.append({"set": name, "rank_delta": delta, "score_delta": round(score_delta, 3) if score_delta is not None else None})
            top10 = {k for k, v in ranks.items() if v and v <= 10}
            comparisons[f"{candidate}@{int(weight*100)}%"] = {
                "max_abs_rank_delta": max((abs(d) for d in deltas), default=0),
                "mean_abs_rank_delta": round(float(np.mean([abs(d) for d in deltas])), 3) if deltas else None,
                "top10_entered": sorted(top10 - baseline_top10),
                "top10_left": sorted(baseline_top10 - top10),
                "largest_movers": sorted(movers, key=lambda m: -abs(m["rank_delta"]))[:5],
            }
    return {
        "baseline": "RIP with 10% Universal Roster Appeal (current shipping structure)",
        "comparisons": comparisons,
    }


def candidate_diagnostics(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    columns = candidate_columns()
    for candidate in columns:
        values = [_as_float(row.get(candidate)) for row in rows]
        values = [v for v in values if v is not None]
        if not values:
            continue
        pairwise = {}
        for other in columns:
            if other == candidate:
                continue
            xs, ys, _n = _paired(rows, candidate, other)
            rho = spearman(xs, ys)
            pairwise[other] = round(rho, 4) if rho is not None else None
        out[candidate] = {
            "n": len(values),
            "mean": round(statistics.mean(values), 3),
            "median": round(statistics.median(values), 3),
            "stdev": round(statistics.stdev(values), 3) if len(values) > 1 else 0.0,
            "min": round(min(values), 3),
            "max": round(max(values), 3),
            "rank_correlation_with_other_candidates": pairwise,
        }
    return out


def sensitivity_variants(base_rows: Sequence[Dict[str, Any]], all_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Magnetism/accessibility structural sensitivity: slot counts and anchors."""
    from backend.desirability.opening_appeal import (
        compute_accessible_appeal as aa,
        compute_elite_chase_magnetism as ecm,
    )

    variants: Dict[str, Any] = {}
    configs = {
        "magnetism_top1": {"slot_weights": (1.0,)},
        "magnetism_top3_default": {"slot_weights": (0.5, 0.3, 0.2)},
        "magnetism_top5": {"slot_weights": (0.4, 0.25, 0.15, 0.12, 0.08)},
        "anchors_1in5_to_1in500": {"easy_probability": 0.2, "elite_probability": 0.002},
        "anchors_1in20_to_1in2000": {"easy_probability": 0.05, "elite_probability": 0.0005},
    }
    baseline_by_set = {row["set_id"]: row.get("elite_chase_magnetism") for row in base_rows}
    accessible_baseline = {row["set_id"]: row.get("accessible_appeal") for row in base_rows}

    for name, config in configs.items():
        magnetism_scores: Dict[str, Optional[float]] = {}
        accessible_scores: Dict[str, Optional[float]] = {}
        for set_id, subjects in all_inputs.items():
            if not subjects:
                continue
            slot_weights = config.get("slot_weights", (0.5, 0.3, 0.2))
            anchor_kwargs = {
                k: v for k, v in config.items() if k in {"easy_probability", "elite_probability"}
            }
            m = ecm(subjects, slot_weights=slot_weights, **anchor_kwargs)
            a = aa(subjects, **anchor_kwargs)
            magnetism_scores[set_id] = (m or {}).get("score")
            accessible_scores[set_id] = (a or {}).get("score")

        def rank_corr(new: Dict[str, Optional[float]], base: Dict[str, Optional[float]]) -> Optional[float]:
            shared = [k for k in new if new.get(k) is not None and base.get(k) is not None]
            if len(shared) < 4:
                return None
            rho = spearman([new[k] for k in shared], [base[k] for k in shared])
            return round(rho, 4) if rho is not None else None

        variants[name] = {
            "magnetism_rank_spearman_vs_default": rank_corr(magnetism_scores, baseline_by_set),
            "accessible_rank_spearman_vs_default": rank_corr(accessible_scores, accessible_baseline),
        }
    return variants


def treatment_prestige_diagnostics(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Phase 9: prestige stays OUTSIDE Opening Appeal this pass; report only."""
    out: Dict[str, Any] = {}
    for target in ("elite_chase_magnetism", "accessible_appeal", "roster_appeal"):
        xs, ys, _n = _paired(rows, "treatment_prestige_mean", target)
        rho = spearman(xs, ys)
        out[f"treatment_prestige_vs_{target}"] = {
            "n": len(xs),
            "spearman": round(rho, 4) if rho is not None else None,
            "redundancy_flag": bool(rho is not None and abs(rho) > REDUNDANCY_FLAG),
        }
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(Path("docs") / "research" / "opening_appeal_study.json"))
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

    client = _client()
    logger.info("Loading modeled pull-rate pack model...")
    pull_model = load_pull_rate_model(client)
    v2_rows = load_latest_v2_rows(client)
    set_rows_raw = _paged_select(client.table("sets").select("id,name,canonical_key,release_date,era_id"))
    eras = {str(r["id"]): str(r.get("name") or "") for r in _paged_select(client.table("eras").select("id,name"))}
    sets_by_id = {str(r["id"]): {**r, "era_name": eras.get(str(r.get("era_id") or ""))} for r in set_rows_raw}
    simulation_rows = load_simulation_rows(client)

    covered = sorted(set(pull_model) & set(v2_rows))
    logger.info("Sets with modeled pull data + V2 rollups: %s", len(covered))
    cards = load_cards(client, covered)
    prices = load_prices(client, covered)
    appeal_by_card = load_appeal_by_card(client, [str(c["id"]) for c in cards])
    set_values = load_set_values(client, covered)

    v2_covered = {set_id: v2_rows[set_id] for set_id in covered}
    rows = build_set_rows(
        v2_rows=v2_covered,
        cards=cards,
        prices=prices,
        appeal_by_card=appeal_by_card,
        pull_model=pull_model,
        sets_by_id=sets_by_id,
        simulation_rows=simulation_rows,
        set_values=set_values,
    )
    flatten_candidates(rows)
    for row in rows:
        row["log_checklist_size"] = math.log(max(row["checklist_size"], 1))
        try:
            release = datetime.fromisoformat(str(row.get("release_date"))).date()
            age = max((datetime.now(timezone.utc).date() - release).days, 1)
        except (TypeError, ValueError):
            age = None
        row["log_release_age"] = math.log(age) if age else None

    scored = [row for row in rows if row.get("accessible_appeal") is not None and row.get("roster_appeal") is not None]
    logger.info("Sets with a full Opening Appeal candidate: %s", len(scored))

    # Subjects per set for structural sensitivity variants.
    subject_inputs: Dict[str, Any] = {}
    for row in rows:
        detail = row.get("magnetism_detail")
        if detail:
            subject_inputs[row["set_id"]] = None  # replaced below

    # Rebuild subjects once for sensitivity (cheap relative to IO).
    rebuilt: Dict[str, Any] = {}
    cards_by_set: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for card in cards:
        cards_by_set[str(card.get("set_id"))].append(card)
    for row in scored:
        set_id = row["set_id"]
        rarity_model = pull_model.get(set_id) or {}
        eligible = []
        for card in cards_by_set.get(set_id, []):
            classification = classify_rarity(card.get("rarity"))
            if classification.bucket not in HIT_BUCKETS:
                continue
            appeal_row = appeal_by_card.get(str(card.get("id") or ""))
            model = rarity_model.get(classification.normalized_key)
            if appeal_row is None or model is None:
                continue
            eligible.append(
                {
                    "subject_key": f"ref:{appeal_row['primary_reference_id']}",
                    "subject_name": appeal_row.get("primary_species"),
                    "subject_demand": appeal_row["appeal"],
                    "pull_probability": model["probability"],
                    "slot_group": model["slot_group"],
                    "card_name": card.get("name"),
                    "rarity": card.get("rarity"),
                }
            )
        rebuilt[set_id] = build_subjects(eligible) if eligible else []

    logger.info("Running pull-rate uncertainty scenarios...")
    scenarios: Dict[str, Any] = {}
    baseline_rank_source = {row["set_id"]: row for row in scored}
    for name, multiplier in PULL_RATE_SCENARIOS.items():
        scenario_rows = build_set_rows(
            v2_rows=v2_covered,
            cards=cards,
            prices=prices,
            appeal_by_card=appeal_by_card,
            pull_model=pull_model,
            sets_by_id=sets_by_id,
            simulation_rows=simulation_rows,
            set_values=set_values,
            probability_multiplier=multiplier,
        )
        flatten_candidates(scenario_rows)
        scenario_scored = [r for r in scenario_rows if r.get("accessible_appeal") is not None]

        def rank_corr(key: str) -> Optional[float]:
            shared = [
                (r, baseline_rank_source.get(r["set_id"]))
                for r in scenario_scored
                if baseline_rank_source.get(r["set_id"]) is not None
            ]
            xs = [_as_float(a.get(key)) for a, b in shared]
            ys = [_as_float(b.get(key)) for a, b in shared]
            pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
            if len(pairs) < 4:
                return None
            rho = spearman([p[0] for p in pairs], [p[1] for p in pairs])
            return round(rho, 4) if rho is not None else None

        movers = []
        for r in scenario_scored:
            base = baseline_rank_source.get(r["set_id"])
            if not base:
                continue
            delta = (_as_float(r.get("OA_60_20_20")) or 0) - (_as_float(base.get("OA_60_20_20")) or 0)
            movers.append({"set": r.get("set_name"), "oa_delta": round(delta, 3)})
        scenarios[name] = {
            "multiplier": multiplier,
            "accessible_rank_spearman_vs_base": rank_corr("accessible_appeal"),
            "magnetism_rank_spearman_vs_base": rank_corr("elite_chase_magnetism"),
            "oa_60_20_20_rank_spearman_vs_base": rank_corr("OA_60_20_20"),
            "most_sensitive_sets": sorted(movers, key=lambda m: -abs(m["oa_delta"]))[:5],
        }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "study": "opening_appeal_candidate_v1_research",
        "rules": [
            "Price is an external outcome only; it never enters construction, normalization, weighting, or selection.",
            "No Opening Appeal weight is fitted to price.",
            "Universal Roster Appeal is unchanged and remains the all-set score; scarcity/accessibility are never merged into it.",
            "Pull input is modeledPullScarcity, never observed 'actual' scarcity.",
        ],
        "cohort": {
            "sets_with_pull_model": len(covered),
            "sets_scored": len(scored),
            "eras": sorted({str(r.get("era")) for r in scored}),
            "era_counts": {
                era: sum(1 for r in scored if str(r.get("era")) == era)
                for era in sorted({str(r.get("era")) for r in scored})
            },
        },
        "set_rows": [
            {
                k: v for k, v in row.items()
                if k not in {"accessible_detail", "magnetism_detail", "candidates"}
            }
            for row in sorted(scored, key=lambda r: -(r.get("OA_60_20_20") or 0))
        ],
        "candidate_diagnostics": candidate_diagnostics(scored),
        "external_validation": external_validation(scored),
        "incremental_market_models": incremental_market_models(scored),
        "redundancy": redundancy_matrix(scored),
        "rip_effect": rip_effect(scored),
        "pull_rate_scenarios": scenarios,
        "structural_sensitivity": sensitivity_variants(scored, rebuilt),
        "treatment_prestige": treatment_prestige_diagnostics(scored),
        "top_sets_detail": [
            {
                "set_name": row.get("set_name"),
                "roster": row.get("roster_appeal"),
                "accessible": row.get("accessible_appeal"),
                "magnetism": row.get("elite_chase_magnetism"),
                "OA_60_20_20": row.get("OA_60_20_20"),
                "accessible_top_contributors": ((row.get("accessible_detail") or {}).get("top_contributors") or [])[:3],
                "magnetism_top_subjects": [
                    {
                        "subject": s.get("subject_name"),
                        "magnetism": s.get("subject_magnetism"),
                        "card": (s.get("driving_card") or {}).get("card_name"),
                        "one_in_x": (s.get("driving_card") or {}).get("one_in_x"),
                    }
                    for s in ((row.get("magnetism_detail") or {}).get("top_subjects") or [])
                ],
            }
            for row in sorted(scored, key=lambda r: -(r.get("OA_60_20_20") or 0))[:8]
        ],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _print_summary(report)
    print(f"\nReport written to {out_path}")
    return 0


def _print_summary(report: Dict[str, Any]) -> None:
    print(f"\nCohort: {report['cohort']['sets_scored']} scored sets | eras: {report['cohort']['era_counts']}")
    print("\n--- Candidate rank correlations (are the candidates the same ranking?) ---")
    for name, entry in report["candidate_diagnostics"].items():
        print(f"  {name:<14} mean={entry['mean']:<6} sd={entry['stdev']:<6} corr_others={entry['rank_correlation_with_other_candidates']}")
    print("\n--- External validation: Spearman vs market outcomes ---")
    for outcome, entry in report["external_validation"].items():
        preds = entry["predictors"]
        roster = (preds.get("roster_appeal") or {}).get("spearman")
        line = f"  {outcome:<28} roster={roster}"
        for c in candidate_columns():
            line += f" {c}={(preds.get(c) or {}).get('spearman')}"
        print(line)
        print(f"      improvement over roster: {entry['improvement_over_roster_appeal']}")
    print("\n--- Incremental models (B2 vs B1 roster) on primary outcome ---")
    primary = report["incremental_market_models"].get("top_10_card_value") or {}
    for candidate, entry in (primary.get("B2_by_candidate") or {}).items():
        vs_b1 = entry.get("vs_B1_roster") or {}
        print(
            f"  {candidate:<14} mae%={vs_b1.get('mae_reduction_pct')} rho+={vs_b1.get('spearman_gain')} "
            f"sets_improved={vs_b1.get('sets_improved')}/{vs_b1.get('sets_total')} gate={vs_b1.get('meets_directional_gate')}"
        )
    print("\n--- Redundancy flags ---")
    for predictor, entry in report["redundancy"].items():
        flagged = [f"{k}({v['spearman']})" for k, v in entry.items() if v.get("redundancy_flag")]
        print(f"  {predictor:<14} flags: {flagged or 'none'}")
    print("\n--- Pull-rate scenarios ---")
    for name, entry in report["pull_rate_scenarios"].items():
        print(
            f"  {name:<14} accessible_rho={entry['accessible_rank_spearman_vs_base']} "
            f"magnetism_rho={entry['magnetism_rank_spearman_vs_base']} oa_rho={entry['oa_60_20_20_rank_spearman_vs_base']}"
        )
    print("\n--- RIP effect (vs current 10% roster appeal) ---")
    for name, entry in report["rip_effect"]["comparisons"].items():
        print(
            f"  {name:<22} max_abs_rank_delta={entry['max_abs_rank_delta']} mean_abs_rank_delta={entry['mean_abs_rank_delta']} "
            f"top10_in={entry['top10_entered']} top10_out={entry['top10_left']}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
