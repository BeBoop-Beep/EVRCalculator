"""Research-only statistical engine for Collector Appeal market validation.

Nothing here is imported by production scoring/publication. Evaluation uses
leave-WHOLE-SET-out CV and fold-local centering so held-out set means never leak
into training. Price-fit coefficients are evidence only; they must never become
Collector Appeal or RIP weights.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

DEFAULT_CONTROLS: Tuple[str, ...] = (
    "log_release_age", "is_secret", "is_promo", "is_mechanic_card",
    "is_stage2", "is_trainer",
)
MIN_SETS_PER_ERA = 4
MIN_CARDS_PER_ERA = 200
RANDOM_SEED = 20260909


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    column: str
    subject_types: Tuple[str, ...]
    role: str = "candidate"  # candidate | final | diagnostic
    cross_bucket_comparable: bool = False
    interaction_with_scarcity: bool = True

    def validate(self) -> None:
        if not self.name or not self.column:
            raise ValueError("component name/column must be non-empty")
        if not self.subject_types:
            raise ValueError(f"component {self.name!r} must declare subject_types")
        if self.role not in {"candidate", "final", "diagnostic"}:
            raise ValueError(f"unsupported component role: {self.role}")
        if len(set(self.subject_types)) > 1 and not self.cross_bucket_comparable:
            raise ValueError(
                f"component {self.name!r} spans multiple subject buckets without "
                "an explicit cross-bucket comparability freeze"
            )


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _rank(values: Sequence[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    order = np.argsort(array, kind="mergesort")
    ranks = np.empty(len(array), dtype=float)
    i = 0
    while i < len(array):
        j = i + 1
        while j < len(array) and array[order[j]] == array[order[i]]:
            j += 1
        ranks[order[i:j]] = (i + j - 1) / 2.0 + 1.0
        i = j
    return ranks


def spearman(x: Sequence[Any], y: Sequence[Any]) -> Optional[float]:
    pairs = [(_finite(a), _finite(b)) for a, b in zip(x, y)]
    clean = [(a, b) for a, b in pairs if a is not None and b is not None]
    if len(clean) < 3:
        return None
    a = np.asarray([p[0] for p in clean], dtype=float)
    b = np.asarray([p[1] for p in clean], dtype=float)
    ra, rb = _rank(a), _rank(b)
    if ra.std() <= 1e-12 or rb.std() <= 1e-12:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def pearson(x: Sequence[Any], y: Sequence[Any]) -> Optional[float]:
    pairs = [(_finite(a), _finite(b)) for a, b in zip(x, y)]
    clean = [(a, b) for a, b in pairs if a is not None and b is not None]
    if len(clean) < 3:
        return None
    a = np.asarray([p[0] for p in clean], dtype=float)
    b = np.asarray([p[1] for p in clean], dtype=float)
    if a.std() <= 1e-12 or b.std() <= 1e-12:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def prediction_metrics(actual: Sequence[float], predicted: Sequence[float]) -> Dict[str, Optional[float]]:
    y = np.asarray(actual, dtype=float)
    yhat = np.asarray(predicted, dtype=float)
    if y.size == 0 or y.size != yhat.size:
        raise ValueError("actual and predicted must be non-empty and aligned")
    errors = y - yhat
    tss = float(np.sum((y - y.mean()) ** 2))
    rss = float(np.sum(errors ** 2))
    return {
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
        "r2": (1.0 - rss / tss) if tss > 0 else None,
        "spearman": spearman(yhat.tolist(), y.tolist()),
    }


def _scope_rows(rows: Sequence[Mapping[str, Any]], spec: ComponentSpec) -> List[Dict[str, Any]]:
    spec.validate()
    allowed = set(spec.subject_types)
    scoped: List[Dict[str, Any]] = []
    for source in rows:
        if str(source.get("subject_type") or "") not in allowed:
            continue
        component = _finite(source.get(spec.column))
        log_price = _finite(source.get("log_price"))
        scarcity = _finite(source.get("pull_scarcity"))
        if component is None or log_price is None or scarcity is None:
            continue
        row = dict(source)
        row[spec.column] = component
        row["log_price"] = log_price
        row["pull_scarcity"] = scarcity
        scoped.append(row)
    return scoped


def descriptive_relationships(rows: Sequence[Mapping[str, Any]], spec: ComponentSpec) -> Dict[str, Any]:
    scoped = _scope_rows(rows, spec)
    component = [float(row[spec.column]) for row in scoped]
    log_price = [float(row["log_price"]) for row in scoped]
    by_era: Dict[str, Any] = {}
    for era in sorted({str(row.get("era") or "") for row in scoped}):
        subset = [row for row in scoped if str(row.get("era") or "") == era]
        by_era[era] = {
            "n_cards": len(subset),
            "n_sets": len({str(row["set_id"]) for row in subset}),
            "spearman_vs_log_price": spearman(
                [row[spec.column] for row in subset], [row["log_price"] for row in subset]
            ),
            "pearson_vs_log_price": pearson(
                [row[spec.column] for row in subset], [row["log_price"] for row in subset]
            ),
        }
    return {
        "n_cards": len(scoped),
        "n_sets": len({str(row["set_id"]) for row in scoped}),
        "spearman_vs_log_price": spearman(component, log_price),
        "pearson_vs_log_price": pearson(component, log_price),
        "by_era": by_era,
    }


def model_specs(spec: ComponentSpec, controls: Sequence[str] = DEFAULT_CONTROLS) -> Dict[str, List[str]]:
    component = f"component::{spec.column}"
    scarcity = "centered::pull_scarcity"
    interaction = f"interaction::{spec.column}::pull_scarcity"
    base = list(controls)
    models = {
        "M0_controls_only": base,
        "M1_component": base + [component],
        "M2_scarcity": base + [scarcity],
        "M3_component_scarcity": base + [component, scarcity],
    }
    if spec.interaction_with_scarcity:
        models["M4_interaction"] = base + [component, scarcity, interaction]
        models["M5_plus_treatment"] = base + [component, scarcity, interaction, "treatment_prestige"]
    else:
        models["M4_plus_treatment"] = base + [component, scarcity, "treatment_prestige"]
    return models


def _fit_centers(train: Sequence[Mapping[str, Any]], spec: ComponentSpec) -> Dict[str, float]:
    return {
        spec.column: float(np.mean([float(row[spec.column]) for row in train])),
        "pull_scarcity": float(np.mean([float(row["pull_scarcity"]) for row in train])),
    }


def _numeric_column(rows: Sequence[Mapping[str, Any]], token: str, spec: ComponentSpec,
                    centers: Mapping[str, float]) -> np.ndarray:
    if token == f"component::{spec.column}":
        return np.asarray([float(row[spec.column]) - centers[spec.column] for row in rows], dtype=float)
    if token == "centered::pull_scarcity":
        return np.asarray([float(row["pull_scarcity"]) - centers["pull_scarcity"] for row in rows], dtype=float)
    if token == f"interaction::{spec.column}::pull_scarcity":
        return (_numeric_column(rows, f"component::{spec.column}", spec, centers)
                * _numeric_column(rows, "centered::pull_scarcity", spec, centers))
    values = [_finite(row.get(token)) for row in rows]
    if any(value is None for value in values):
        raise ValueError(f"predictor {token!r} contains missing/non-finite values")
    return np.asarray(values, dtype=float)


def _design(rows: Sequence[Mapping[str, Any]], predictors: Sequence[str], spec: ComponentSpec,
            centers: Mapping[str, float], *, era_levels: Sequence[str] = (),
            intercept: bool) -> Tuple[np.ndarray, List[str]]:
    columns: List[np.ndarray] = []
    names: List[str] = []
    if intercept:
        columns.append(np.ones(len(rows), dtype=float)); names.append("intercept")
    for token in predictors:
        columns.append(_numeric_column(rows, token, spec, centers)); names.append(token)
    for era in era_levels:
        columns.append(np.asarray([1.0 if str(row.get("era") or "") == era else 0.0 for row in rows]))
        names.append(f"era::{era}")
    return (np.column_stack(columns) if columns else np.empty((len(rows), 0))), names


def _drop_constant_columns(matrix: np.ndarray, names: Sequence[str]) -> Tuple[np.ndarray, List[str], List[str]]:
    keep: List[int] = []
    dropped: List[str] = []
    for index, name in enumerate(names):
        if name == "intercept" or float(np.std(matrix[:, index])) > 1e-10:
            keep.append(index)
        else:
            dropped.append(name)
    return matrix[:, keep], [names[i] for i in keep], dropped


def grouped_leave_set_out_cv(rows: Sequence[Mapping[str, Any]], predictors: Sequence[str],
                             spec: ComponentSpec) -> Optional[Dict[str, Any]]:
    """Leave one whole set out; centering and era levels are fit on train only."""
    scoped = _scope_rows(rows, spec)
    set_ids = sorted({str(row["set_id"]) for row in scoped})
    if len(set_ids) < 3:
        return None
    predictions: List[Dict[str, Any]] = []
    folds: List[Dict[str, Any]] = []
    for held_out in set_ids:
        train = [row for row in scoped if str(row["set_id"]) != held_out]
        test = [row for row in scoped if str(row["set_id"]) == held_out]
        if not test:
            continue
        centers = _fit_centers(train, spec)
        train_eras = sorted({str(row.get("era") or "") for row in train})
        era_levels = train_eras[1:] if len(train_eras) > 1 else []
        x_train, names = _design(train, predictors, spec, centers, era_levels=era_levels, intercept=True)
        x_test, _ = _design(test, predictors, spec, centers, era_levels=era_levels, intercept=True)
        x_train, kept, dropped = _drop_constant_columns(x_train, names)
        x_test = x_test[:, [names.index(name) for name in kept]]
        if len(train) <= x_train.shape[1] + 1:
            continue
        y_train = np.asarray([float(row["log_price"]) for row in train])
        beta, *_ = np.linalg.lstsq(x_train, y_train, rcond=None)
        y_test = np.asarray([float(row["log_price"]) for row in test])
        y_hat = x_test @ beta
        folds.append({
            "set_id": held_out, "set_name": test[0].get("set_name"), "n": len(test),
            "centering": dict(centers), "dropped_predictors": dropped,
            **prediction_metrics(y_test, y_hat),
        })
        for row, actual, predicted in zip(test, y_test.tolist(), y_hat.tolist()):
            predictions.append({
                "card_id": str(row.get("card_id") or row.get("canonical_card_id") or ""),
                "set_id": held_out, "actual": actual, "predicted": predicted,
            })
    if not predictions:
        return None
    metrics = prediction_metrics([row["actual"] for row in predictions],
                                 [row["predicted"] for row in predictions])
    return {"n": len(predictions), "n_folds": len(folds), **metrics,
            "folds": folds, "_predictions": predictions}


def _demean_by_set(matrix: np.ndarray, groups: Sequence[str]) -> np.ndarray:
    out = np.array(matrix, dtype=float, copy=True)
    group_array = np.asarray(groups)
    for group in sorted(set(groups)):
        mask = group_array == group
        out[mask] -= out[mask].mean(axis=0)
    return out


def fit_set_fixed_effects(rows: Sequence[Mapping[str, Any]], predictors: Sequence[str],
                          spec: ComponentSpec) -> Optional[Dict[str, Any]]:
    """Set-FE OLS with set-cluster SE and optional two-way set/subject SE."""
    scoped = _scope_rows(rows, spec)
    groups = [str(row["set_id"]) for row in scoped]
    if len(set(groups)) < 3 or len(scoped) <= len(predictors) + 3:
        return None
    centers = _fit_centers(scoped, spec)
    x_raw, names = _design(scoped, predictors, spec, centers, intercept=False)
    y = np.asarray([float(row["log_price"]) for row in scoped])
    x = _demean_by_set(x_raw, groups)
    y_within = _demean_by_set(y.reshape(-1, 1), groups).ravel()
    x, kept, dropped = _drop_constant_columns(x, names)
    if x.shape[1] == 0:
        return None
    beta, *_ = np.linalg.lstsq(x, y_within, rcond=None)
    residual = y_within - x @ beta
    n, k = x.shape
    xtx_inv = np.linalg.pinv(x.T @ x)

    def cluster_meat(labels: Sequence[str]) -> Tuple[np.ndarray, int]:
        label_array = np.asarray(labels)
        unique_labels = sorted(set(labels))
        meat = np.zeros((k, k), dtype=float)
        for label in unique_labels:
            mask = label_array == label
            score = x[mask].T @ residual[mask]
            meat += np.outer(score, score)
        return meat, len(unique_labels)

    def corrected_vcov(meat: np.ndarray, clusters: int) -> np.ndarray:
        correction = (clusters / max(clusters - 1, 1)) * ((n - 1) / max(n - k - clusters, 1))
        return xtx_inv @ meat @ xtx_inv * correction

    set_meat, set_clusters = cluster_meat(groups)
    vcov = corrected_vcov(set_meat, set_clusters)
    stderr = np.sqrt(np.maximum(np.diag(vcov), 0.0))
    subject_labels = [str(row.get("subject_cluster_key") or "") for row in scoped]
    two_way_stderr = None
    if all(subject_labels) and len(set(subject_labels)) >= 3:
        subject_meat, subject_clusters = cluster_meat(subject_labels)
        intersections = [f"{set_id}::{subject}" for set_id, subject in zip(groups, subject_labels)]
        intersection_meat, intersection_clusters = cluster_meat(intersections)
        two_way_vcov = (corrected_vcov(set_meat, set_clusters)
                        + corrected_vcov(subject_meat, subject_clusters)
                        - corrected_vcov(intersection_meat, intersection_clusters))
        two_way_stderr = np.sqrt(np.maximum(np.diag(two_way_vcov), 0.0))
    tss = float(np.sum((y_within - y_within.mean()) ** 2))
    rss = float(np.sum(residual ** 2))
    return {
        "n": n, "n_sets": set_clusters, "centering": dict(centers), "columns": kept,
        "dropped_collinear_columns": dropped,
        "coefficients": {name: float(beta[i]) for i, name in enumerate(kept)},
        "cluster_robust_se": {name: float(stderr[i]) for i, name in enumerate(kept)},
        "t_stats": {name: (float(beta[i] / stderr[i]) if stderr[i] > 0 else None)
                    for i, name in enumerate(kept)},
        "two_way_cluster_robust_se_set_subject": (
            {name: float(two_way_stderr[i]) for i, name in enumerate(kept)}
            if two_way_stderr is not None else None
        ),
        "two_way_t_stats_set_subject": (
            {name: (float(beta[i] / two_way_stderr[i]) if two_way_stderr[i] > 0 else None)
             for i, name in enumerate(kept)} if two_way_stderr is not None else None
        ),
        "within_r2": (1.0 - rss / tss) if tss > 0 else None,
    }


def cluster_bootstrap_coefficients(rows: Sequence[Mapping[str, Any]], predictors: Sequence[str],
                                   spec: ComponentSpec, *, draws: int,
                                   seed: int = RANDOM_SEED) -> Dict[str, Any]:
    if draws <= 0:
        return {}
    scoped = _scope_rows(rows, spec)
    by_set: Dict[str, List[Dict[str, Any]]] = {}
    for row in scoped:
        by_set.setdefault(str(row["set_id"]), []).append(dict(row))
    set_ids = sorted(by_set)
    if len(set_ids) < 3:
        return {}
    rng = np.random.default_rng(seed)
    samples: Dict[str, List[float]] = {}
    for _ in range(draws):
        picked = rng.choice(len(set_ids), size=len(set_ids), replace=True)
        boot: List[Dict[str, Any]] = []
        for copy_index, source_index in enumerate(picked):
            source = set_ids[int(source_index)]
            for row in by_set[source]:
                copied = dict(row); copied["set_id"] = f"{source}__boot_{copy_index}"; boot.append(copied)
        fit = fit_set_fixed_effects(boot, predictors, spec)
        if fit is None:
            continue
        for name, value in fit["coefficients"].items():
            samples.setdefault(name, []).append(float(value))
    output: Dict[str, Any] = {}
    for name, values in samples.items():
        if len(values) < 20:
            output[name] = {"draws": len(values), "ci_low": None, "ci_high": None}
            continue
        array = np.asarray(values)
        output[name] = {
            "draws": len(values), "ci_low": float(np.percentile(array, 2.5)),
            "ci_high": float(np.percentile(array, 97.5)), "share_positive": float(np.mean(array > 0)),
        }
    return output


def _aligned_predictions(base: Mapping[str, Any], richer: Mapping[str, Any]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    key = lambda row: (str(row["set_id"]), str(row["card_id"]))
    base_map = {key(row): dict(row) for row in base.get("_predictions", [])}
    rich_map = {key(row): dict(row) for row in richer.get("_predictions", [])}
    keys = sorted(set(base_map) & set(rich_map))
    if len(keys) != len(base_map) or len(keys) != len(rich_map):
        raise ValueError("nested-model CV predictions are not perfectly aligned")
    return [(base_map[k], rich_map[k]) for k in keys]


def incremental_lift(base: Mapping[str, Any], richer: Mapping[str, Any], *,
                     bootstrap_draws: int = 0, seed: int = RANDOM_SEED) -> Dict[str, Any]:
    aligned = _aligned_predictions(base, richer)
    bm = prediction_metrics([a["actual"] for a, _ in aligned], [a["predicted"] for a, _ in aligned])
    rm = prediction_metrics([b["actual"] for _, b in aligned], [b["predicted"] for _, b in aligned])
    result: Dict[str, Any] = {
        "n": len(aligned), "base_metrics": bm, "richer_metrics": rm,
        "mae_reduction": bm["mae"] - rm["mae"],
        "mae_reduction_pct": 100.0 * (bm["mae"] - rm["mae"]) / bm["mae"] if bm["mae"] else None,
        "rmse_reduction": bm["rmse"] - rm["rmse"],
        "rmse_reduction_pct": 100.0 * (bm["rmse"] - rm["rmse"]) / bm["rmse"] if bm["rmse"] else None,
        "r2_gain": None if bm["r2"] is None or rm["r2"] is None else rm["r2"] - bm["r2"],
        "spearman_gain": (None if bm["spearman"] is None or rm["spearman"] is None
                          else rm["spearman"] - bm["spearman"]),
    }
    if bootstrap_draws > 0:
        by_set: Dict[str, List[Tuple[Dict[str, Any], Dict[str, Any]]]] = {}
        for pair in aligned:
            by_set.setdefault(str(pair[0]["set_id"]), []).append(pair)
        set_ids = sorted(by_set); rng = np.random.default_rng(seed)
        samples = {name: [] for name in ("mae_reduction", "rmse_reduction", "r2_gain", "spearman_gain")}
        for _ in range(bootstrap_draws):
            picked = rng.choice(len(set_ids), size=len(set_ids), replace=True)
            pairs = [pair for index in picked for pair in by_set[set_ids[int(index)]]]
            b = prediction_metrics([a["actual"] for a, _ in pairs], [a["predicted"] for a, _ in pairs])
            r = prediction_metrics([a["actual"] for a, _ in pairs], [b["predicted"] for _, b in pairs])
            values = {
                "mae_reduction": b["mae"] - r["mae"], "rmse_reduction": b["rmse"] - r["rmse"],
                "r2_gain": None if b["r2"] is None or r["r2"] is None else r["r2"] - b["r2"],
                "spearman_gain": (None if b["spearman"] is None or r["spearman"] is None
                                  else r["spearman"] - b["spearman"]),
            }
            for name, value in values.items():
                if value is not None and math.isfinite(value): samples[name].append(float(value))
        result["cluster_bootstrap_by_held_out_set"] = {
            name: {
                "draws": len(values),
                "ci_low": float(np.percentile(values, 2.5)) if len(values) >= 20 else None,
                "ci_high": float(np.percentile(values, 97.5)) if len(values) >= 20 else None,
                "share_positive": float(np.mean(np.asarray(values) > 0)) if values else None,
            } for name, values in samples.items()
        }
    return result


def _public_cv(cv: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return None if cv is None else {key: value for key, value in cv.items() if key != "_predictions"}


def run_component_suite(rows: Sequence[Mapping[str, Any]], spec: ComponentSpec, *,
                        controls: Sequence[str] = DEFAULT_CONTROLS,
                        bootstrap_draws: int = 0) -> Dict[str, Any]:
    scoped = _scope_rows(rows, spec)
    specs = model_specs(spec, controls)
    models: Dict[str, Any] = {}
    raw_cv: Dict[str, Dict[str, Any]] = {}
    for index, (name, predictors) in enumerate(specs.items()):
        cv = grouped_leave_set_out_cv(scoped, predictors, spec)
        fit = fit_set_fixed_effects(scoped, predictors, spec)
        raw_cv[name] = cv or {}
        models[name] = {
            "predictors": list(predictors), "leave_whole_set_out_cv": _public_cv(cv),
            "set_fixed_effects_fit": fit,
            "cluster_bootstrap_coefficient_ci": (
                cluster_bootstrap_coefficients(scoped, predictors, spec, draws=bootstrap_draws,
                                               seed=RANDOM_SEED + index)
                if bootstrap_draws > 0 and fit is not None else {}
            ),
        }

    def lift(base: str, richer: str, seed_offset: int) -> Optional[Dict[str, Any]]:
        if not raw_cv.get(base) or not raw_cv.get(richer): return None
        return incremental_lift(raw_cv[base], raw_cv[richer], bootstrap_draws=bootstrap_draws,
                                seed=RANDOM_SEED + seed_offset)

    increments = {
        "component_over_controls_M1_vs_M0": lift("M0_controls_only", "M1_component", 101),
        "scarcity_over_controls_M2_vs_M0": lift("M0_controls_only", "M2_scarcity", 102),
        "component_over_scarcity_M3_vs_M2": lift("M2_scarcity", "M3_component_scarcity", 103),
        "scarcity_over_component_M3_vs_M1": lift("M1_component", "M3_component_scarcity", 104),
    }
    if spec.interaction_with_scarcity:
        increments["interaction_over_additive_M4_vs_M3"] = lift("M3_component_scarcity", "M4_interaction", 105)
        increments["treatment_over_interaction_M5_vs_M4"] = lift("M4_interaction", "M5_plus_treatment", 106)
    else:
        increments["treatment_over_additive_M4_vs_M3"] = lift("M3_component_scarcity", "M4_plus_treatment", 105)

    by_era: Dict[str, Any] = {}
    for era in sorted({str(row.get("era") or "") for row in scoped}):
        subset = [row for row in scoped if str(row.get("era") or "") == era]
        n_sets = len({str(row["set_id"]) for row in subset})
        if n_sets < MIN_SETS_PER_ERA or len(subset) < MIN_CARDS_PER_ERA:
            by_era[era] = {"eligible": False, "n_cards": len(subset), "n_sets": n_sets,
                           "reason": f"requires >= {MIN_SETS_PER_ERA} sets and >= {MIN_CARDS_PER_ERA} cards"}
            continue
        base = grouped_leave_set_out_cv(subset, specs["M2_scarcity"], spec)
        richer = grouped_leave_set_out_cv(subset, specs["M3_component_scarcity"], spec)
        by_era[era] = {
            "eligible": True, "n_cards": len(subset), "n_sets": n_sets,
            "component_over_scarcity": incremental_lift(base, richer) if base and richer else None,
            "models": {"M2_scarcity": _public_cv(base), "M3_component_scarcity": _public_cv(richer)},
        }
    return {
        "component": {"name": spec.name, "column": spec.column,
                      "subject_types": list(spec.subject_types), "role": spec.role,
                      "cross_bucket_comparable": spec.cross_bucket_comparable},
        "sample": {"n_cards": len(scoped), "n_sets": len({str(r["set_id"]) for r in scoped}),
                   "n_eras": len({str(r.get("era") or "") for r in scoped})},
        "relationships": descriptive_relationships(scoped, spec),
        "models": models, "incremental_lift_out_of_sample": increments, "by_era": by_era,
    }


def compare_components(rows: Sequence[Mapping[str, Any]], specs: Iterable[ComponentSpec], *,
                       controls: Sequence[str] = DEFAULT_CONTROLS,
                       bootstrap_draws: int = 0) -> Dict[str, Any]:
    """Run every declared component under one methodology; never choose a winner."""
    suites: Dict[str, Any] = {}; summary: List[Dict[str, Any]] = []
    for spec in specs:
        suite = run_component_suite(rows, spec, controls=controls, bootstrap_draws=bootstrap_draws)
        suites[spec.name] = suite
        cv = (suite["models"].get("M3_component_scarcity") or {}).get("leave_whole_set_out_cv") or {}
        lift = suite["incremental_lift_out_of_sample"].get("component_over_scarcity_M3_vs_M2") or {}
        summary.append({
            "component": spec.name, "role": spec.role, "subject_types": list(spec.subject_types),
            "n_cards": suite["sample"]["n_cards"], "n_sets": suite["sample"]["n_sets"],
            "raw_spearman_vs_log_price": suite["relationships"].get("spearman_vs_log_price"),
            "oos_mae": cv.get("mae"), "oos_rmse": cv.get("rmse"), "oos_r2": cv.get("r2"),
            "oos_spearman": cv.get("spearman"),
            "incremental_mae_reduction_pct_vs_scarcity": lift.get("mae_reduction_pct"),
            "incremental_rmse_reduction_pct_vs_scarcity": lift.get("rmse_reduction_pct"),
            "incremental_r2_gain_vs_scarcity": lift.get("r2_gain"),
            "incremental_spearman_gain_vs_scarcity": lift.get("spearman_gain"),
        })
    return {
        "methodology": {
            "outcome": "log(card market price)",
            "validation": "leave-whole-set-out grouped cross-validation",
            "cv_centering": "fit on training sets only; applied unchanged to held-out set",
            "inference": "set fixed effects + set-cluster robust SE; two-way set/subject SE when subject key exists",
            "uncertainty": "whole-set cluster bootstrap when bootstrap_draws > 0",
            "selection_policy": "report all registered components; do not tune or select V6 here",
            "weight_transfer_policy": "price-fit coefficients must never be copied into Collector Appeal or RIP weights",
        },
        "component_summary": summary, "components": suites,
    }
