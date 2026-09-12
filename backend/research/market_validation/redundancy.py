"""Redundancy / multicollinearity diagnostics between Collector components.

A component can correlate with price while adding NO unique information (it's just
measuring the same underlying thing another component already captures). This
module answers: how much does component B still add once component A is already in
the model, and how collinear are they with each other?
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

import numpy as np

from backend.research.market_validation.incremental_models import build_design_matrix, fit_ols, predict
from backend.research.market_validation.grouped_cv import leave_whole_set_out_folds
from backend.research.validation_stats import paired, pearson, spearman

# Component pairs of standing interest, per the research spec. Only pairs where
# both keys are present in a given dataset are actually evaluated -- this list is
# a menu, not a requirement.
COMPONENT_PAIRS_OF_INTEREST = [
    ("pokemon_subject_appeal", "artist_recognition_score"),
    ("pokemon_subject_appeal", "playability_raw_score"),
    ("treatment_prestige_score", "pull_scarcity_score"),
    ("artist_recognition_score", "treatment_prestige_score"),
    ("d_pokemon", "generalized_f"),  # set-level pair
    ("final_collector_appeal", "pull_scarcity_score"),
]


def pairwise_redundancy(records: Sequence[Mapping[str, Any]], key_a: str, key_b: str) -> Dict[str, Any]:
    xs, ys = paired(records, key_a, key_b)
    n = len(xs)
    if n < 3:
        return {"a": key_a, "b": key_b, "n": n, "spearman": None, "pearson": None}
    return {"a": key_a, "b": key_b, "n": n, "spearman": spearman(xs, ys), "pearson": pearson(xs, ys)}


def variance_inflation_factor(x: np.ndarray, column_index: int) -> float:
    """VIF for column `column_index` of design matrix x: regress that column on
    every other column, VIF = 1/(1-R^2) of that regression. VIF>=10 is the usual
    rule-of-thumb severe-collinearity threshold; this function returns the raw
    value and lets the caller apply whatever threshold it wants."""
    if x.shape[1] < 2:
        return 1.0
    target = x[:, column_index]
    others = np.delete(x, column_index, axis=1)
    coef, intercept = fit_ols(others, target)
    preds = predict(others, coef, intercept)
    residuals = target - preds
    sse = float(np.sum(residuals**2))
    sst = float(np.sum((target - np.mean(target)) ** 2))
    r2 = 1.0 - sse / sst if sst > 0 else 0.0
    if r2 >= 0.999999:
        return float("inf")
    return 1.0 / (1.0 - r2)


def vif_report(records: Sequence[Mapping[str, Any]], predictor_keys: Sequence[str]) -> Dict[str, float]:
    columns, x, _kept = build_design_matrix(records, predictor_keys, categorical_control_keys=())
    if x.shape[0] < len(columns) + 2:
        return {c: None for c in columns}  # type: ignore[misc]
    return {col: variance_inflation_factor(x, i) for i, col in enumerate(columns)}


def incremental_contribution_after(
    records: Sequence[Mapping[str, Any]],
    base_predictor_keys: Sequence[str],
    candidate_key: str,
    outcome_key: str = "log_market_price",
    set_key: str = "set_id",
) -> Dict[str, Any]:
    """Out-of-sample ΔR² of adding `candidate_key` on top of `base_predictor_keys`
    -- the direct test of "does this component add unique information after its
    competitor is already present," using the same grouped-CV discipline as the
    main incremental-model ladder (not an in-sample comparison).
    """
    folds = leave_whole_set_out_folds(records, set_key=set_key)

    def _oos_r2(predictor_keys: Sequence[str]) -> Any:
        columns, x_full, kept_idx = build_design_matrix(records, predictor_keys, categorical_control_keys=())
        y_full = np.array([float(records[i][outcome_key]) for i in kept_idx])
        preds_all: List[float] = []
        actual_all: List[float] = []
        for train_idx, val_idx in folds:
            train_pos = [pos for pos, orig in enumerate(kept_idx) if orig in set(train_idx)]
            val_pos = [pos for pos, orig in enumerate(kept_idx) if orig in set(val_idx)]
            if len(train_pos) < len(columns) + 2 or not val_pos:
                continue
            coef, intercept = fit_ols(x_full[train_pos], y_full[train_pos])
            preds_all.extend(predict(x_full[val_pos], coef, intercept).tolist())
            actual_all.extend(y_full[val_pos].tolist())
        if len(actual_all) < 3:
            return None
        a = np.array(actual_all)
        p = np.array(preds_all)
        sse = float(np.sum((a - p) ** 2))
        sst = float(np.sum((a - np.mean(a)) ** 2))
        return (1.0 - sse / sst) if sst > 0 else None

    base_r2 = _oos_r2(base_predictor_keys)
    with_candidate_r2 = _oos_r2(list(base_predictor_keys) + [candidate_key])
    delta = (with_candidate_r2 - base_r2) if (base_r2 is not None and with_candidate_r2 is not None) else None
    return {
        "candidate": candidate_key,
        "baselinePredictors": list(base_predictor_keys),
        "baseOosR2": base_r2,
        "withCandidateOosR2": with_candidate_r2,
        "deltaOosR2": delta,
        "interpretation": (
            "candidate adds unique out-of-sample signal" if (delta is not None and delta > 0.01)
            else "candidate adds little/no unique signal beyond the base predictors" if delta is not None
            else "insufficient data"
        ),
    }


def redundancy_matrix(records: Sequence[Mapping[str, Any]], pairs: Sequence[tuple] = tuple(COMPONENT_PAIRS_OF_INTEREST)) -> List[Dict[str, Any]]:
    results = []
    for a, b in pairs:
        if any(row.get(a) is not None for row in records) and any(row.get(b) is not None for row in records):
            results.append(pairwise_redundancy(records, a, b))
    return results
