"""Nested incremental-model framework (M0..M7) with grouped out-of-sample evaluation.

Pre-registered model ladder (per the research spec): each model adds exactly one
signal (or one pre-registered interaction set) on top of the previous model, so the
INCREMENTAL contribution of that signal -- not just its raw correlation -- can be
measured out-of-sample. Ordinary least squares via numpy.linalg.lstsq (no sklearn
dependency). Only fits models over signals actually present in the supplied
records; a signal that doesn't exist yet (Artist/Treatment/Scarcity pre-V7) is
simply never activated -- callers do not need placeholder columns.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from backend.research.market_validation.grouped_cv import leave_whole_set_out_folds
from backend.research.market_validation.price_separation import assert_no_price_in_predictor_keys
from backend.research.validation_stats import spearman

# Pre-registered nested ladder. Each entry's `adds` names the NEW predictor
# key(s)/interaction added relative to the previous stage. `M7` interactions are
# only meaningful once their constituent components exist; build_nested_ladder()
# below drops any stage whose required columns are absent from the dataset,
# rather than fabricating zeros for missing signals.
NESTED_LADDER: List[Dict[str, Any]] = [
    {"id": "M0", "adds": [], "controls_only": True},
    {"id": "M1", "adds": ["pokemon_subject_appeal"]},
    {"id": "M2", "adds": ["pull_scarcity_score"]},
    {"id": "M3", "adds": ["treatment_prestige_score"]},
    {"id": "M4", "adds": ["playability_raw_score", "playability_applied_lift"]},
    {"id": "M5", "adds": ["artist_recognition_score"]},
    {"id": "M6", "adds": ["trainer_appeal"]},
    {
        "id": "M7",
        "adds": [],
        "interactions": [
            ("pokemon_subject_appeal", "pull_scarcity_score"),
            ("artist_recognition_score", "treatment_prestige_score"),
            ("trainer_appeal", "playability_raw_score"),
        ],
    },
]

DEFAULT_STRUCTURAL_CONTROLS = ["release_age_days"]  # numeric controls; categoricals handled via one-hot below


@dataclass
class FittedModel:
    model_id: str
    predictor_keys: List[str]
    n_train: int
    coefficients: Dict[str, float]
    intercept: float


@dataclass
class OosMetrics:
    model_id: str
    n: int
    r2: Optional[float]
    mae: Optional[float]
    rmse: Optional[float]
    spearman_held_out: Optional[float]


def _one_hot(records: Sequence[Mapping[str, Any]], key: str) -> Tuple[List[str], List[List[float]]]:
    categories = sorted({str(row.get(key)) for row in records if row.get(key) is not None})
    columns = [f"{key}={c}" for c in categories[1:]]  # drop first level to avoid collinearity with intercept
    rows = []
    for row in records:
        val = str(row.get(key)) if row.get(key) is not None else None
        rows.append([1.0 if val == c else 0.0 for c in categories[1:]])
    return columns, rows


def build_design_matrix(
    records: Sequence[Mapping[str, Any]],
    numeric_predictor_keys: Sequence[str],
    categorical_control_keys: Sequence[str] = ("set_era_bucket",),
) -> Tuple[List[str], np.ndarray, List[int]]:
    """Builds X for the rows where every requested numeric predictor is finite.
    Categorical controls (era buckets etc.) are one-hot encoded. Returns
    (column_names, X, kept_row_indices). Raises PriceContaminationError via
    assert_no_price_in_predictor_keys if a price field sneaks into the requested
    predictor list.
    """
    assert_no_price_in_predictor_keys(list(numeric_predictor_keys) + list(categorical_control_keys))

    kept_indices = [
        i
        for i, row in enumerate(records)
        if all(_finite(row.get(k)) is not None for k in numeric_predictor_keys)
    ]
    kept_records = [records[i] for i in kept_indices]

    columns: List[str] = list(numeric_predictor_keys)
    numeric_block = [[float(row[k]) for k in numeric_predictor_keys] for row in kept_records]

    for cat_key in categorical_control_keys:
        if any(row.get(cat_key) is not None for row in kept_records):
            cat_cols, cat_block = _one_hot(kept_records, cat_key)
            columns += cat_cols
            for row_vals, extra in zip(numeric_block, cat_block):
                row_vals.extend(extra)

    x = np.array(numeric_block, dtype=float) if numeric_block else np.zeros((0, len(columns)))
    return columns, x, kept_indices


def fit_ols(x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, float]:
    """Fits y = X @ coef + intercept via least squares. Returns (coef, intercept)."""
    x_with_intercept = np.hstack([x, np.ones((x.shape[0], 1))]) if x.shape[1] > 0 else np.ones((x.shape[0], 1))
    solution, *_ = np.linalg.lstsq(x_with_intercept, y, rcond=None)
    if x.shape[1] > 0:
        return solution[:-1], float(solution[-1])
    return np.array([]), float(solution[0])


def predict(x: np.ndarray, coef: np.ndarray, intercept: float) -> np.ndarray:
    if coef.size == 0:
        return np.full(x.shape[0], intercept)
    return x @ coef + intercept


def build_nested_ladder(available_columns: Sequence[str]) -> List[Dict[str, Any]]:
    """Filters NESTED_LADDER down to stages whose required predictor columns are
    actually present in the dataset -- never fabricates a stage for an unavailable
    signal. Returns stages in order, each carrying the CUMULATIVE predictor set up
    to and including that stage."""
    available = set(available_columns)
    cumulative: List[str] = []
    stages: List[Dict[str, Any]] = []
    for spec in NESTED_LADDER:
        adds = [k for k in spec.get("adds", []) if k in available]
        interactions = []
        for a, b in spec.get("interactions", []):
            if a in available and b in available:
                interactions.append((a, b))
        if spec.get("controls_only"):
            stages.append({"id": spec["id"], "predictors": list(cumulative), "interactions": []})
            continue
        if not adds and not interactions:
            continue  # signal not available yet; do not emit a degenerate identical stage
        cumulative = cumulative + adds
        stages.append({"id": spec["id"], "predictors": list(cumulative), "interactions": interactions})
    return stages


def evaluate_nested_ladder(
    records: Sequence[Mapping[str, Any]],
    structural_controls: Sequence[str] = DEFAULT_STRUCTURAL_CONTROLS,
    categorical_controls: Sequence[str] = ("set_era_bucket",),
    outcome_key: str = "log_market_price",
    set_key: str = "set_id",
) -> List[Dict[str, Any]]:
    """Runs the full nested ladder with leave-whole-set-out cross-validation,
    reporting incremental OOS R²/MAE/RMSE/held-out-Spearman for each stage vs. the
    previous one. This is the framework's central deliverable: does adding signal
    X improve OUT-OF-SAMPLE prediction on unseen sets, not just in-sample fit.
    """
    all_signal_keys = sorted(
        {k for spec in NESTED_LADDER for k in spec.get("adds", [])}
        | {a for spec in NESTED_LADDER for a, b in spec.get("interactions", [])}
        | {b for spec in NESTED_LADDER for a, b in spec.get("interactions", [])}
    )
    available_columns = [k for k in all_signal_keys if any(_finite(r.get(k)) is not None for r in records)]
    stages = build_nested_ladder(available_columns)

    folds = leave_whole_set_out_folds(records, set_key=set_key)
    results: List[Dict[str, Any]] = []
    prev_r2: Optional[float] = None
    prev_mae: Optional[float] = None
    prev_rmse: Optional[float] = None

    for stage in stages:
        predictor_keys = list(structural_controls) + stage["predictors"]
        columns, x_full, kept_idx = build_design_matrix(records, predictor_keys, categorical_controls)
        y_full = np.array([float(records[i][outcome_key]) for i in kept_idx])
        kept_set = set(kept_idx)

        preds_all: List[float] = []
        actual_all: List[float] = []
        for train_idx, val_idx in folds:
            train_pos = [pos for pos, orig in enumerate(kept_idx) if orig in set(train_idx)]
            val_pos = [pos for pos, orig in enumerate(kept_idx) if orig in set(val_idx)]
            if len(train_pos) < len(columns) + 2 or not val_pos:
                continue
            x_train, y_train = x_full[train_pos], y_full[train_pos]
            x_val, y_val = x_full[val_pos], y_full[val_pos]
            coef, intercept = fit_ols(x_train, y_train)
            preds = predict(x_val, coef, intercept)
            preds_all.extend(preds.tolist())
            actual_all.extend(y_val.tolist())

        metrics = _oos_metrics(stage["id"], actual_all, preds_all)
        entry = {
            "modelId": stage["id"],
            "predictors": predictor_keys,
            "n": metrics.n,
            "oosR2": metrics.r2,
            "mae": metrics.mae,
            "rmse": metrics.rmse,
            "heldOutSpearman": metrics.spearman_held_out,
            "deltaR2VsPrevious": (metrics.r2 - prev_r2) if (metrics.r2 is not None and prev_r2 is not None) else None,
            "deltaMaeVsPrevious": (prev_mae - metrics.mae) if (metrics.mae is not None and prev_mae is not None) else None,
            "deltaRmseVsPrevious": (prev_rmse - metrics.rmse) if (metrics.rmse is not None and prev_rmse is not None) else None,
        }
        results.append(entry)
        prev_r2, prev_mae, prev_rmse = metrics.r2, metrics.mae, metrics.rmse

    return results


def _oos_metrics(model_id: str, actual: Sequence[float], predicted: Sequence[float]) -> OosMetrics:
    n = len(actual)
    if n < 3:
        return OosMetrics(model_id, n, None, None, None, None)
    a = np.array(actual)
    p = np.array(predicted)
    residuals = a - p
    sse = float(np.sum(residuals**2))
    sst = float(np.sum((a - np.mean(a)) ** 2))
    r2 = 1.0 - sse / sst if sst > 0 else None
    mae = float(np.mean(np.abs(residuals)))
    rmse = float(np.sqrt(np.mean(residuals**2)))
    held_out_spearman = spearman(list(actual), list(predicted))
    return OosMetrics(model_id, n, r2, mae, rmse, held_out_spearman)


def _finite(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None
