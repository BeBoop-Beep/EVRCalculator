"""Helpers for fixed-threshold value bins from Monte Carlo simulation outcomes."""

from __future__ import annotations

from typing import Any, Sequence


DEFAULT_VALUE_THRESHOLD_BUCKETS: tuple[tuple[float, float | None], ...] = (
    (0.0, 0.5),
    (0.5, 1.0),
    (1.0, 1.5),
    (1.5, 2.0),
    (2.0, 3.0),
    (3.0, 5.0),
    (5.0, 7.5),
    (7.5, 12.5),
    (12.5, 17.5),
    (17.5, 37.5),
    (37.5, 75.0),
    (75.0, 175.0),
    (175.0, 375.0),
    (375.0, 750.0),
    (750.0, 1800.0),
    (1800.0, 3800.0),
    (3800.0, 5000.0),
    (5000.0, None),
)


def _format_bucket_label(floor: float, ceiling: float | None) -> str:
    if ceiling is None:
        return f">={int(floor) if float(floor).is_integer() else floor}"
    return (
        f"{int(floor) if float(floor).is_integer() else floor}-"
        f"{int(ceiling) if float(ceiling).is_integer() else ceiling}"
    )


def compute_simulation_value_threshold_bins(
    values: Sequence[float],
    thresholds: Sequence[tuple[float, float | None]] = DEFAULT_VALUE_THRESHOLD_BUCKETS,
) -> list[dict[str, Any]]:
    """Aggregate raw simulation values into fixed threshold buckets.

    Rules:
    - bucket membership is [floor, ceiling) except final open-ended bucket [floor, +inf)
    - no interpolation or approximation
    - sum(occurrence_count) must equal len(values)
    """
    n = len(values)
    if n == 0:
        raise ValueError("compute_simulation_value_threshold_bins: values must not be empty")
    if not thresholds:
        raise ValueError("compute_simulation_value_threshold_bins: thresholds must not be empty")

    rows: list[dict[str, Any]] = []
    running_cumulative = 0.0
    total_occurrence_count = 0

    for index, (floor, ceiling) in enumerate(thresholds, start=1):
        floor_f = float(floor)
        ceiling_f = float(ceiling) if ceiling is not None else None

        occurrence_count = 0
        for value in values:
            numeric_value = float(value)
            if numeric_value < floor_f:
                continue
            if ceiling_f is not None and numeric_value >= ceiling_f:
                continue
            occurrence_count += 1

        probability = occurrence_count / n
        running_cumulative += probability
        survival_probability = 1.0 - running_cumulative + probability
        total_occurrence_count += occurrence_count

        rows.append(
            {
                "threshold_floor": floor_f,
                "threshold_ceiling": ceiling_f,
                "occurrence_count": occurrence_count,
                "probability": probability,
                "cumulative_probability": running_cumulative,
                "survival_probability": survival_probability,
                "bucket_label": _format_bucket_label(floor_f, ceiling_f),
                "bucket_order": index,
            }
        )

    if total_occurrence_count != n:
        raise ValueError(
            "compute_simulation_value_threshold_bins: threshold coverage mismatch "
            f"(counted={total_occurrence_count}, total={n})"
        )

    return rows
