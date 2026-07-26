"""Phase 3-5 — repeated-species correction for the card-level market study.

The original card-level amplification study clustered only by SET, but Pokemon
Appeal is a *species-level* variable repeated across many cards and many sets:
every Charizard card in every set carries the same appeal value. Clustering only
by set therefore understates uncertainty on the Appeal coefficient, because
observations sharing a species are correlated across set boundaries.

Three specifications:

  A. Set fixed effects + cluster-robust by set          (existing, for comparison)
  B. Set fixed effects + TWO-WAY cluster (set x species) (Cameron-Gelbach-Miller)
  C. Crossed mixed effects: (1|set) + (1|species)        (statsmodels MixedLM,
     variance components; species is a RANDOM intercept, never a fixed effect,
     which would absorb the species-level Appeal variable entirely)

Plus:
  - wild cluster bootstrap by set (Rademacher) on the Appeal and interaction
    coefficients, with the ordinary set bootstrap retained as a comparison;
  - pooled modern cohort (Scarlet & Violet + Mega Evolution) with era as a
    control and era x scarcity / era x prestige diagnostic interactions;
  - Lost Origin as a directional external holdout (never an era model);
  - leave-whole-set-out AND grouped-species cross-validation, reported both
    card-weighted and set-balanced.

Read-only. Nothing is committed. No coefficient here may become a RIP weight.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import statistics
import sys
import warnings
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.scripts.build_card_market_amplification_study import (  # noqa: E402
    CONTROL_COLUMNS,
    _client,
    add_centered_terms,
    build_rows,
    fit_within_ols,
    load_appeal_by_card,
    load_cards,
    load_prices,
    load_pull_rate_tables,
    _paged_select,
)

logger = logging.getLogger(__name__)

MODERN_ERAS = ("Scarlet and Violet", "Mega Evolution")
HOLDOUT_SET_NAME = "Lost Origin"
BOOTSTRAP_DRAWS = 400
RANDOM_SEED = 20260716
CORE_TERMS = ("appeal_c", "pull_scarcity_c", "appeal_x_scarcity", "treatment_prestige")


def _as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


# ---------------------------------------------------------------------------
# Spec B — two-way cluster-robust covariance (Cameron, Gelbach & Miller 2011)
# ---------------------------------------------------------------------------

def _cluster_meat(X: np.ndarray, residuals: np.ndarray, groups: Sequence[Any]) -> np.ndarray:
    by_group: Dict[Any, List[int]] = defaultdict(list)
    for index, group in enumerate(groups):
        by_group[group].append(index)
    k = X.shape[1]
    meat = np.zeros((k, k))
    for indices in by_group.values():
        score = X[indices].T @ residuals[indices]
        meat += np.outer(score, score)
    return meat


def _demean_by_group(matrix: np.ndarray, groups: Sequence[Any]) -> np.ndarray:
    out = np.array(matrix, dtype=float, copy=True)
    by_group: Dict[Any, List[int]] = defaultdict(list)
    for index, group in enumerate(groups):
        by_group[group].append(index)
    for indices in by_group.values():
        out[indices] -= out[indices].mean(axis=0)
    return out


def fit_two_way_clustered(
    rows: Sequence[Dict[str, Any]],
    columns: Sequence[str],
) -> Optional[Dict[str, Any]]:
    """Set FE OLS with two-way (set x species) cluster-robust SEs.

    V_2way = V_set + V_species - V_intersection.
    The intersection cluster is (set, species). The estimator is not guaranteed
    positive semi-definite in finite samples; if any variance goes negative we
    report that rather than silently patching it.
    """
    sets = [row["set_id"] for row in rows]
    species = [row.get("primary_reference_id") for row in rows]
    intersection = [(row["set_id"], row.get("primary_reference_id")) for row in rows]

    y = np.array([row["log_price"] for row in rows], dtype=float)
    X_raw = np.column_stack([[float(row[c]) for row in rows] for c in columns])
    y_w = _demean_by_group(y.reshape(-1, 1), sets).ravel()
    X_w = _demean_by_group(X_raw, sets)

    keep = [i for i in range(X_w.shape[1]) if np.std(X_w[:, i]) > 1e-10]
    dropped = [columns[i] for i in range(len(columns)) if i not in keep]
    X_w = X_w[:, keep]
    names = [columns[i] for i in keep]
    if X_w.shape[1] == 0:
        return None

    beta, *_ = np.linalg.lstsq(X_w, y_w, rcond=None)
    residuals = y_w - X_w @ beta
    n, k = X_w.shape
    bread = np.linalg.pinv(X_w.T @ X_w)

    def sandwich(groups: Sequence[Any]) -> np.ndarray:
        n_groups = len(set(map(str, groups)))
        correction = n_groups / max(n_groups - 1, 1)
        return bread @ _cluster_meat(X_w, residuals, groups) @ bread * correction

    v_set = sandwich(sets)
    v_species = sandwich(species)
    v_intersection = sandwich(intersection)
    vcov = v_set + v_species - v_intersection
    diagonal = np.diag(vcov)
    negative = [names[i] for i in range(k) if diagonal[i] <= 0]
    stderr = np.sqrt(np.maximum(diagonal, 0.0))

    return {
        "columns": names,
        "dropped_collinear_columns": dropped,
        "coefficients": {name: float(beta[i]) for i, name in enumerate(names)},
        "two_way_se": {name: float(stderr[i]) for i, name in enumerate(names)},
        "t_stats": {
            name: (float(beta[i] / stderr[i]) if stderr[i] > 0 else None)
            for i, name in enumerate(names)
        },
        "se_set_only": {name: float(np.sqrt(max(np.diag(v_set)[i], 0.0))) for i, name in enumerate(names)},
        "se_species_only": {name: float(np.sqrt(max(np.diag(v_species)[i], 0.0))) for i, name in enumerate(names)},
        "n": n,
        "n_sets": len(set(map(str, sets))),
        "n_species": len(set(map(str, species))),
        "non_psd_terms": negative,
        "finite_cluster_note": (
            f"Two-way clustering with only {len(set(map(str, sets)))} set clusters is the binding "
            "limitation: cluster-robust inference is asymptotic in the NUMBER OF CLUSTERS, and "
            "~20 is few. Species clusters are plentiful (~900) but sets are not, so the set "
            "dimension dominates the uncertainty. Treat these SEs as indicative, and prefer the "
            "wild cluster bootstrap by set."
        ),
    }


# ---------------------------------------------------------------------------
# Spec C — crossed random intercepts (statsmodels MixedLM variance components)
# ---------------------------------------------------------------------------

def fit_crossed_mixed_effects(rows: Sequence[Dict[str, Any]], columns: Sequence[str]) -> Optional[Dict[str, Any]]:
    """log_price ~ fixed + (1|set) + (1|species).

    Species must be a RANDOM intercept: as a fixed effect it would absorb the
    species-level Appeal variable completely and the coefficient would vanish.
    Crossed effects are fitted via MixedLM variance components on a single
    pseudo-group covering all rows.
    """
    try:
        import pandas as pd
        import statsmodels.formula.api as smf
    except Exception as exc:
        return {"available": False, "reason": f"statsmodels/pandas unavailable: {exc}"}

    # Drop zero-variance regressors before fitting. Unlike the set-FE specs
    # (which absorb set-level constants by demeaning), the mixed model keeps an
    # explicit design matrix, so an all-constant column (e.g. is_promo, which is
    # 0 for every card in these main sets) makes X'X singular.
    usable_columns = [
        column for column in columns
        if float(np.std([float(row[column]) for row in rows])) > 1e-10
    ]
    dropped_constant = [column for column in columns if column not in usable_columns]
    if not usable_columns:
        return {"available": False, "reason": "no non-constant regressors"}

    frame = pd.DataFrame(
        {
            "log_price": [row["log_price"] for row in rows],
            "set_id": [str(row["set_id"]) for row in rows],
            "species": [str(row.get("primary_reference_id")) for row in rows],
            "group": 1,
            **{column: [float(row[column]) for row in rows] for column in usable_columns},
        }
    )
    columns = usable_columns
    formula = "log_price ~ " + " + ".join(columns)
    vc_formula = {"set": "0 + C(set_id)", "species": "0 + C(species)"}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = smf.mixedlm(formula, frame, groups=frame["group"], vc_formula=vc_formula)
            result = model.fit(reml=True, method="lbfgs", maxiter=200)
    except Exception as exc:
        return {"available": False, "reason": f"fit failed: {exc}"}

    variance = {k: float(v) for k, v in result.vcomp_dict.items()} if hasattr(result, "vcomp_dict") else {}
    if not variance:
        try:
            variance = dict(zip(model.exog_vc.names, [float(v) for v in result.vcomp]))
        except Exception:
            variance = {}
    residual_variance = float(result.scale)
    total = sum(variance.values()) + residual_variance

    return {
        "available": True,
        "converged": bool(result.converged),
        "dropped_constant_columns": dropped_constant,
        "n": int(result.nobs),
        "coefficients": {name: float(result.fe_params.get(name, float("nan"))) for name in columns if name in result.fe_params},
        "std_errors": {name: float(result.bse_fe.get(name, float("nan"))) for name in columns if name in result.bse_fe},
        "t_stats": {name: float(result.tvalues.get(name, float("nan"))) for name in columns if name in result.tvalues},
        "variance_components": {k: round(v, 5) for k, v in variance.items()},
        "residual_variance": round(residual_variance, 5),
        "variance_share": {
            **{k: round(v / total, 4) for k, v in variance.items()},
            "residual": round(residual_variance / total, 4),
        } if total > 0 else {},
        "method": "MixedLM REML, crossed variance components for set and species",
    }


# ---------------------------------------------------------------------------
# Wild cluster bootstrap by set (Rademacher)
# ---------------------------------------------------------------------------

def wild_cluster_bootstrap(
    rows: Sequence[Dict[str, Any]],
    columns: Sequence[str],
    *,
    terms: Sequence[str] = CORE_TERMS,
    draws: int = BOOTSTRAP_DRAWS,
    seed: int = RANDOM_SEED,
) -> Dict[str, Any]:
    """Wild cluster bootstrap-t by set, imposing no null (percentile-t of beta).

    Preferred over the ordinary cluster bootstrap when the number of clusters is
    small (~20 sets), which is exactly this cohort's situation.
    """
    sets = [row["set_id"] for row in rows]
    y = np.array([row["log_price"] for row in rows], dtype=float)
    X_raw = np.column_stack([[float(row[c]) for row in rows] for c in columns])
    y_w = _demean_by_group(y.reshape(-1, 1), sets).ravel()
    X_w = _demean_by_group(X_raw, sets)
    keep = [i for i in range(X_w.shape[1]) if np.std(X_w[:, i]) > 1e-10]
    X_w = X_w[:, keep]
    names = [columns[i] for i in keep]
    if X_w.shape[1] == 0:
        return {}

    beta, *_ = np.linalg.lstsq(X_w, y_w, rcond=None)
    fitted = X_w @ beta
    residuals = y_w - fitted

    rng = np.random.default_rng(seed)
    unique_sets = sorted(set(map(str, sets)))
    index_by_set = {s: [i for i, g in enumerate(map(str, sets)) if g == s] for s in unique_sets}

    samples: Dict[str, List[float]] = defaultdict(list)
    for _ in range(draws):
        weights = rng.choice([-1.0, 1.0], size=len(unique_sets))
        y_star = fitted.copy()
        for weight, s in zip(weights, unique_sets):
            indices = index_by_set[s]
            y_star[indices] = fitted[indices] + weight * residuals[indices]
        beta_star, *_ = np.linalg.lstsq(X_w, y_star, rcond=None)
        for i, name in enumerate(names):
            samples[name].append(float(beta_star[i]))

    out: Dict[str, Any] = {}
    for name in terms:
        values = samples.get(name)
        if not values:
            continue
        array = np.array(values)
        out[name] = {
            "point": round(float(beta[names.index(name)]), 6),
            "ci_low": round(float(np.percentile(array, 2.5)), 6),
            "ci_high": round(float(np.percentile(array, 97.5)), 6),
            "share_positive": round(float(np.mean(array > 0)), 4),
            "draws": len(values),
        }
    return out


# ---------------------------------------------------------------------------
# Validation — LOSO + grouped species CV, card-weighted and set-balanced
# ---------------------------------------------------------------------------

def _design(rows: Sequence[Dict[str, Any]], columns: Sequence[str], eras: Sequence[str]) -> np.ndarray:
    pieces = [np.ones((len(rows), 1)), np.column_stack([[float(row[c]) for row in rows] for c in columns])]
    for era in eras[1:]:
        pieces.append(np.array([[1.0 if str(row.get("era")) == era else 0.0] for row in rows]))
    return np.hstack(pieces)


def _metrics(actual: np.ndarray, predicted: np.ndarray, per_group: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    from scipy.stats import spearmanr

    errors = actual - predicted
    tss = float(np.sum((actual - actual.mean()) ** 2))
    rss = float(np.sum(errors ** 2))
    rho = spearmanr(predicted, actual).statistic if len(actual) > 2 else None
    return {
        "n": int(len(actual)),
        "n_folds": len(per_group),
        "mae_card_weighted": round(float(np.mean(np.abs(errors))), 5),
        "rmse_card_weighted": round(float(np.sqrt(np.mean(errors ** 2))), 5),
        "spearman": round(float(rho), 4) if rho is not None and math.isfinite(rho) else None,
        "r2": round(1.0 - rss / tss, 4) if tss > 0 else None,
        "macro_avg_fold_mae": round(float(np.mean([g["mae"] for g in per_group])), 5) if per_group else None,
        "median_fold_mae": round(float(np.median([g["mae"] for g in per_group])), 5) if per_group else None,
    }


def grouped_cv(
    rows: Sequence[Dict[str, Any]],
    columns: Sequence[str],
    *,
    group_key: str,
    n_folds: Optional[int] = None,
    seed: int = RANDOM_SEED,
) -> Optional[Dict[str, Any]]:
    """Grouped CV. ``group_key='set_id'`` gives leave-whole-set-out (one fold per
    set). ``group_key='primary_reference_id'`` with n_folds gives grouped species
    CV: every card of a species is held out together, so a species seen in
    training can never leak into its own test fold."""
    eras = sorted({str(row.get("era")) for row in rows})
    groups = sorted({str(row.get(group_key)) for row in rows})
    if len(groups) < 3:
        return None
    if n_folds is None:
        folds = [[g] for g in groups]
    else:
        rng = np.random.default_rng(seed)
        shuffled = list(groups)
        rng.shuffle(shuffled)
        folds = [shuffled[i::n_folds] for i in range(min(n_folds, len(shuffled)))]

    predictions: List[float] = []
    actuals: List[float] = []
    per_fold: List[Dict[str, Any]] = []
    per_set_errors: Dict[str, List[float]] = defaultdict(list)
    for fold in folds:
        fold_set = set(fold)
        train = [row for row in rows if str(row.get(group_key)) not in fold_set]
        test = [row for row in rows if str(row.get(group_key)) in fold_set]
        if len(train) < len(columns) + 5 or not test:
            continue
        X = _design(train, columns, eras)
        y = np.array([row["log_price"] for row in train])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        y_hat = _design(test, columns, eras) @ beta
        y_test = np.array([row["log_price"] for row in test])
        predictions.extend(y_hat.tolist())
        actuals.extend(y_test.tolist())
        per_fold.append({"fold": fold[0] if len(fold) == 1 else f"{len(fold)} groups", "n": len(test),
                         "mae": float(np.mean(np.abs(y_test - y_hat)))})
        for row, error in zip(test, np.abs(y_test - y_hat)):
            per_set_errors[str(row.get("set_name"))].append(float(error))
    if not predictions:
        return None

    metrics = _metrics(np.array(actuals), np.array(predictions), per_fold)
    metrics["set_balanced_mae"] = round(
        float(np.mean([float(np.mean(v)) for v in per_set_errors.values()])), 5
    )
    metrics["per_set_mae"] = {k: round(float(np.mean(v)), 4) for k, v in sorted(per_set_errors.items())}
    return metrics


def compare_cv(base: Optional[Dict[str, Any]], richer: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not base or not richer:
        return {"available": False}
    base_sets = base.get("per_set_mae") or {}
    rich_sets = richer.get("per_set_mae") or {}
    shared = sorted(set(base_sets) & set(rich_sets))
    deltas = [(base_sets[s] - rich_sets[s], s) for s in shared]
    improved = [d for d, _s in deltas if d > 0]
    return {
        "available": True,
        "mae_card_weighted_reduction_pct": round(
            100.0 * (base["mae_card_weighted"] - richer["mae_card_weighted"]) / base["mae_card_weighted"], 3
        ),
        "set_balanced_mae_reduction_pct": round(
            100.0 * (base["set_balanced_mae"] - richer["set_balanced_mae"]) / base["set_balanced_mae"], 3
        ) if base.get("set_balanced_mae") else None,
        "macro_fold_mae_reduction_pct": round(
            100.0 * (base["macro_avg_fold_mae"] - richer["macro_avg_fold_mae"]) / base["macro_avg_fold_mae"], 3
        ) if base.get("macro_avg_fold_mae") else None,
        "spearman_gain": round((richer.get("spearman") or 0) - (base.get("spearman") or 0), 4),
        "sets_improved": len(improved),
        "sets_total": len(deltas),
        "pct_sets_improved": round(100.0 * len(improved) / len(deltas), 1) if deltas else None,
        "largest_improvements": [{"set": s, "mae_delta": round(d, 4)} for d, s in sorted(deltas, reverse=True)[:5]],
        "largest_regressions": [{"set": s, "mae_delta": round(d, 4)} for d, s in sorted(deltas)[:5]],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(Path("docs") / "research" / "repeated_species_correction.json"))
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

    client = _client()
    logger.info("Loading data...")
    pull_rates = load_pull_rate_tables(client)
    set_rows = _paged_select(client.table("sets").select("id,name,canonical_key,release_date,era_id"))
    eras = {str(r["id"]): str(r.get("name") or "") for r in _paged_select(client.table("eras").select("id,name"))}
    sets_by_id = {str(r["id"]): {**r, "era_name": eras.get(str(r.get("era_id") or ""))} for r in set_rows}
    covered = [s for s in pull_rates if s in sets_by_id]
    cards = load_cards(client, covered)
    prices = load_prices(client, covered)
    appeal_by_card = load_appeal_by_card(client, [str(c["id"]) for c in cards])
    rows, dropped = build_rows(
        cards=cards, prices=prices, appeal_by_card=appeal_by_card, pull_rates=pull_rates,
        sets_by_id=sets_by_id, as_of=datetime.now(timezone.utc).date(),
    )
    logger.info("Sample: %s cards / %s sets", len(rows), len({r['set_id'] for r in rows}))

    modern = [row for row in rows if str(row.get("era")) in MODERN_ERAS]
    holdout = [row for row in rows if str(row.get("set_name")) == HOLDOUT_SET_NAME]
    add_centered_terms(modern)
    columns = list(CONTROL_COLUMNS) + ["appeal_c", "pull_scarcity_c", "appeal_x_scarcity", "treatment_prestige"]

    logger.info("Spec A: set FE + cluster-robust by set...")
    spec_a = fit_within_ols(modern, columns)
    logger.info("Spec B: two-way cluster (set x species)...")
    spec_b = fit_two_way_clustered(modern, columns)
    logger.info("Spec C: crossed mixed effects (1|set)+(1|species)...")
    spec_c = fit_crossed_mixed_effects(modern, columns)
    logger.info("Wild cluster bootstrap by set...")
    wild = wild_cluster_bootstrap(modern, columns)

    # Era diagnostics: era x scarcity, era x prestige (diagnostic only).
    for row in modern:
        row["is_mega"] = 1.0 if str(row.get("era")) == "Mega Evolution" else 0.0
        row["era_x_scarcity"] = row["is_mega"] * row["pull_scarcity_c"]
        row["era_x_prestige"] = row["is_mega"] * row["treatment_prestige"]
    era_columns = columns + ["era_x_scarcity", "era_x_prestige"]
    era_fit = fit_within_ols(modern, era_columns)
    era_wild = wild_cluster_bootstrap(
        modern, era_columns, terms=("era_x_scarcity", "era_x_prestige", "appeal_c", "appeal_x_scarcity")
    )

    logger.info("Validation: leave-whole-set-out and grouped species CV...")
    base_columns = list(CONTROL_COLUMNS) + ["pull_scarcity_c"]
    full_columns = list(CONTROL_COLUMNS) + ["appeal_c", "pull_scarcity_c", "appeal_x_scarcity"]
    validation = {
        "leave_whole_set_out": {
            "without_appeal": grouped_cv(modern, base_columns, group_key="set_id"),
            "with_appeal": grouped_cv(modern, full_columns, group_key="set_id"),
        },
        "grouped_species_10_fold": {
            "without_appeal": grouped_cv(modern, base_columns, group_key="primary_reference_id", n_folds=10),
            "with_appeal": grouped_cv(modern, full_columns, group_key="primary_reference_id", n_folds=10),
        },
        "grouped_species_20_fold": {
            "without_appeal": grouped_cv(modern, base_columns, group_key="primary_reference_id", n_folds=20),
            "with_appeal": grouped_cv(modern, full_columns, group_key="primary_reference_id", n_folds=20),
        },
    }
    for key, entry in validation.items():
        entry["appeal_lift"] = compare_cv(entry["without_appeal"], entry["with_appeal"])

    # Lost Origin directional external holdout.
    holdout_result: Dict[str, Any] = {"available": False, "reason": "no Lost Origin rows"}
    if holdout:
        appeal_mean = float(np.mean([r["appeal"] for r in modern]))
        scarcity_mean = float(np.mean([r["pull_scarcity"] for r in modern]))
        for row in holdout:
            row["appeal_c"] = row["appeal"] - appeal_mean
            row["pull_scarcity_c"] = row["pull_scarcity"] - scarcity_mean
            row["appeal_x_scarcity"] = row["appeal_c"] * row["pull_scarcity_c"]
        era_levels = sorted({str(r.get("era")) for r in modern})
        X = _design(modern, full_columns, era_levels)
        y = np.array([r["log_price"] for r in modern])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        # Held-out era is unseen: score it at the pooled intercept (era dummies 0).
        X_hold = _design(holdout, full_columns, era_levels)
        y_hold = np.array([r["log_price"] for r in holdout])
        y_hat = X_hold @ beta
        errors = y_hold - y_hat
        from scipy.stats import spearmanr

        rho = spearmanr(y_hat, y_hold).statistic if len(y_hold) > 2 else None
        holdout_result = {
            "available": True,
            "set": HOLDOUT_SET_NAME,
            "n_cards": len(holdout),
            "mae": round(float(np.mean(np.abs(errors))), 5),
            "rmse": round(float(np.sqrt(np.mean(errors ** 2))), 5),
            "spearman": round(float(rho), 4) if rho is not None and math.isfinite(rho) else None,
            "mean_bias_log_price": round(float(np.mean(errors)), 5),
            "note": (
                "Directional only. One Sword & Shield set is NOT an era model and this result "
                "must not be generalized to the Sword & Shield era."
            ),
        }

    era_counts = defaultdict(int)
    for row in modern:
        era_counts[str(row.get("era"))] += 1

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "study": "repeated_species_correction_v1",
        "sample": {
            "pooled_modern_cards": len(modern),
            "pooled_modern_sets": len({r["set_id"] for r in modern}),
            "pooled_modern_species": len({r.get("primary_reference_id") for r in modern}),
            "era_card_counts": dict(era_counts),
            "era_share": {
                era: round(count / len(modern), 3) for era, count in era_counts.items()
            },
            "dropped_counts": dropped,
        },
        "spec_a_set_cluster": spec_a,
        "spec_b_two_way_cluster": spec_b,
        "spec_c_crossed_mixed_effects": spec_c,
        "wild_cluster_bootstrap_by_set": wild,
        "era_diagnostics": {
            "fit_with_era_interactions": era_fit,
            "wild_bootstrap": era_wild,
            "note": (
                "Diagnostic only. A single pooled modern model is retained; no separate "
                "production formula is built per era."
            ),
        },
        "validation": validation,
        "lost_origin_holdout": holdout_result,
        "prohibitions": [
            "No coefficient here may be transferred into RIP or Opening Appeal weights.",
            "Contemporaneous price explanation only; this is not future-price prediction.",
        ],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _print(report)
    print(f"\nReport written to {out_path}")
    return 0


def _print(report: Dict[str, Any]) -> None:
    sample = report["sample"]
    print(f"\nPooled modern: {sample['pooled_modern_cards']} cards / {sample['pooled_modern_sets']} sets / "
          f"{sample['pooled_modern_species']} species | era share {sample['era_share']}")
    a = report["spec_a_set_cluster"] or {}
    b = report["spec_b_two_way_cluster"] or {}
    c = report["spec_c_crossed_mixed_effects"] or {}
    print("\n--- Appeal / interaction across specifications ---")
    for term in CORE_TERMS:
        line = f"  {term:<20}"
        if a.get("coefficients", {}).get(term) is not None:
            line += f" A: b={a['coefficients'][term]:+.5f} se={a['cluster_robust_se'][term]:.5f} t={a['t_stats'][term]:+.2f}"
        if b.get("coefficients", {}).get(term) is not None:
            line += f" | B(2-way): se={b['two_way_se'][term]:.5f} t={b['t_stats'][term]:+.2f}"
        if c.get("available") and term in (c.get("coefficients") or {}):
            line += f" | C(mixed): b={c['coefficients'][term]:+.5f} t={c['t_stats'][term]:+.2f}"
        print(line)
    if b.get("non_psd_terms"):
        print(f"  NOTE non-PSD two-way variance terms: {b['non_psd_terms']}")
    if c.get("available"):
        print(f"  Spec C converged={c['converged']} variance_share={c.get('variance_share')}")
    else:
        print(f"  Spec C unavailable: {c.get('reason')}")
    print("\n--- Wild cluster bootstrap by set ---")
    for term, entry in (report["wild_cluster_bootstrap_by_set"] or {}).items():
        print(f"  {term:<20} b={entry['point']:+.5f} 95% CI [{entry['ci_low']:+.5f},{entry['ci_high']:+.5f}] pos={entry['share_positive']}")
    print("\n--- Era diagnostic interactions ---")
    for term, entry in (report["era_diagnostics"]["wild_bootstrap"] or {}).items():
        print(f"  {term:<20} b={entry['point']:+.5f} CI [{entry['ci_low']:+.5f},{entry['ci_high']:+.5f}] pos={entry['share_positive']}")
    print("\n--- Validation: appeal lift ---")
    for name, entry in report["validation"].items():
        lift = entry.get("appeal_lift") or {}
        if lift.get("available"):
            print(f"  {name:<26} card_mae%={lift['mae_card_weighted_reduction_pct']:+.2f} "
                  f"set_balanced_mae%={lift['set_balanced_mae_reduction_pct']} "
                  f"rho+={lift['spearman_gain']:+.4f} sets_improved={lift['sets_improved']}/{lift['sets_total']}")
    h = report["lost_origin_holdout"]
    if h.get("available"):
        print(f"\n--- Lost Origin holdout: n={h['n_cards']} mae={h['mae']} rho={h['spearman']} bias={h['mean_bias_log_price']}")


if __name__ == "__main__":
    raise SystemExit(main())
