from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import NormalDist
from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from backend.simulations.monteCarloSimV2 import resolve_slot_outcomes_from_state, sample_pack_state
from backend.simulations.utils.packStateModels.packStateCoercion import normalize_rarity
from backend.simulations.utils.packStateModels.packStateModelOrchestrator import (
    normalize_era_key,
    resolve_era_builder,
    resolve_pack_state_model,
)


MODE_STATE = "state"
MODE_RARITY = "rarity"
MODE_CONSISTENCY = "consistency"
VALIDATION_MODES = {MODE_STATE, MODE_RARITY, MODE_CONSISTENCY}

DIMENSION_STATE = "state"
DIMENSION_RARE_SLOT = "rare_slot_rarity"
DIMENSION_REVERSE_SLOT = "reverse_slot_rarity"
DIMENSION_REVERSE_1 = "reverse_1_rarity"
DIMENSION_REVERSE_2 = "reverse_2_rarity"
DIMENSION_AGGREGATE_HITS = "aggregate_hit_frequency"

DEFAULT_CONFIDENCE_LEVEL = 0.95
DEFAULT_RESIDUAL_THRESHOLD = 0.02
DEFAULT_MIN_CONFIDENCE_SAMPLE_SIZE = 100


def _normalize_state_name(state_name: str) -> str:
    return str(state_name or "").strip().lower().replace(" ", "_")


def _normalize_dimension_name(dimension: str) -> str:
    return str(dimension or "").strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_category_name(
    *,
    dimension: str,
    raw_value: str,
    state_alias_map: Optional[Mapping[str, str]] = None,
) -> str:
    value = str(raw_value or "").strip()
    if _normalize_dimension_name(dimension) == DIMENSION_STATE:
        normalized = _normalize_state_name(value)
        if state_alias_map and normalized in state_alias_map:
            return _normalize_state_name(state_alias_map[normalized])
        return normalized
    if _normalize_dimension_name(dimension) == DIMENSION_AGGREGATE_HITS:
        return _normalize_state_name(value)
    return normalize_rarity(value)


def _count_non_regular_slot_hits(slot_outcomes: Mapping[str, str]) -> int:
    count = 0
    for rarity in slot_outcomes.values():
        normalized = normalize_rarity(rarity)
        if normalized not in {"rare", "regular reverse"}:
            count += 1
    return count


def _normalize_probabilities(probabilities: Mapping[str, float]) -> Dict[str, float]:
    total = float(sum(float(v) for v in probabilities.values()))
    if total <= 0:
        return {str(k): 0.0 for k in probabilities}
    return {str(k): float(v) / total for k, v in probabilities.items()}


def _series_from_counts(counts: Mapping[str, int], denom: Optional[float] = None) -> pd.Series:
    counts_series = pd.Series({str(k): float(v) for k, v in counts.items()}, dtype=float)
    used_denom = float(denom) if denom is not None else float(counts_series.sum())
    if used_denom <= 0:
        return counts_series * 0.0
    return counts_series / used_denom


def compute_wilson_interval(
    *,
    observed_count: int,
    sample_size: int,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> Dict[str, Any]:
    """Compute Wilson score interval for a binomial proportion.

    Method: Wilson interval (normal approximation with continuity correction omitted).
    This is a standard interval for binomial proportions with better small-sample
    behavior than naive Wald intervals.
    """
    n = int(sample_size)
    if n <= 0:
        return {
            "lower": None,
            "upper": None,
            "confidence_level": float(confidence_level),
            "method": "wilson",
        }

    count = max(0, min(int(observed_count), n))
    p_hat = float(count) / float(n)

    alpha = 1.0 - float(confidence_level)
    z = NormalDist().inv_cdf(1.0 - alpha / 2.0)
    z2 = z * z

    denominator = 1.0 + (z2 / n)
    center = (p_hat + z2 / (2.0 * n)) / denominator
    margin = (
        z
        * np.sqrt((p_hat * (1.0 - p_hat) / n) + (z2 / (4.0 * n * n)))
        / denominator
    )

    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)

    return {
        "lower": float(lower),
        "upper": float(upper),
        "confidence_level": float(confidence_level),
        "method": "wilson",
    }


def _classify_review_priority(
    *,
    expected_probability: float,
    observed_probability: Optional[float],
    expected_outside_ci: Optional[bool],
    absolute_difference: Optional[float],
    observed_sample_size: Optional[int],
    residual_threshold: float,
    minimum_confidence_sample_size: int,
) -> Dict[str, str]:
    if observed_probability is None:
        return {
            "review_flag": "insufficient_observed_data",
            "review_priority": "data_needed",
            "review_label": "possible sampling noise",
        }

    abs_diff = float(absolute_difference or 0.0)
    n = int(observed_sample_size or 0)
    high_confidence_n = n >= int(minimum_confidence_sample_size)

    if bool(expected_outside_ci) and abs_diff >= float(residual_threshold) and high_confidence_n:
        return {
            "review_flag": "flagged_for_review",
            "review_priority": "high",
            "review_label": "possible structural mismatch",
        }
    if bool(expected_outside_ci):
        return {
            "review_flag": "flagged_for_review_low_confidence",
            "review_priority": "medium",
            "review_label": "possible structural mismatch",
        }
    if abs_diff >= float(residual_threshold):
        return {
            "review_flag": "possible_sampling_noise",
            "review_priority": "low",
            "review_label": "possible sampling noise",
        }

    return {
        "review_flag": "no_material_mismatch_detected",
        "review_priority": "low",
        "review_label": "possible sampling noise",
    }


def _build_expected_distributions(config: Any) -> Dict[str, Dict[str, float]]:
    model = resolve_pack_state_model(config)
    state_probabilities = {
        _normalize_state_name(state): float(prob)
        for state, prob in model.get("state_probabilities", {}).items()
    }
    state_probabilities = _normalize_probabilities(state_probabilities)

    state_outcomes = {
        _normalize_state_name(state): {
            "rare": normalize_rarity(slots.get("rare", "rare")),
            "reverse_1": normalize_rarity(slots.get("reverse_1", "regular reverse")),
            "reverse_2": normalize_rarity(slots.get("reverse_2", "regular reverse")),
        }
        for state, slots in model.get("state_outcomes", {}).items()
    }

    rare_slot: MutableMapping[str, float] = defaultdict(float)
    reverse_1: MutableMapping[str, float] = defaultdict(float)
    reverse_2: MutableMapping[str, float] = defaultdict(float)
    reverse_slot: MutableMapping[str, float] = defaultdict(float)
    aggregate_hits: MutableMapping[str, float] = defaultdict(float)

    for state_name, probability in state_probabilities.items():
        outcomes = state_outcomes.get(state_name)
        if not outcomes:
            continue
        rare_slot[outcomes["rare"]] += probability
        reverse_1[outcomes["reverse_1"]] += probability
        reverse_2[outcomes["reverse_2"]] += probability
        reverse_slot[outcomes["reverse_1"]] += probability
        reverse_slot[outcomes["reverse_2"]] += probability

        hit_count = _count_non_regular_slot_hits(outcomes)
        if hit_count == 0:
            aggregate_hits["no_non_regular_hit_pack"] += probability
        else:
            aggregate_hits["any_non_regular_hit_pack"] += probability
        if hit_count >= 2:
            aggregate_hits["two_or_more_non_regular_hit_pack"] += probability

    reverse_slot = {k: v / 2.0 for k, v in reverse_slot.items()}

    return {
        DIMENSION_STATE: _normalize_probabilities(state_probabilities),
        DIMENSION_RARE_SLOT: _normalize_probabilities(dict(rare_slot)),
        DIMENSION_REVERSE_1: _normalize_probabilities(dict(reverse_1)),
        DIMENSION_REVERSE_2: _normalize_probabilities(dict(reverse_2)),
        DIMENSION_REVERSE_SLOT: _normalize_probabilities(reverse_slot),
        DIMENSION_AGGREGATE_HITS: _normalize_probabilities(dict(aggregate_hits)),
    }


def _simulate_distributions_v2(
    config: Any,
    *,
    n_packs: int,
    random_seed: Optional[int] = 7,
) -> Dict[str, Dict[str, float]]:
    rng = np.random.default_rng(random_seed)

    state_counts: MutableMapping[str, int] = defaultdict(int)
    rare_slot_counts: MutableMapping[str, int] = defaultdict(int)
    reverse_1_counts: MutableMapping[str, int] = defaultdict(int)
    reverse_2_counts: MutableMapping[str, int] = defaultdict(int)
    reverse_slot_counts: MutableMapping[str, int] = defaultdict(int)
    aggregate_hit_counts: MutableMapping[str, int] = defaultdict(int)

    for _ in range(int(n_packs)):
        pack_state = sample_pack_state(config=config, rng=rng)
        state_name = _normalize_state_name(str(pack_state.get("state", "")))
        state_counts[state_name] += 1

        slot_outcomes = resolve_slot_outcomes_from_state(pack_state=pack_state, config=config, rng=rng)
        rare = normalize_rarity(slot_outcomes["rare"])
        r1 = normalize_rarity(slot_outcomes["reverse_1"])
        r2 = normalize_rarity(slot_outcomes["reverse_2"])

        rare_slot_counts[rare] += 1
        reverse_1_counts[r1] += 1
        reverse_2_counts[r2] += 1
        reverse_slot_counts[r1] += 1
        reverse_slot_counts[r2] += 1

        hit_count = _count_non_regular_slot_hits(slot_outcomes)
        if hit_count == 0:
            aggregate_hit_counts["no_non_regular_hit_pack"] += 1
        else:
            aggregate_hit_counts["any_non_regular_hit_pack"] += 1
        if hit_count >= 2:
            aggregate_hit_counts["two_or_more_non_regular_hit_pack"] += 1

    return {
        DIMENSION_STATE: _series_from_counts(state_counts).to_dict(),
        DIMENSION_RARE_SLOT: _series_from_counts(rare_slot_counts).to_dict(),
        DIMENSION_REVERSE_1: _series_from_counts(reverse_1_counts).to_dict(),
        DIMENSION_REVERSE_2: _series_from_counts(reverse_2_counts).to_dict(),
        DIMENSION_REVERSE_SLOT: _series_from_counts(reverse_slot_counts).to_dict(),
        DIMENSION_AGGREGATE_HITS: _series_from_counts(aggregate_hit_counts).to_dict(),
    }


def _parse_counts_map(
    raw_counts: Mapping[str, Any],
    *,
    dimension: str,
    state_alias_map: Optional[Mapping[str, str]] = None,
) -> Dict[str, int]:
    parsed: MutableMapping[str, int] = defaultdict(int)
    for raw_key, raw_val in raw_counts.items():
        normalized_key = _normalize_category_name(
            dimension=dimension,
            raw_value=str(raw_key),
            state_alias_map=state_alias_map,
        )
        parsed[normalized_key] += int(raw_val)
    return dict(parsed)


def _parse_observed_from_dataframe(
    df: pd.DataFrame,
    *,
    state_alias_map: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    columns = {str(c).strip().lower(): c for c in df.columns}

    if {"dimension", "category", "count"}.issubset(columns.keys()):
        grouped: Dict[str, Dict[str, int]] = {}
        for _, row in df.iterrows():
            dimension = _normalize_dimension_name(str(row[columns["dimension"]]))
            category = str(row[columns["category"]])
            count = int(row[columns["count"]])
            grouped.setdefault(dimension, {})
            key = _normalize_category_name(
                dimension=dimension,
                raw_value=category,
                state_alias_map=state_alias_map,
            )
            grouped[dimension][key] = grouped[dimension].get(key, 0) + count
        return {"counts_by_dimension": grouped}

    if {"state", "count"}.issubset(columns.keys()):
        grouped: Dict[str, int] = defaultdict(int)
        for _, row in df.iterrows():
            key = _normalize_category_name(
                dimension=DIMENSION_STATE,
                raw_value=str(row[columns["state"]]),
                state_alias_map=state_alias_map,
            )
            grouped[key] += int(row[columns["count"]])
        return {"counts_by_dimension": {DIMENSION_STATE: dict(grouped)}}

    raise ValueError(
        "Observed DataFrame format not recognized. Use either columns "
        "[dimension, category, count] or [state, count]."
    )


def load_observed_pull_data(
    source: Any,
    *,
    state_alias_map: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Load observed pull data from dict/JSON/CSV/DataFrame into a normalized structure."""

    loaded: Dict[str, Any]

    if isinstance(source, pd.DataFrame):
        loaded = _parse_observed_from_dataframe(source, state_alias_map=state_alias_map)
    elif isinstance(source, Mapping):
        loaded = deepcopy(dict(source))
    elif isinstance(source, (str, Path)):
        path = Path(source)
        suffix = path.suffix.lower()
        if suffix == ".json":
            loaded = json.loads(path.read_text(encoding="utf-8"))
        elif suffix == ".csv":
            frame = pd.read_csv(path)
            loaded = _parse_observed_from_dataframe(frame, state_alias_map=state_alias_map)
        else:
            raise ValueError(f"Unsupported observed data file type: {path.suffix}")
    else:
        raise TypeError("Observed data source must be DataFrame, dict, JSON path, or CSV path.")

    counts_by_dimension = loaded.get("counts_by_dimension", {})

    if not counts_by_dimension:
        remapped = {
            DIMENSION_STATE: loaded.get("state_counts", {}),
            DIMENSION_RARE_SLOT: loaded.get("rare_slot_counts", {}),
            DIMENSION_REVERSE_1: loaded.get("reverse_1_counts", {}),
            DIMENSION_REVERSE_2: loaded.get("reverse_2_counts", {}),
            DIMENSION_REVERSE_SLOT: loaded.get("reverse_slot_counts", {}),
            DIMENSION_AGGREGATE_HITS: loaded.get("aggregate_hit_counts", {}),
        }
        counts_by_dimension = {k: v for k, v in remapped.items() if v}

    normalized_counts: Dict[str, Dict[str, int]] = {}
    for raw_dimension, raw_counts in counts_by_dimension.items():
        if not raw_counts:
            continue
        dimension = _normalize_dimension_name(raw_dimension)
        if not isinstance(raw_counts, Mapping):
            raise ValueError(f"Counts for dimension '{dimension}' must be a mapping of category -> count.")
        normalized_counts[dimension] = _parse_counts_map(
            raw_counts,
            dimension=dimension,
            state_alias_map=state_alias_map,
        )

    sample_size = loaded.get("sample_size")
    if sample_size is not None:
        sample_size = int(sample_size)

    dimension_sample_sizes = {
        _normalize_dimension_name(dim): int(val)
        for dim, val in loaded.get("dimension_sample_sizes", {}).items()
    }

    for dimension, counts in normalized_counts.items():
        inferred_n = int(sum(counts.values()))
        if dimension not in dimension_sample_sizes and inferred_n > 0:
            dimension_sample_sizes[dimension] = inferred_n

    return {
        "set_id": loaded.get("set_id"),
        "set_name": loaded.get("set_name"),
        "sample_size": sample_size,
        "source_metadata": loaded.get("source_metadata", {}),
        "notes": loaded.get("notes"),
        "counts_by_dimension": normalized_counts,
        "dimension_sample_sizes": dimension_sample_sizes,
    }


def compute_goodness_of_fit_metrics(
    *,
    expected_probabilities: Mapping[str, float],
    observed_probabilities: Mapping[str, float],
    observed_counts: Optional[Mapping[str, int]] = None,
    sample_size: Optional[int] = None,
    min_expected_count_for_chi_square: float = 5.0,
    smoothing: float = 1e-12,
) -> Dict[str, Any]:
    """Compute concrete, interpretable mismatch metrics between expected and observed distributions.

    Primary practical diagnostics:
    - mean_absolute_error
    - total_variation_distance

    Secondary information-theoretic diagnostics:
    - kl_divergence_observed_to_expected
    - jensen_shannon_divergence

    KL/JS use epsilon smoothing (``smoothing``) via clipping before normalization to avoid
    divide-by-zero and log-of-zero instability in sparse categories.

    Chi-square is only computed over categories whose expected counts satisfy:
    expected_count >= min_expected_count_for_chi_square.
    """
    categories = sorted(set(expected_probabilities.keys()) | set(observed_probabilities.keys()))
    if not categories:
        return {
            "mean_absolute_error": 0.0,
            "total_variation_distance": 0.0,
            "kl_divergence_observed_to_expected": 0.0,
            "jensen_shannon_divergence": 0.0,
            "divergence_smoothing_epsilon": float(smoothing),
            "chi_square": None,
            "chi_square_dof": 0,
            "chi_square_categories_used": [],
            "chi_square_categories_excluded": [],
        }

    p = np.array([float(expected_probabilities.get(cat, 0.0)) for cat in categories], dtype=float)
    q = np.array([float(observed_probabilities.get(cat, 0.0)) for cat in categories], dtype=float)

    p = p / p.sum() if p.sum() > 0 else np.zeros_like(p)
    q = q / q.sum() if q.sum() > 0 else np.zeros_like(q)

    abs_errors = np.abs(p - q)
    mae = float(abs_errors.mean())
    tvd = float(0.5 * abs_errors.sum())

    # Epsilon smoothing is explicit by design. Sparse observed/expected categories can
    # produce zeros that make KL/JS undefined without clipping.
    p_safe = np.clip(p, smoothing, None)
    q_safe = np.clip(q, smoothing, None)
    p_safe = p_safe / p_safe.sum()
    q_safe = q_safe / q_safe.sum()

    kl_qp = float(np.sum(q_safe * np.log(q_safe / p_safe)))
    m = 0.5 * (p_safe + q_safe)
    js = float(0.5 * np.sum(p_safe * np.log(p_safe / m)) + 0.5 * np.sum(q_safe * np.log(q_safe / m)))

    chi_square_value: Optional[float] = None
    chi_square_used: list[str] = []
    chi_square_excluded: list[str] = []

    if observed_counts is not None:
        if sample_size is None:
            sample_size = int(sum(int(v) for v in observed_counts.values()))

        if sample_size and sample_size > 0:
            chi_observed = []
            chi_expected = []
            for idx, category in enumerate(categories):
                expected_count = p[idx] * sample_size
                observed_count = float(observed_counts.get(category, 0))
                if expected_count < float(min_expected_count_for_chi_square):
                    chi_square_excluded.append(category)
                    continue
                chi_observed.append(observed_count)
                chi_expected.append(expected_count)
                chi_square_used.append(category)

            if chi_expected:
                chi_observed_arr = np.array(chi_observed, dtype=float)
                chi_expected_arr = np.array(chi_expected, dtype=float)
                chi_square_value = float(np.sum((chi_observed_arr - chi_expected_arr) ** 2 / chi_expected_arr))

    return {
        "mean_absolute_error": mae,
        "total_variation_distance": tvd,
        "kl_divergence_observed_to_expected": kl_qp,
        "jensen_shannon_divergence": js,
        "divergence_smoothing_epsilon": float(smoothing),
        "chi_square": chi_square_value,
        "chi_square_dof": max(0, len(chi_square_used) - 1),
        "chi_square_categories_used": chi_square_used,
        "chi_square_categories_excluded": chi_square_excluded,
    }


def compare_distribution_dimension(
    *,
    dimension: str,
    expected_probabilities: Mapping[str, float],
    simulated_probabilities: Optional[Mapping[str, float]] = None,
    observed_counts: Optional[Mapping[str, int]] = None,
    observed_sample_size: Optional[int] = None,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    residual_threshold: float = DEFAULT_RESIDUAL_THRESHOLD,
    minimum_confidence_sample_size: int = DEFAULT_MIN_CONFIDENCE_SAMPLE_SIZE,
) -> Dict[str, Any]:
    dimension = _normalize_dimension_name(dimension)
    observed_counts = observed_counts or {}

    if observed_sample_size is None and observed_counts:
        observed_sample_size = int(sum(observed_counts.values()))

    observed_probabilities = (
        _series_from_counts(observed_counts, denom=observed_sample_size).to_dict()
        if observed_counts
        else {}
    )

    categories = sorted(
        set(expected_probabilities.keys())
        | set((simulated_probabilities or {}).keys())
        | set(observed_probabilities.keys())
    )

    rows = []
    for category in categories:
        expected = float(expected_probabilities.get(category, 0.0))
        simulated = (
            float(simulated_probabilities.get(category, 0.0))
            if simulated_probabilities is not None
            else None
        )
        observed_prob = float(observed_probabilities.get(category, 0.0)) if observed_probabilities else None
        observed_count = int(observed_counts.get(category, 0)) if observed_counts else None

        abs_diff = None if observed_prob is None else abs(observed_prob - expected)
        rel_diff = None
        if observed_prob is not None and expected > 0:
            rel_diff = (observed_prob - expected) / expected

        expected_count = None
        if observed_sample_size is not None:
            expected_count = expected * observed_sample_size

        observed_ci = (
            compute_wilson_interval(
                observed_count=observed_count,
                sample_size=observed_sample_size,
                confidence_level=confidence_level,
            )
            if observed_count is not None and observed_sample_size is not None and observed_sample_size > 0
            else {"lower": None, "upper": None, "confidence_level": float(confidence_level), "method": "wilson"}
        )

        expected_in_observed_ci = None
        if observed_ci["lower"] is not None and observed_ci["upper"] is not None:
            expected_in_observed_ci = bool(observed_ci["lower"] <= expected <= observed_ci["upper"])

        review_tags = _classify_review_priority(
            expected_probability=expected,
            observed_probability=observed_prob,
            expected_outside_ci=(None if expected_in_observed_ci is None else (not expected_in_observed_ci)),
            absolute_difference=abs_diff,
            observed_sample_size=observed_sample_size,
            residual_threshold=residual_threshold,
            minimum_confidence_sample_size=minimum_confidence_sample_size,
        )

        rows.append(
            {
                "dimension": dimension,
                "category": category,
                "expected_probability": expected,
                "simulated_probability": simulated,
                "observed_probability": observed_prob,
                "observed_count": observed_count,
                "expected_count_at_observed_n": expected_count,
                "absolute_difference_observed_vs_expected": abs_diff,
                "relative_difference_observed_vs_expected": rel_diff,
                "difference_simulated_vs_expected": None if simulated is None else simulated - expected,
                "difference_simulated_vs_observed": (
                    None if simulated is None or observed_prob is None else simulated - observed_prob
                ),
                "observed_probability_ci_lower": observed_ci["lower"],
                "observed_probability_ci_upper": observed_ci["upper"],
                "observed_probability_ci_confidence_level": observed_ci["confidence_level"],
                "observed_probability_ci_method": observed_ci["method"],
                "expected_within_observed_ci": expected_in_observed_ci,
                "expected_outside_observed_ci": (
                    None if expected_in_observed_ci is None else (not expected_in_observed_ci)
                ),
                "review_flag": review_tags["review_flag"],
                "review_priority": review_tags["review_priority"],
                "review_label": review_tags["review_label"],
            }
        )

    comparison_df = pd.DataFrame(rows)

    metrics = None
    if observed_probabilities:
        metrics = compute_goodness_of_fit_metrics(
            expected_probabilities=expected_probabilities,
            observed_probabilities=observed_probabilities,
            observed_counts=observed_counts,
            sample_size=observed_sample_size,
        )

    return {
        "dimension": dimension,
        "observed_sample_size": observed_sample_size,
        "confidence_interval_method": "wilson",
        "confidence_level": float(confidence_level),
        "comparison_rows": rows,
        "comparison_df": comparison_df,
        "metrics": metrics,
    }


def analyze_confidence_aware_residuals(
    comparison_rows: Sequence[Mapping[str, Any]],
    *,
    top_n: int = 10,
) -> Dict[str, Any]:
    df = pd.DataFrame(list(comparison_rows))
    if df.empty:
        return {
            "high_confidence_mismatch_candidates": [],
            "low_confidence_mismatch_candidates": [],
            "likely_noise_only_categories": [],
            "categories_needing_more_data": [],
        }

    for column in (
        "absolute_difference_observed_vs_expected",
        "expected_probability",
        "observed_probability",
    ):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)

    mismatch_order = df.sort_values("absolute_difference_observed_vs_expected", ascending=False)

    high_conf = mismatch_order[
        mismatch_order["review_flag"].astype(str).isin({"flagged_for_review"})
    ].head(int(top_n))
    low_conf = mismatch_order[
        mismatch_order["review_flag"].astype(str).isin({"flagged_for_review_low_confidence"})
    ].head(int(top_n))
    likely_noise = mismatch_order[
        mismatch_order["review_flag"].astype(str).isin({"possible_sampling_noise", "no_material_mismatch_detected"})
    ].head(int(top_n))
    needs_data = mismatch_order[
        mismatch_order["review_flag"].astype(str).isin({"insufficient_observed_data"})
    ].head(int(top_n))

    cols = [
        "category",
        "expected_probability",
        "observed_probability",
        "observed_probability_ci_lower",
        "observed_probability_ci_upper",
        "expected_within_observed_ci",
        "absolute_difference_observed_vs_expected",
        "review_flag",
        "review_priority",
        "review_label",
    ]

    return {
        "high_confidence_mismatch_candidates": high_conf[cols].to_dict(orient="records"),
        "low_confidence_mismatch_candidates": low_conf[cols].to_dict(orient="records"),
        "likely_noise_only_categories": likely_noise[cols].to_dict(orient="records"),
        "categories_needing_more_data": needs_data[cols].to_dict(orient="records"),
    }


def analyze_state_residuals(
    state_comparison_rows: Sequence[Mapping[str, Any]],
    *,
    top_n: int = 8,
) -> Dict[str, Any]:
    df = pd.DataFrame(list(state_comparison_rows))
    if df.empty:
        return {
            "top_over_predicted": [],
            "top_under_predicted": [],
            "observed_only_states": [],
            "model_only_states": [],
        }

    df["expected_probability"] = pd.to_numeric(df["expected_probability"], errors="coerce").fillna(0.0)
    df["observed_probability"] = pd.to_numeric(df["observed_probability"], errors="coerce").fillna(0.0)
    df["model_minus_observed"] = df["expected_probability"] - df["observed_probability"]
    df["observed_minus_model"] = df["observed_probability"] - df["expected_probability"]

    over_predicted = df.sort_values("model_minus_observed", ascending=False).head(int(top_n))
    under_predicted = df.sort_values("observed_minus_model", ascending=False).head(int(top_n))

    observed_only = df[(df["observed_probability"] > 0) & (df["expected_probability"] <= 0)]["category"].tolist()
    model_only = df[(df["expected_probability"] > 0) & (df["observed_probability"] <= 0)]["category"].tolist()

    return {
        "top_over_predicted": over_predicted[
            ["category", "expected_probability", "observed_probability", "model_minus_observed"]
        ].to_dict(orient="records"),
        "top_under_predicted": under_predicted[
            ["category", "expected_probability", "observed_probability", "observed_minus_model"]
        ].to_dict(orient="records"),
        "observed_only_states": sorted(set(str(x) for x in observed_only)),
        "model_only_states": sorted(set(str(x) for x in model_only)),
    }


def _select_dimensions_for_mode(mode: str) -> Tuple[str, ...]:
    if mode == MODE_STATE:
        return (DIMENSION_STATE,)
    if mode == MODE_RARITY:
        return (
            DIMENSION_RARE_SLOT,
            DIMENSION_REVERSE_1,
            DIMENSION_REVERSE_2,
            DIMENSION_REVERSE_SLOT,
            DIMENSION_AGGREGATE_HITS,
        )
    if mode == MODE_CONSISTENCY:
        return (DIMENSION_STATE, DIMENSION_RARE_SLOT, DIMENSION_REVERSE_SLOT, DIMENSION_AGGREGATE_HITS)
    raise ValueError(f"Unsupported mode: {mode}")


def compare_model_to_observed(
    *,
    config: Any,
    observed_data: Any,
    state_alias_map: Optional[Mapping[str, str]] = None,
    modes: Sequence[str] = (MODE_STATE, MODE_RARITY),
    include_simulation: bool = True,
    simulation_packs: int = 250000,
    random_seed: Optional[int] = 7,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    residual_threshold: float = DEFAULT_RESIDUAL_THRESHOLD,
    minimum_confidence_sample_size: int = DEFAULT_MIN_CONFIDENCE_SAMPLE_SIZE,
) -> Dict[str, Any]:
    normalized_modes = tuple(_normalize_dimension_name(mode) for mode in modes)
    for mode in normalized_modes:
        if mode not in VALIDATION_MODES:
            raise ValueError(f"Unsupported validation mode: {mode}")

    observed = load_observed_pull_data(observed_data, state_alias_map=state_alias_map)
    expected = _build_expected_distributions(config)
    simulated = (
        _simulate_distributions_v2(config, n_packs=simulation_packs, random_seed=random_seed)
        if include_simulation
        else {}
    )

    comparisons_by_dimension: Dict[str, Dict[str, Any]] = {}
    notes: list[str] = []

    for mode in normalized_modes:
        for dimension in _select_dimensions_for_mode(mode):
            if dimension in comparisons_by_dimension:
                continue

            observed_counts = observed["counts_by_dimension"].get(dimension)
            observed_n = observed["dimension_sample_sizes"].get(dimension)

            if observed_counts is None:
                notes.append(
                    f"Observed data missing dimension '{dimension}'. Comparison limited to expected vs simulated."
                )

            comparison = compare_distribution_dimension(
                dimension=dimension,
                expected_probabilities=expected.get(dimension, {}),
                simulated_probabilities=simulated.get(dimension) if include_simulation else None,
                observed_counts=observed_counts,
                observed_sample_size=observed_n,
                confidence_level=confidence_level,
                residual_threshold=residual_threshold,
                minimum_confidence_sample_size=minimum_confidence_sample_size,
            )
            comparisons_by_dimension[dimension] = comparison

    state_residuals = analyze_state_residuals(
        comparisons_by_dimension.get(DIMENSION_STATE, {}).get("comparison_rows", []),
        top_n=10,
    )

    confidence_aware_residuals_by_dimension = {
        dim: analyze_confidence_aware_residuals(section.get("comparison_rows", []), top_n=10)
        for dim, section in comparisons_by_dimension.items()
    }

    sample_size_warnings = []
    for dim, size in observed["dimension_sample_sizes"].items():
        if size < 100:
            sample_size_warnings.append(
                f"Observed sample size for '{dim}' is {size}; inference is noisy at this size."
            )

    return {
        "report_type": "pack_state_validation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "modes": normalized_modes,
        "set_id": observed.get("set_id"),
        "set_name": observed.get("set_name"),
        "observed": observed,
        "expected_distributions": expected,
        "simulated_distributions": simulated if include_simulation else None,
        "comparisons_by_dimension": comparisons_by_dimension,
        "state_residuals": state_residuals,
        "confidence_aware_residuals_by_dimension": confidence_aware_residuals_by_dimension,
        "notes": notes,
        "sample_size_warnings": sample_size_warnings,
    }


def run_pack_state_validation(
    *,
    config: Any,
    observed_data: Optional[Any] = None,
    state_alias_map: Optional[Mapping[str, str]] = None,
    modes: Sequence[str] = (MODE_STATE, MODE_RARITY, MODE_CONSISTENCY),
    simulation_packs: int = 250000,
    random_seed: Optional[int] = 7,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    residual_threshold: float = DEFAULT_RESIDUAL_THRESHOLD,
    minimum_confidence_sample_size: int = DEFAULT_MIN_CONFIDENCE_SAMPLE_SIZE,
) -> Dict[str, Any]:
    normalized_modes = tuple(_normalize_dimension_name(mode) for mode in modes)

    expected = _build_expected_distributions(config)
    simulated = _simulate_distributions_v2(config, n_packs=simulation_packs, random_seed=random_seed)

    if observed_data is None:
        observed_payload = {
            "set_id": None,
            "set_name": None,
            "sample_size": None,
            "source_metadata": {},
            "notes": "No observed payload provided.",
            "counts_by_dimension": {},
            "dimension_sample_sizes": {},
        }
    else:
        observed_payload = load_observed_pull_data(observed_data, state_alias_map=state_alias_map)

    comparisons: Dict[str, Dict[str, Any]] = {}
    notes: list[str] = []

    for mode in normalized_modes:
        if mode not in VALIDATION_MODES:
            raise ValueError(f"Unsupported validation mode: {mode}")
        for dimension in _select_dimensions_for_mode(mode):
            if dimension in comparisons:
                continue
            observed_counts = observed_payload["counts_by_dimension"].get(dimension)
            observed_n = observed_payload["dimension_sample_sizes"].get(dimension)
            if observed_counts is None:
                notes.append(
                    f"Observed data missing dimension '{dimension}'. Comparison limited to expected vs simulated."
                )
            comparisons[dimension] = compare_distribution_dimension(
                dimension=dimension,
                expected_probabilities=expected.get(dimension, {}),
                simulated_probabilities=simulated.get(dimension),
                observed_counts=observed_counts,
                observed_sample_size=observed_n,
                confidence_level=confidence_level,
                residual_threshold=residual_threshold,
                minimum_confidence_sample_size=minimum_confidence_sample_size,
            )

    state_residuals = analyze_state_residuals(
        comparisons.get(DIMENSION_STATE, {}).get("comparison_rows", []),
        top_n=10,
    )

    confidence_aware_residuals_by_dimension = {
        dim: analyze_confidence_aware_residuals(section.get("comparison_rows", []), top_n=10)
        for dim, section in comparisons.items()
    }

    return {
        "report_type": "pack_state_validation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "modes": normalized_modes,
        "observed": observed_payload,
        "expected_distributions": expected,
        "simulated_distributions": simulated,
        "comparisons_by_dimension": comparisons,
        "state_residuals": state_residuals,
        "confidence_aware_residuals_by_dimension": confidence_aware_residuals_by_dimension,
        "notes": notes,
    }


def _deepcopy_expected_distributions(expected_distributions: Mapping[str, Mapping[str, float]]) -> Dict[str, Dict[str, float]]:
    return {
        str(dimension): {str(category): float(value) for category, value in probs.items()}
        for dimension, probs in expected_distributions.items()
    }


def build_artifact_adjusted_expected_distributions(
    *,
    base_expected_distributions: Mapping[str, Mapping[str, float]],
    calibration_artifact: Mapping[str, Any],
    dimension: str = DIMENSION_STATE,
) -> Dict[str, Dict[str, float]]:
    adjusted = _deepcopy_expected_distributions(base_expected_distributions)
    normalized_dimension = _normalize_dimension_name(dimension)
    artifact_dimension = _normalize_dimension_name(str(calibration_artifact.get("dimension", normalized_dimension)))
    if artifact_dimension != normalized_dimension:
        raise ValueError(
            f"Calibration artifact dimension '{artifact_dimension}' does not match requested dimension '{normalized_dimension}'."
        )

    fitted = calibration_artifact.get("fitted_probabilities", {})
    adjusted[normalized_dimension] = _normalize_probabilities({str(k): float(v) for k, v in fitted.items()})
    return adjusted


def _compute_candidate_expected_distributions(candidate: Any) -> Dict[str, Dict[str, float]]:
    if isinstance(candidate, Mapping):
        if "expected_distributions" in candidate:
            expected = candidate.get("expected_distributions", {})
            return _deepcopy_expected_distributions(expected)
        if "config" in candidate:
            return _build_expected_distributions(candidate["config"])
    return _build_expected_distributions(candidate)


def compare_candidate_models(
    *,
    observed_data: Any,
    candidate_models: Mapping[str, Any],
    modes: Sequence[str] = (MODE_STATE, MODE_RARITY),
    ranking_dimension: str = DIMENSION_STATE,
    ranking_metric: str = "total_variation_distance",
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    residual_threshold: float = DEFAULT_RESIDUAL_THRESHOLD,
    minimum_confidence_sample_size: int = DEFAULT_MIN_CONFIDENCE_SAMPLE_SIZE,
) -> Dict[str, Any]:
    if not candidate_models:
        raise ValueError("candidate_models must contain at least one candidate.")

    observed_payload = load_observed_pull_data(observed_data)
    normalized_modes = tuple(_normalize_dimension_name(mode) for mode in modes)
    ranking_dimension = _normalize_dimension_name(ranking_dimension)

    candidate_reports: Dict[str, Dict[str, Any]] = {}
    ranking_rows = []

    for candidate_name, candidate in candidate_models.items():
        expected = _compute_candidate_expected_distributions(candidate)
        comparisons: Dict[str, Dict[str, Any]] = {}

        for mode in normalized_modes:
            if mode not in VALIDATION_MODES:
                raise ValueError(f"Unsupported validation mode: {mode}")
            for dimension in _select_dimensions_for_mode(mode):
                if dimension in comparisons:
                    continue
                observed_counts = observed_payload["counts_by_dimension"].get(dimension)
                observed_n = observed_payload["dimension_sample_sizes"].get(dimension)
                comparisons[dimension] = compare_distribution_dimension(
                    dimension=dimension,
                    expected_probabilities=expected.get(dimension, {}),
                    simulated_probabilities=None,
                    observed_counts=observed_counts,
                    observed_sample_size=observed_n,
                    confidence_level=confidence_level,
                    residual_threshold=residual_threshold,
                    minimum_confidence_sample_size=minimum_confidence_sample_size,
                )

        confidence_aware_residuals_by_dimension = {
            dim: analyze_confidence_aware_residuals(section.get("comparison_rows", []), top_n=10)
            for dim, section in comparisons.items()
        }

        ranking_section = comparisons.get(ranking_dimension, {})
        ranking_metrics = ranking_section.get("metrics") or {}
        primary_metric_value = ranking_metrics.get(ranking_metric)
        if primary_metric_value is None:
            primary_metric_value = float("inf")

        ci_outside_count = 0
        row_count_with_ci = 0
        for row in ranking_section.get("comparison_rows", []):
            outside = row.get("expected_outside_observed_ci")
            if outside is not None:
                row_count_with_ci += 1
                if bool(outside):
                    ci_outside_count += 1

        major_residual_contributors = sorted(
            ranking_section.get("comparison_rows", []),
            key=lambda r: abs(float(r.get("absolute_difference_observed_vs_expected") or 0.0)),
            reverse=True,
        )[:5]

        candidate_reports[str(candidate_name)] = {
            "candidate_name": str(candidate_name),
            "expected_distributions": expected,
            "comparisons_by_dimension": comparisons,
            "confidence_aware_residuals_by_dimension": confidence_aware_residuals_by_dimension,
        }

        ranking_rows.append(
            {
                "candidate_name": str(candidate_name),
                "ranking_dimension": ranking_dimension,
                "ranking_metric": ranking_metric,
                "ranking_metric_value": float(primary_metric_value),
                "mean_absolute_error": ranking_metrics.get("mean_absolute_error"),
                "total_variation_distance": ranking_metrics.get("total_variation_distance"),
                "chi_square": ranking_metrics.get("chi_square"),
                "jensen_shannon_divergence": ranking_metrics.get("jensen_shannon_divergence"),
                "ci_outside_count": int(ci_outside_count),
                "ci_evaluable_categories": int(row_count_with_ci),
                "major_residual_contributors": [
                    {
                        "category": row.get("category"),
                        "absolute_difference_observed_vs_expected": row.get("absolute_difference_observed_vs_expected"),
                        "expected_probability": row.get("expected_probability"),
                        "observed_probability": row.get("observed_probability"),
                        "expected_outside_observed_ci": row.get("expected_outside_observed_ci"),
                        "review_flag": row.get("review_flag"),
                    }
                    for row in major_residual_contributors
                ],
            }
        )

    ranking = sorted(ranking_rows, key=lambda row: float(row["ranking_metric_value"]))
    for idx, row in enumerate(ranking, start=1):
        row["rank"] = idx

    return {
        "report_type": "candidate_model_comparison",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ranking_dimension": ranking_dimension,
        "ranking_metric": ranking_metric,
        "ranking": ranking,
        "candidate_reports": candidate_reports,
        "notes": [
            "Candidate ranking is a research aid and not automatic truth promotion.",
            "No candidate is auto-promoted into sourced configuration truth.",
        ],
    }


def build_model_assumption_inventory(
    *,
    config: Any,
    resolved_model: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    model = dict(resolved_model) if resolved_model is not None else resolve_pack_state_model(config)

    era_name = str(getattr(config, "ERA", "") or "")
    era_key = normalize_era_key(era_name)
    era_builder = resolve_era_builder(era_key)

    has_explicit_pack_state_model = bool(getattr(config, "PACK_STATE_MODEL", None))
    has_custom_getter = callable(getattr(config, "get_pack_state_model", None))
    has_overrides_getter = callable(getattr(config, "get_pack_state_overrides", None))

    constraints = model.get("constraints", {}) or {}
    known_sourced_assumptions = []
    inferred_assumptions = []
    unresolved_assumptions = []
    review_required_assumptions = []

    if has_explicit_pack_state_model or has_custom_getter:
        known_sourced_assumptions.append("pack_state_model is provided explicitly by set config")
    else:
        inferred_assumptions.append("pack_state_model resolved from era/base builder")

    if has_overrides_getter:
        inferred_assumptions.append("set-level pack_state overrides may adjust era/base model")

    if getattr(config, "RARE_SLOT_PROBABILITY", None):
        known_sourced_assumptions.append("rare_slot_probability table present")
    else:
        unresolved_assumptions.append("rare_slot_probability table missing")

    if getattr(config, "REVERSE_SLOT_PROBABILITIES", None):
        known_sourced_assumptions.append("reverse_slot_probabilities table present")
    else:
        unresolved_assumptions.append("reverse_slot_probabilities table missing")

    if not constraints:
        unresolved_assumptions.append("constraints missing in resolved pack-state model")
    else:
        inferred_assumptions.append("constraints active in resolved pack-state model")

    if not has_explicit_pack_state_model:
        review_required_assumptions.append("resolved probabilities should be reviewed against observed pull data")

    god_enabled = bool((getattr(config, "GOD_PACK_CONFIG", {}) or {}).get("enabled"))
    demi_enabled = bool((getattr(config, "DEMI_GOD_PACK_CONFIG", {}) or {}).get("enabled"))

    return {
        "report_type": "model_assumption_inventory",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sourced_truth_boundary": {
            "source_config_mutation_allowed": False,
            "automatic_truth_promotion_allowed": False,
            "policy": "research outputs are inferred/provisional/review-only",
        },
        "model_resolution": {
            "era_name": era_name,
            "normalized_era_key": era_key,
            "era_builder_used": era_builder.__name__ if callable(era_builder) else None,
            "has_explicit_pack_state_model": has_explicit_pack_state_model,
            "has_custom_pack_state_getter": has_custom_getter,
            "has_set_overrides_getter": has_overrides_getter,
            "resolved_state_count": len(model.get("state_probabilities", {}) or {}),
        },
        "constraints_active": {
            "primary_hits": sorted(str(x) for x in constraints.get("primary_hits", [])),
            "exclusive_hits": sorted(str(x) for x in constraints.get("exclusive_hits", [])),
            "bonus_hits": sorted(str(x) for x in constraints.get("bonus_hits", [])),
            "max_major_hits": constraints.get("max_major_hits"),
            "max_non_regular_hits": constraints.get("max_non_regular_hits"),
            "max_exclusive_hits": constraints.get("max_exclusive_hits"),
        },
        "special_pack_behavior": {
            "god_pack_enabled": god_enabled,
            "demi_god_pack_enabled": demi_enabled,
        },
        "assumption_status": {
            "known_sourced_assumptions": known_sourced_assumptions,
            "inferred_assumptions": inferred_assumptions,
            "unresolved_assumptions": unresolved_assumptions,
            "review_required_assumptions": review_required_assumptions,
        },
    }


def generate_research_bundle(
    *,
    validation_report: Mapping[str, Any],
    output_dir: str | Path,
    file_prefix: str = "pack_state_research",
    model_assumption_inventory: Optional[Mapping[str, Any]] = None,
    candidate_model_comparison: Optional[Mapping[str, Any]] = None,
    calibration_artifact_comparison_summary: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    exported: Dict[str, str] = {}

    summary_json_path = output_path / f"{file_prefix}_summary.json"
    summary_json_path.write_text(
        json.dumps(_json_safe_report(validation_report), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    exported["summary_json"] = str(summary_json_path)

    comparisons = validation_report.get("comparisons_by_dimension", {})
    for dimension, comparison in comparisons.items():
        frame = comparison.get("comparison_df")
        if not isinstance(frame, pd.DataFrame):
            frame = pd.DataFrame(comparison.get("comparison_rows", []))

        comparison_csv_path = output_path / f"{file_prefix}_{dimension}_comparison.csv"
        frame.to_csv(comparison_csv_path, index=False)
        exported[f"comparison_csv_{dimension}"] = str(comparison_csv_path)

        ci_columns = [
            "dimension",
            "category",
            "observed_count",
            "observed_probability",
            "observed_probability_ci_lower",
            "observed_probability_ci_upper",
            "observed_probability_ci_confidence_level",
            "observed_probability_ci_method",
            "expected_probability",
            "expected_within_observed_ci",
            "expected_outside_observed_ci",
            "review_flag",
            "review_priority",
        ]
        ci_frame = frame[[col for col in ci_columns if col in frame.columns]]
        ci_csv_path = output_path / f"{file_prefix}_{dimension}_confidence_intervals.csv"
        ci_frame.to_csv(ci_csv_path, index=False)
        exported[f"confidence_interval_csv_{dimension}"] = str(ci_csv_path)

    confidence_residuals = validation_report.get("confidence_aware_residuals_by_dimension") or {}
    confidence_residuals_path = output_path / f"{file_prefix}_confidence_aware_residuals.json"
    confidence_residuals_path.write_text(
        json.dumps(confidence_residuals, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    exported["confidence_aware_residuals_json"] = str(confidence_residuals_path)

    if model_assumption_inventory is not None:
        assumption_path = output_path / f"{file_prefix}_assumption_inventory.json"
        assumption_path.write_text(
            json.dumps(dict(model_assumption_inventory), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        exported["assumption_inventory_json"] = str(assumption_path)

    if candidate_model_comparison is not None:
        candidate_summary_path = output_path / f"{file_prefix}_candidate_model_comparison.json"
        candidate_summary_path.write_text(
            json.dumps(_json_safe_report(candidate_model_comparison), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        exported["candidate_model_comparison_json"] = str(candidate_summary_path)

    if calibration_artifact_comparison_summary is not None:
        artifact_compare_path = output_path / f"{file_prefix}_artifact_comparison_summary.json"
        artifact_compare_path.write_text(
            json.dumps(_json_safe_report(calibration_artifact_comparison_summary), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        exported["calibration_artifact_comparison_json"] = str(artifact_compare_path)

    manifest = {
        "report_type": "phase6_research_bundle_manifest",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "notes": [
            "Bundle supports research triage and does not mutate sourced config truth.",
            "Inferred/provisional outputs must not be promoted automatically.",
        ],
        "exports": exported,
    }
    manifest_path = output_path / f"{file_prefix}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    exported["manifest_json"] = str(manifest_path)

    return exported


def run_confidence_aware_validation(
    *,
    config: Any,
    observed_data: Any,
    state_alias_map: Optional[Mapping[str, str]] = None,
    modes: Sequence[str] = (MODE_STATE, MODE_RARITY),
    simulation_packs: int = 250000,
    random_seed: Optional[int] = 7,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    residual_threshold: float = DEFAULT_RESIDUAL_THRESHOLD,
    minimum_confidence_sample_size: int = DEFAULT_MIN_CONFIDENCE_SAMPLE_SIZE,
    candidate_models: Optional[Mapping[str, Any]] = None,
    calibration_artifact: Optional[Mapping[str, Any]] = None,
    ranking_dimension: str = DIMENSION_STATE,
    ranking_metric: str = "total_variation_distance",
) -> Dict[str, Any]:
    validation_report = run_pack_state_validation(
        config=config,
        observed_data=observed_data,
        state_alias_map=state_alias_map,
        modes=modes,
        simulation_packs=simulation_packs,
        random_seed=random_seed,
        confidence_level=confidence_level,
        residual_threshold=residual_threshold,
        minimum_confidence_sample_size=minimum_confidence_sample_size,
    )

    resolved_model = resolve_pack_state_model(config)
    assumption_inventory = build_model_assumption_inventory(config=config, resolved_model=resolved_model)

    candidate_payload: Dict[str, Any] = {
        "current_derived_model": {
            "expected_distributions": validation_report.get("expected_distributions", {}),
            "candidate_metadata": {
                "candidate_type": "derived_model",
                "provisional": False,
                "review_only": True,
            },
        }
    }
    if candidate_models:
        candidate_payload.update(candidate_models)

    artifact_comparison_summary = None
    if calibration_artifact is not None:
        artifact_adjusted_expected = build_artifact_adjusted_expected_distributions(
            base_expected_distributions=validation_report.get("expected_distributions", {}),
            calibration_artifact=calibration_artifact,
            dimension=DIMENSION_STATE,
        )
        candidate_payload["artifact_adjusted_model"] = {
            "expected_distributions": artifact_adjusted_expected,
            "candidate_metadata": {
                "candidate_type": "artifact_adjusted",
                "provisional": True,
                "review_only": True,
                "not_for_automatic_config_promotion": True,
            },
        }

    candidate_model_comparison = compare_candidate_models(
        observed_data=validation_report.get("observed", {}),
        candidate_models=candidate_payload,
        modes=modes,
        ranking_dimension=ranking_dimension,
        ranking_metric=ranking_metric,
        confidence_level=confidence_level,
        residual_threshold=residual_threshold,
        minimum_confidence_sample_size=minimum_confidence_sample_size,
    )

    if "artifact_adjusted_model" in candidate_payload:
        artifact_rows = [
            row for row in candidate_model_comparison.get("ranking", [])
            if row.get("candidate_name") in {"current_derived_model", "artifact_adjusted_model"}
        ]
        artifact_comparison_summary = {
            "report_type": "calibration_artifact_candidate_comparison",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "ranking_dimension": ranking_dimension,
            "ranking_metric": ranking_metric,
            "rows": artifact_rows,
            "notes": [
                "Artifact comparison is allowed for research triage.",
                "Artifact output must not be auto-promoted into sourced config truth.",
            ],
        }

    return {
        "report_type": "phase6_confidence_aware_validation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "validation_report": validation_report,
        "model_assumption_inventory": assumption_inventory,
        "candidate_model_comparison": candidate_model_comparison,
        "calibration_artifact_comparison_summary": artifact_comparison_summary,
    }


def generate_calibration_artifact(
    validation_report: Mapping[str, Any],
    *,
    dimension: str = DIMENSION_STATE,
    minimum_observed_count: int = 10,
    blend_weight: Optional[float] = None,
) -> Dict[str, Any]:
    """Build a non-destructive calibration artifact for manual review.

    Calibration artifacts are heuristic empirical suggestions, not statistically
    fitted truth. The blend-weight logic is a practical review aid and is not a
    formal inference procedure. Artifact output is exploratory/provisional and
    must not be auto-promoted into sourced configuration truth.
    """
    dimension = _normalize_dimension_name(dimension)

    comparison = validation_report.get("comparisons_by_dimension", {}).get(dimension, {})
    rows = comparison.get("comparison_rows", [])
    observed_sample_size = comparison.get("observed_sample_size")

    blend_weight_rationale = "manual_override" if blend_weight is not None else "sample_size_heuristic"
    if blend_weight is None:
        if observed_sample_size is None or observed_sample_size <= 0:
            blend_weight = 0.0
        else:
            # Heuristic blend: this is a practical review weighting, not a statistical fitter.
            blend_weight = min(1.0, float(observed_sample_size) / 5000.0)

    expected_probs: Dict[str, float] = {}
    observed_probs: Dict[str, float] = {}
    observed_counts: Dict[str, int] = {}

    for row in rows:
        category = str(row["category"])
        expected_probs[category] = float(row.get("expected_probability", 0.0) or 0.0)
        if row.get("observed_probability") is not None:
            observed_probs[category] = float(row.get("observed_probability") or 0.0)
        if row.get("observed_count") is not None:
            observed_counts[category] = int(row.get("observed_count") or 0)

    fitted: Dict[str, float] = {}
    for category, expected in expected_probs.items():
        obs_count = observed_counts.get(category, 0)
        if category in observed_probs and obs_count >= int(minimum_observed_count):
            observed = observed_probs[category]
            fitted[category] = (1.0 - blend_weight) * expected + blend_weight * observed
        else:
            fitted[category] = expected

    fitted = _normalize_probabilities(fitted)

    deltas = {
        category: fitted.get(category, 0.0) - expected_probs.get(category, 0.0)
        for category in sorted(expected_probs.keys())
    }

    ranked = sorted(deltas.items(), key=lambda kv: abs(kv[1]), reverse=True)

    return {
        "artifact_type": "empirical_calibration",
        "label": (
            "fitted empirical provisional artifact; heuristic review aid only; "
            "not statistically fitted truth; does not overwrite sourced config truth"
        ),
        "artifact_status": "provisional",
        "artifact_intent": "heuristic_empirical_suggestion_layer",
        "artifact_method": "heuristic_blend",
        "fit_status": "exploratory",
        "not_for_automatic_config_promotion": True,
        "non_destructive": True,
        "writes_to_source_config": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dimension": dimension,
        "minimum_observed_count": int(minimum_observed_count),
        "blend_weight": float(blend_weight),
        "blend_weight_rationale": blend_weight_rationale,
        "expected_probabilities": expected_probs,
        "fitted_probabilities": fitted,
        "probability_deltas": deltas,
        "ranked_categories_for_review": [
            {"category": category, "delta": delta, "absolute_delta": abs(delta)}
            for category, delta in ranked
        ],
    }


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="records")
    if isinstance(value, Mapping):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _json_safe_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    serializable = deepcopy(dict(report))
    return _to_json_safe(serializable)


def export_calibration_results(
    *,
    validation_report: Mapping[str, Any],
    output_dir: str | Path,
    file_prefix: str = "pack_state_calibration",
    include_simulated_raw: bool = True,
) -> Dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    exported: Dict[str, str] = {}

    summary_json_path = output_path / f"{file_prefix}_summary.json"
    summary_json_path.write_text(
        json.dumps(_json_safe_report(validation_report), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    exported["summary_json"] = str(summary_json_path)

    comparisons = validation_report.get("comparisons_by_dimension", {})
    for dimension, comparison in comparisons.items():
        frame = comparison.get("comparison_df")
        if not isinstance(frame, pd.DataFrame):
            frame = pd.DataFrame(comparison.get("comparison_rows", []))
        csv_path = output_path / f"{file_prefix}_{dimension}_comparison.csv"
        frame.to_csv(csv_path, index=False)
        exported[f"comparison_csv_{dimension}"] = str(csv_path)

    residuals = validation_report.get("state_residuals")
    if residuals:
        residuals_json_path = output_path / f"{file_prefix}_state_residuals.json"
        residuals_json_path.write_text(json.dumps(residuals, indent=2, sort_keys=True), encoding="utf-8")
        exported["state_residuals_json"] = str(residuals_json_path)

    if include_simulated_raw:
        simulated = validation_report.get("simulated_distributions")
        if simulated is not None:
            sim_json_path = output_path / f"{file_prefix}_simulated_distributions.json"
            sim_json_path.write_text(json.dumps(simulated, indent=2, sort_keys=True), encoding="utf-8")
            exported["simulated_json"] = str(sim_json_path)

    return exported


def generate_calibration_report(
    *,
    config: Any,
    observed_data: Optional[Any] = None,
    output_dir: Optional[str | Path] = None,
    state_alias_map: Optional[Mapping[str, str]] = None,
    modes: Sequence[str] = (MODE_STATE, MODE_RARITY, MODE_CONSISTENCY),
    simulation_packs: int = 250000,
    random_seed: Optional[int] = 7,
    file_prefix: str = "pack_state_calibration",
) -> Dict[str, Any]:
    report = run_pack_state_validation(
        config=config,
        observed_data=observed_data,
        state_alias_map=state_alias_map,
        modes=modes,
        simulation_packs=simulation_packs,
        random_seed=random_seed,
    )

    report["calibration_artifact"] = generate_calibration_artifact(report, dimension=DIMENSION_STATE)

    if output_dir is not None:
        report["export_paths"] = export_calibration_results(
            validation_report=report,
            output_dir=output_dir,
            file_prefix=file_prefix,
        )

    return report
