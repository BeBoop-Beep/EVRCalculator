"""Card-level market amplification study (READ-ONLY, research).

Asks whether price-independent Pokemon Appeal carries information about card
price *beyond* structural controls and ACTUAL pull scarcity, and whether
scarcity amplifies appeal.

This study - not the raw set-level desirability-vs-set-value correlation - is
the construct validation for Universal Set Desirability. The set-level
correlation is a descriptive diagnostic only: a deliberately price-independent
score is not expected to reproduce price, which is jointly produced by demand,
scarcity, prestige, supply, and age. Gating the score on that correlation would
optimize it back toward price contamination.

Definitions
-----------
appeal              Pure Pokemon Demand (0-100), price-independent
                    (0.75*fan_popularity + 0.25*current_trend), mapped to a
                    card as the contribution-weighted mean over linked species.
pull_scarcity       -log10(P(specific card in one pack)), from the set's
                    modeled pull-rate assumptions (1 / specific_card_odds_denominator).
treatment_prestige  Normalized categorical rarity/treatment designation
                    (get_treatment_score/100), kept SEPARATE from actual pull odds.
outcome             log(card market price).

Nested models (weights are never chosen by hand before testing)
---------------------------------------------------------------
M0  controls only
M1  M0 + appeal
M2  M0 + pull_scarcity
M3  M0 + appeal + pull_scarcity
M4  M3 + appeal x pull_scarcity
M5  M4 + treatment_prestige

Inference uses set fixed effects with cluster-robust (by set) standard errors,
plus a cluster bootstrap by set. Model comparison uses leave-WHOLE-SET-out
grouped cross-validation (never random card splits); held-out sets have no set
intercept, so the CV specification uses era + structural controls in place of
set dummies.

Nothing here is committed, and no coefficient from this study may be
transferred into RIP weights: these fit price, not user utility.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.calculations.utils.rarity_classification import normalize_rarity_key  # noqa: E402
from backend.desirability.card_appeal import get_treatment_score  # noqa: E402
from backend.desirability.composite import COMPOSITE_SCORING_VERSION  # noqa: E402

logger = logging.getLogger(__name__)

MIN_SETS_PER_ERA = 4          # below this, leave-whole-set-out CV is not credible
MIN_CARDS_PER_ERA = 200
BOOTSTRAP_DRAWS = 400
RANDOM_SEED = 20260715


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _client():
    from backend.db.clients.supabase_client import public_read_client

    return public_read_client


def _paged_select(query: Any, *, page_size: int = 1000, attempts: int = 4) -> List[Dict[str, Any]]:
    """Paged read with retries.

    Supabase intermittently returns read timeouts / statement timeouts on the
    larger tables here, so each page is retried with backoff. A page that still
    fails raises rather than silently truncating the study sample.
    """
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
            except Exception as exc:  # transient timeouts / 5xx
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


def load_pull_rate_tables(client) -> Dict[str, Dict[str, float]]:
    """set_id -> {normalized_rarity_key: specific_card_pull_probability}.

    Rows are keyed by rarity within a set, so pull scarcity is constant within
    (set, rarity) - appeal still varies within that cell, which is what
    identifies the appeal and interaction terms.
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


def load_cards(client, set_ids: Sequence[str]) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    for chunk in _chunked(sorted(set_ids), 50):
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
    """Contribution-weighted Pure Demand per card, plus its primary species."""
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
            reference_id = link.get("pokemon_reference_id")
            try:
                reference_id = int(reference_id)
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
        total = sum(weight for _s, weight, _r in weighted)
        if total <= 0:
            continue
        primary = max(weighted, key=lambda item: item[1])
        appeal[card_id] = {
            "appeal": sum(score * weight for score, weight, _r in weighted) / total,
            "primary_reference_id": primary[2],
            "primary_species": (scores.get(primary[2]) or {}).get("pokemon_name"),
        }
    return appeal


# ---------------------------------------------------------------------------
# Feature construction
# ---------------------------------------------------------------------------

def _card_number(card: Dict[str, Any]) -> Optional[int]:
    raw = str(card.get("printed_number") or card.get("number") or "")
    digits = "".join(ch for ch in raw.split("/")[0] if ch.isdigit())
    return int(digits) if digits else None


def _printed_set_size(card: Dict[str, Any]) -> Optional[int]:
    """Set size from the printed denominator, e.g. "245/91" -> 91.

    The denominator is the printed set size, so a card numbered above it is a
    secret. Deriving the size from the max numerator instead would be wrong:
    the max numerator IS a secret, which would make ``is_secret`` always 0.
    """
    raw = str(card.get("printed_number") or "")
    if "/" not in raw:
        return None
    digits = "".join(ch for ch in raw.split("/", 1)[1] if ch.isdigit())
    return int(digits) if digits else None


def _is_secret(card: Dict[str, Any], set_size_by_set: Dict[str, int]) -> int:
    number = _card_number(card)
    set_size = set_size_by_set.get(str(card.get("set_id")))
    if number is None or not set_size:
        return 0
    return 1 if number > set_size else 0


def _subtype_flags(card: Dict[str, Any]) -> Dict[str, int]:
    subtypes = card.get("subtypes") if isinstance(card.get("subtypes"), list) else []
    normalized = {str(item).strip().lower() for item in subtypes}
    return {
        "is_promo": 1 if "promo" in normalized else 0,
        "is_mechanic_card": 1 if normalized & {"ex", "gx", "v", "vmax", "vstar", "mega"} else 0,
        "is_stage2": 1 if "stage 2" in normalized else 0,
    }


def build_rows(
    *,
    cards: Sequence[Dict[str, Any]],
    prices: Dict[str, float],
    appeal_by_card: Dict[str, Dict[str, Any]],
    pull_rates: Dict[str, Dict[str, float]],
    sets_by_id: Dict[str, Dict[str, Any]],
    as_of: date,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    # Printed denominators are the authoritative set size; take the modal one
    # per set so a single malformed number cannot move it.
    denominators_by_set: Dict[str, List[int]] = defaultdict(list)
    for card in cards:
        size = _printed_set_size(card)
        if size:
            denominators_by_set[str(card.get("set_id"))].append(size)
    set_size_by_set: Dict[str, int] = {}
    for set_id, sizes in denominators_by_set.items():
        set_size_by_set[set_id] = max(set(sizes), key=sizes.count)

    rows: List[Dict[str, Any]] = []
    dropped = defaultdict(int)
    for card in cards:
        card_id = str(card.get("id") or "")
        set_id = str(card.get("set_id") or "")
        price = prices.get(card_id)
        if price is None:
            dropped["no_price"] += 1
            continue
        appeal_row = appeal_by_card.get(card_id)
        if appeal_row is None:
            dropped["no_appeal_link"] += 1
            continue
        rarity_key = normalize_rarity_key(str(card.get("rarity") or ""))
        if not rarity_key:
            dropped["no_rarity"] += 1
            continue
        probability = (pull_rates.get(set_id) or {}).get(rarity_key)
        if probability is None or probability <= 0:
            dropped["no_pull_rate_for_rarity"] += 1
            continue

        set_row = sets_by_id.get(set_id) or {}
        release = set_row.get("release_date")
        try:
            release_date = datetime.fromisoformat(str(release)).date()
            age_days = max((as_of - release_date).days, 0)
        except (TypeError, ValueError):
            dropped["no_release_date"] += 1
            continue

        flags = _subtype_flags(card)
        rows.append(
            {
                "card_id": card_id,
                "card_name": card.get("name"),
                "set_id": set_id,
                "set_name": set_row.get("name"),
                "era": set_row.get("era_name"),
                "rarity_key": rarity_key,
                "log_price": math.log(price),
                "market_price": price,
                "appeal": appeal_row["appeal"],
                "primary_species": appeal_row.get("primary_species"),
                "primary_reference_id": appeal_row.get("primary_reference_id"),
                "pull_probability": probability,
                "pull_scarcity": -math.log10(probability),
                "treatment_prestige": get_treatment_score(card.get("rarity")) / 100.0,
                "log_release_age": math.log1p(age_days),
                "is_secret": _is_secret(card, set_size_by_set),
                **flags,
            }
        )
    return rows, dict(dropped)


# ---------------------------------------------------------------------------
# Estimation: OLS with absorbed set fixed effects + cluster-robust inference
# ---------------------------------------------------------------------------

CONTROL_COLUMNS = ["log_release_age", "is_secret", "is_promo", "is_mechanic_card", "is_stage2"]


def _design(rows: Sequence[Dict[str, Any]], columns: Sequence[str]) -> np.ndarray:
    if not columns:
        return np.empty((len(rows), 0))
    return np.column_stack([[float(row[column]) for row in rows] for column in columns])


def _demean_by_group(matrix: np.ndarray, groups: Sequence[str]) -> np.ndarray:
    """Absorb group fixed effects by within-group demeaning."""
    if matrix.size == 0:
        return matrix
    out = np.array(matrix, dtype=float, copy=True)
    index_by_group: Dict[str, List[int]] = defaultdict(list)
    for index, group in enumerate(groups):
        index_by_group[group].append(index)
    for indices in index_by_group.values():
        out[indices] -= out[indices].mean(axis=0)
    return out


def _drop_constant_columns(matrix: np.ndarray, names: Sequence[str]) -> Tuple[np.ndarray, List[str], List[str]]:
    keep, dropped = [], []
    for index, name in enumerate(names):
        column = matrix[:, index]
        if np.std(column) > 1e-10:
            keep.append(index)
        else:
            dropped.append(name)
    return matrix[:, keep], [names[i] for i in keep], dropped


def fit_within_ols(
    rows: Sequence[Dict[str, Any]],
    columns: Sequence[str],
) -> Optional[Dict[str, Any]]:
    """Set-fixed-effects OLS with cluster-robust (by set) standard errors."""
    if len(rows) <= len(columns) + 2:
        return None
    groups = [row["set_id"] for row in rows]
    y = np.array([row["log_price"] for row in rows], dtype=float)
    X_raw = _design(rows, columns)
    y_within = _demean_by_group(y.reshape(-1, 1), groups).ravel()
    X_within = _demean_by_group(X_raw, groups)
    X_within, kept_names, dropped_names = _drop_constant_columns(X_within, list(columns))
    if X_within.shape[1] == 0:
        return None

    beta, *_ = np.linalg.lstsq(X_within, y_within, rcond=None)
    residuals = y_within - X_within @ beta
    n, k = X_within.shape
    unique_groups = sorted(set(groups))
    n_groups = len(unique_groups)

    xtx_inv = np.linalg.pinv(X_within.T @ X_within)
    meat = np.zeros((k, k))
    for group in unique_groups:
        indices = [i for i, g in enumerate(groups) if g == group]
        Xg = X_within[indices]
        ug = residuals[indices]
        score = Xg.T @ ug
        meat += np.outer(score, score)
    dof = n - k - n_groups
    correction = (n_groups / max(n_groups - 1, 1)) * ((n - 1) / max(dof, 1))
    vcov = xtx_inv @ meat @ xtx_inv * correction
    stderr = np.sqrt(np.maximum(np.diag(vcov), 0.0))

    tss = float(np.sum((y_within - y_within.mean()) ** 2))
    rss = float(np.sum(residuals ** 2))
    within_r2 = 1.0 - rss / tss if tss > 0 else None

    return {
        "columns": kept_names,
        "dropped_collinear_columns": dropped_names,
        "coefficients": {name: float(beta[i]) for i, name in enumerate(kept_names)},
        "cluster_robust_se": {name: float(stderr[i]) for i, name in enumerate(kept_names)},
        "t_stats": {
            name: (float(beta[i] / stderr[i]) if stderr[i] > 0 else None)
            for i, name in enumerate(kept_names)
        },
        "n": n,
        "n_sets": n_groups,
        "within_r2": within_r2,
    }


def cluster_bootstrap(
    rows: Sequence[Dict[str, Any]],
    columns: Sequence[str],
    *,
    draws: int = BOOTSTRAP_DRAWS,
    seed: int = RANDOM_SEED,
) -> Dict[str, Dict[str, Optional[float]]]:
    """Percentile CIs from resampling whole sets with replacement."""
    rng = np.random.default_rng(seed)
    rows_by_set: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rows_by_set[row["set_id"]].append(row)
    set_ids = sorted(rows_by_set)
    if len(set_ids) < 3:
        return {}

    samples: Dict[str, List[float]] = defaultdict(list)
    for _ in range(draws):
        picked = rng.choice(len(set_ids), size=len(set_ids), replace=True)
        boot_rows: List[Dict[str, Any]] = []
        for offset, index in enumerate(picked):
            # Re-label duplicated sets so each draw is its own cluster.
            for row in rows_by_set[set_ids[index]]:
                boot_rows.append({**row, "set_id": f"{row['set_id']}__{offset}"})
        fit = fit_within_ols(boot_rows, columns)
        if fit is None:
            continue
        for name, value in fit["coefficients"].items():
            samples[name].append(value)

    result: Dict[str, Dict[str, Optional[float]]] = {}
    for name, values in samples.items():
        if len(values) < 20:
            result[name] = {"ci_low": None, "ci_high": None, "draws": len(values)}
            continue
        array = np.array(values)
        result[name] = {
            "ci_low": float(np.percentile(array, 2.5)),
            "ci_high": float(np.percentile(array, 97.5)),
            "draws": len(values),
            "share_positive": float(np.mean(array > 0)),
        }
    return result


# ---------------------------------------------------------------------------
# Leave-whole-set-out cross-validation
# ---------------------------------------------------------------------------

def _spearman(x: np.ndarray, y: np.ndarray) -> Optional[float]:
    if len(x) < 3:
        return None
    from scipy.stats import spearmanr

    rho = spearmanr(x, y).statistic
    return float(rho) if rho is not None and math.isfinite(rho) else None


def leave_one_set_out_cv(
    rows: Sequence[Dict[str, Any]],
    columns: Sequence[str],
    *,
    era_dummies: bool = True,
) -> Optional[Dict[str, Any]]:
    """Grouped CV: train on all-but-one set, predict the held-out set.

    A held-out set has no set intercept, so the CV specification uses era
    dummies plus structural controls instead of set fixed effects. This is the
    honest generalization test - random card splits would leak set-level price
    level through cards of the same set.
    """
    set_ids = sorted({row["set_id"] for row in rows})
    if len(set_ids) < 3:
        return None
    eras = sorted({str(row.get("era") or "") for row in rows})
    use_eras = era_dummies and len(eras) > 1

    def design(subset: Sequence[Dict[str, Any]]) -> np.ndarray:
        base = _design(subset, columns)
        pieces = [np.ones((len(subset), 1)), base]
        if use_eras:
            for era in eras[1:]:
                pieces.append(
                    np.array([[1.0 if str(row.get("era") or "") == era else 0.0] for row in subset])
                )
        return np.hstack(pieces)

    predictions: List[float] = []
    actuals: List[float] = []
    per_set: List[Dict[str, Any]] = []
    for held_out in set_ids:
        train = [row for row in rows if row["set_id"] != held_out]
        test = [row for row in rows if row["set_id"] == held_out]
        if len(train) <= len(columns) + 5 or not test:
            continue
        X_train = design(train)
        y_train = np.array([row["log_price"] for row in train])
        beta, *_ = np.linalg.lstsq(X_train, y_train, rcond=None)
        X_test = design(test)
        y_test = np.array([row["log_price"] for row in test])
        y_hat = X_test @ beta
        predictions.extend(y_hat.tolist())
        actuals.extend(y_test.tolist())
        per_set.append(
            {
                "set_name": test[0].get("set_name"),
                "n": len(test),
                "mae": float(np.mean(np.abs(y_test - y_hat))),
            }
        )

    if not predictions:
        return None
    predicted = np.array(predictions)
    actual = np.array(actuals)
    errors = actual - predicted
    tss = float(np.sum((actual - actual.mean()) ** 2))
    rss = float(np.sum(errors ** 2))
    return {
        "n": len(actual),
        "n_folds": len(per_set),
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
        "spearman": _spearman(predicted, actual),
        "r2": (1.0 - rss / tss) if tss > 0 else None,
        "worst_sets": sorted(per_set, key=lambda item: -item["mae"])[:5],
    }


# ---------------------------------------------------------------------------
# Model suite
# ---------------------------------------------------------------------------

def model_specs() -> Dict[str, List[str]]:
    controls = list(CONTROL_COLUMNS)
    return {
        "M0_controls_only": controls,
        "M1_appeal": controls + ["appeal_c"],
        "M2_scarcity": controls + ["pull_scarcity_c"],
        "M3_appeal_scarcity": controls + ["appeal_c", "pull_scarcity_c"],
        "M4_interaction": controls + ["appeal_c", "pull_scarcity_c", "appeal_x_scarcity"],
        "M5_plus_prestige": controls + ["appeal_c", "pull_scarcity_c", "appeal_x_scarcity", "treatment_prestige"],
    }


def add_centered_terms(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    """Center appeal and scarcity so the interaction's main effects stay
    interpretable at the sample mean."""
    appeal_mean = float(np.mean([row["appeal"] for row in rows]))
    scarcity_mean = float(np.mean([row["pull_scarcity"] for row in rows]))
    for row in rows:
        row["appeal_c"] = row["appeal"] - appeal_mean
        row["pull_scarcity_c"] = row["pull_scarcity"] - scarcity_mean
        row["appeal_x_scarcity"] = row["appeal_c"] * row["pull_scarcity_c"]
    return {"appeal_mean": appeal_mean, "pull_scarcity_mean": scarcity_mean}


def run_model_suite(rows: List[Dict[str, Any]], *, label: str, bootstrap: bool) -> Dict[str, Any]:
    centering = add_centered_terms(rows)
    specs = model_specs()
    results: Dict[str, Any] = {}
    for name, columns in specs.items():
        fit = fit_within_ols(rows, columns)
        cv = leave_one_set_out_cv(rows, columns)
        entry: Dict[str, Any] = {"fixed_effects_fit": fit, "leave_whole_set_out_cv": cv}
        if bootstrap and name in {"M3_appeal_scarcity", "M4_interaction", "M5_plus_prestige"}:
            entry["cluster_bootstrap_ci"] = cluster_bootstrap(rows, columns)
        results[name] = entry

    def cv_metric(name: str, metric: str) -> Optional[float]:
        cv = (results.get(name) or {}).get("leave_whole_set_out_cv") or {}
        return cv.get(metric)

    def lift(base: str, richer: str) -> Dict[str, Optional[float]]:
        base_mae, rich_mae = cv_metric(base, "mae"), cv_metric(richer, "mae")
        base_rho, rich_rho = cv_metric(base, "spearman"), cv_metric(richer, "spearman")
        return {
            "mae_reduction": (base_mae - rich_mae) if base_mae and rich_mae else None,
            "mae_reduction_pct": (
                100.0 * (base_mae - rich_mae) / base_mae if base_mae and rich_mae else None
            ),
            "spearman_gain": (rich_rho - base_rho) if base_rho is not None and rich_rho is not None else None,
        }

    return {
        "label": label,
        "n_cards": len(rows),
        "n_sets": len({row["set_id"] for row in rows}),
        "n_species": len({row.get("primary_reference_id") for row in rows}),
        "centering": centering,
        "models": results,
        "incremental_lift_out_of_sample": {
            "appeal_over_controls (M1 vs M0)": lift("M0_controls_only", "M1_appeal"),
            "scarcity_over_controls (M2 vs M0)": lift("M0_controls_only", "M2_scarcity"),
            "appeal_over_scarcity (M3 vs M2)": lift("M2_scarcity", "M3_appeal_scarcity"),
            "scarcity_over_appeal (M3 vs M1)": lift("M1_appeal", "M3_appeal_scarcity"),
            "interaction_over_additive (M4 vs M3)": lift("M3_appeal_scarcity", "M4_interaction"),
            "prestige_over_interaction (M5 vs M4)": lift("M4_interaction", "M5_plus_prestige"),
        },
    }


# ---------------------------------------------------------------------------
# Visualization support (buckets are for plotting only; the continuous
# interaction model remains the inferential source of truth)
# ---------------------------------------------------------------------------

def build_visualization(rows: Sequence[Dict[str, Any]], *, buckets: int = 3) -> Dict[str, Any]:
    scarcity = np.array([row["pull_scarcity"] for row in rows])
    edges = np.quantile(scarcity, np.linspace(0, 1, buckets + 1))
    bucket_rows: List[Dict[str, Any]] = []
    for index in range(buckets):
        low, high = edges[index], edges[index + 1]
        if index == buckets - 1:
            selected = [row for row in rows if low <= row["pull_scarcity"] <= high]
        else:
            selected = [row for row in rows if low <= row["pull_scarcity"] < high]
        if len(selected) < 10:
            continue
        appeal = np.array([row["appeal"] for row in selected])
        log_price = np.array([row["log_price"] for row in selected])
        slope, intercept = np.polyfit(appeal, log_price, 1) if np.std(appeal) > 1e-9 else (None, None)
        bucket_rows.append(
            {
                "bucket": index + 1,
                "scarcity_range_neg_log10_p": [float(low), float(high)],
                "one_in_x_range": [float(10 ** low), float(10 ** high)],
                "n": len(selected),
                "appeal_vs_log_price_slope": float(slope) if slope is not None else None,
                "appeal_vs_log_price_spearman": _spearman(appeal, log_price),
                "median_price": float(np.median([row["market_price"] for row in selected])),
                "scatter_sample": [
                    {"appeal": round(row["appeal"], 2), "log_price": round(row["log_price"], 4)}
                    for row in selected[:400]
                ],
            }
        )
    return {
        "note": (
            "Quantile buckets exist only for plotting. Inference comes from the "
            "continuous appeal x pull_scarcity model (M4/M5)."
        ),
        "scarcity_buckets": bucket_rows,
    }


def fitted_appeal_slopes(rows: Sequence[Dict[str, Any]], fit: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """d log(price) / d appeal at low / median / high scarcity, from M4."""
    if not fit:
        return None
    appeal_beta = fit["coefficients"].get("appeal_c")
    interaction_beta = fit["coefficients"].get("appeal_x_scarcity")
    if appeal_beta is None or interaction_beta is None:
        return None
    scarcity = np.array([row["pull_scarcity"] for row in rows])
    centered_mean = float(np.mean(scarcity))
    output = {}
    for label, quantile in (("low_scarcity_p10", 0.10), ("median_scarcity_p50", 0.50), ("high_scarcity_p90", 0.90)):
        value = float(np.quantile(scarcity, quantile))
        output[label] = {
            "pull_scarcity_neg_log10_p": round(value, 4),
            "one_in_x": round(10 ** value, 1),
            "d_log_price_d_appeal": round(appeal_beta + interaction_beta * (value - centered_mean), 6),
        }
    return output


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(Path("docs") / "research" / "card_market_amplification_study.json"))
    parser.add_argument("--no-bootstrap", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

    client = _client()
    logger.info("Loading pull-rate assumptions...")
    pull_rates = load_pull_rate_tables(client)
    if not pull_rates:
        print("No sets have modeled pull-rate assumptions; the amplification study cannot run.")
        return 1

    set_rows = _paged_select(client.table("sets").select("id,name,canonical_key,release_date,era_id"))
    eras = {
        str(row["id"]): str(row.get("name") or "")
        for row in _paged_select(client.table("eras").select("id,name"))
    }
    sets_by_id = {
        str(row["id"]): {**row, "era_name": eras.get(str(row.get("era_id") or ""))}
        for row in set_rows
    }
    covered_set_ids = [set_id for set_id in pull_rates if set_id in sets_by_id]
    logger.info("Sets with pull-rate coverage: %s", len(covered_set_ids))

    logger.info("Loading cards, prices, appeal...")
    cards = load_cards(client, covered_set_ids)
    prices = load_prices(client, covered_set_ids)
    appeal_by_card = load_appeal_by_card(client, [str(card["id"]) for card in cards])

    rows, dropped = build_rows(
        cards=cards,
        prices=prices,
        appeal_by_card=appeal_by_card,
        pull_rates=pull_rates,
        sets_by_id=sets_by_id,
        as_of=datetime.now(timezone.utc).date(),
    )
    logger.info("Modeling sample: %s cards across %s sets", len(rows), len({r["set_id"] for r in rows}))

    by_era: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_era[str(row.get("era") or "unknown")].append(row)

    era_reports: Dict[str, Any] = {}
    era_coverage: Dict[str, Any] = {}
    for era, era_rows in sorted(by_era.items()):
        n_sets = len({row["set_id"] for row in era_rows})
        eligible = n_sets >= MIN_SETS_PER_ERA and len(era_rows) >= MIN_CARDS_PER_ERA
        era_coverage[era] = {
            "n_cards": len(era_rows),
            "n_sets": n_sets,
            "eligible_for_era_model": eligible,
            "reason": None
            if eligible
            else f"needs >= {MIN_SETS_PER_ERA} sets and >= {MIN_CARDS_PER_ERA} cards for leave-whole-set-out CV",
        }
        if eligible:
            logger.info("Fitting era model: %s (%s cards, %s sets)", era, len(era_rows), n_sets)
            report = run_model_suite(list(era_rows), label=era, bootstrap=not args.no_bootstrap)
            m4_fit = ((report["models"].get("M4_interaction") or {}).get("fixed_effects_fit"))
            report["fitted_appeal_slopes_by_scarcity"] = fitted_appeal_slopes(era_rows, m4_fit)
            report["visualization"] = build_visualization(era_rows)
            era_reports[era] = report

    logger.info("Fitting pooled model...")
    pooled = run_model_suite(list(rows), label="pooled_all_covered_eras", bootstrap=not args.no_bootstrap)
    pooled_m4 = ((pooled["models"].get("M4_interaction") or {}).get("fixed_effects_fit"))
    pooled["fitted_appeal_slopes_by_scarcity"] = fitted_appeal_slopes(rows, pooled_m4)
    pooled["visualization"] = build_visualization(rows)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "study": "card_market_amplification_v1",
        "design": {
            "outcome": "log(card market price)",
            "appeal": "Pure Pokemon Demand (0.75*fan + 0.25*trend), price-independent",
            "pull_scarcity": "-log10(P(specific card in one pack)) from modeled set pull-rate assumptions",
            "treatment_prestige": "get_treatment_score(rarity)/100, kept separate from actual pull odds",
            "controls": CONTROL_COLUMNS,
            "inference": "set fixed effects (absorbed) + cluster-robust SE by set + cluster bootstrap by set",
            "validation": "leave-WHOLE-SET-out grouped CV (era dummies replace set FE out of sample)",
            "prohibitions": [
                "No coefficient here may be transferred into RIP weights; these fit price, not user utility.",
                "Buckets are for visualization only; the continuous interaction model is the inferential truth.",
                "Model selection never uses in-sample correlation alone.",
            ],
        },
        "sample": {
            "n_cards_modeled": len(rows),
            "n_sets_modeled": len({row["set_id"] for row in rows}),
            "n_species": len({row.get("primary_reference_id") for row in rows}),
            "dropped_counts": dropped,
            "note": (
                "Modeling sample is Pokemon cards with a species link, a positive price, "
                "and a rarity that matches a modeled pull-rate row; supertype is therefore "
                "constant and cannot serve as a control."
            ),
        },
        "era_coverage": era_coverage,
        "pooled": pooled,
        "by_era": era_reports,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"\nSample: {len(rows)} cards / {report['sample']['n_sets_modeled']} sets / {report['sample']['n_species']} species")
    print(f"Dropped: {dropped}")
    _print_suite(pooled, "POOLED")
    for era, era_report in era_reports.items():
        _print_suite(era_report, f"ERA: {era}")
    for era, coverage in era_coverage.items():
        if not coverage["eligible_for_era_model"]:
            print(f"ERA {era}: SKIPPED ({coverage['n_sets']} sets, {coverage['n_cards']} cards) - {coverage['reason']}")
    print(f"\nReport written to {out_path}")
    return 0


def _print_suite(report: Dict[str, Any], header: str) -> None:
    print(f"\n=== {header} === n={report['n_cards']} cards, {report['n_sets']} sets, {report['n_species']} species")
    for name, entry in report["models"].items():
        cv = entry.get("leave_whole_set_out_cv") or {}
        fit = entry.get("fixed_effects_fit") or {}
        mae = cv.get("mae")
        rho = cv.get("spearman")
        r2 = cv.get("r2")
        print(
            f"  {name:<24} OOS mae={mae:.4f} " if mae is not None else f"  {name:<24} OOS mae=n/a ",
            end="",
        )
        print(
            f"rho={rho:.4f} " if rho is not None else "rho=n/a ",
            end="",
        )
        print(f"r2={r2:.4f} " if r2 is not None else "r2=n/a ", end="")
        print(f"within_r2={fit.get('within_r2'):.4f}" if fit.get("within_r2") is not None else "within_r2=n/a")
    for key, value in report["incremental_lift_out_of_sample"].items():
        pct = value.get("mae_reduction_pct")
        gain = value.get("spearman_gain")
        print(
            f"    LIFT {key:<38} mae_reduction={pct:+.2f}% " if pct is not None else f"    LIFT {key:<38} mae_reduction=n/a ",
            end="",
        )
        print(f"spearman_gain={gain:+.4f}" if gain is not None else "spearman_gain=n/a")
    m4 = (report["models"].get("M4_interaction") or {}).get("fixed_effects_fit") or {}
    if m4:
        for name in ("appeal_c", "pull_scarcity_c", "appeal_x_scarcity"):
            coefficient = m4["coefficients"].get(name)
            stderr = m4["cluster_robust_se"].get(name)
            t_stat = m4["t_stats"].get(name)
            if coefficient is not None:
                print(f"    M4 {name:<20} b={coefficient:+.5f} se={stderr:.5f} t={t_stat:+.2f}")
    ci = (report["models"].get("M4_interaction") or {}).get("cluster_bootstrap_ci") or {}
    for name in ("appeal_c", "appeal_x_scarcity"):
        entry = ci.get(name)
        if entry and entry.get("ci_low") is not None:
            print(
                f"    M4 boot {name:<16} 95% CI [{entry['ci_low']:+.5f}, {entry['ci_high']:+.5f}] "
                f"share_positive={entry.get('share_positive')}"
            )
    slopes = report.get("fitted_appeal_slopes_by_scarcity")
    if slopes:
        for label, entry in slopes.items():
            print(f"    slope@{label:<22} 1-in-{entry['one_in_x']:<9} d_log_price/d_appeal={entry['d_log_price_d_appeal']:+.5f}")


if __name__ == "__main__":
    raise SystemExit(main())
