"""
Pure helper for computing value distribution bins from Monte Carlo V2 simulation outcomes.

This module is intentionally import-free (no DB, no simulation engine dependencies)
so the math is easy to unit-test in isolation.
"""
from __future__ import annotations

from typing import Any

_DEFAULT_NUM_BINS: int = 50


def compute_simulation_value_distribution_bins(
    values: list[float],
    num_bins: int = _DEFAULT_NUM_BINS,
) -> list[dict[str, Any]]:
    """Compute distribution bins from a list of simulated pack total values.

    Parameters
    ----------
    values:
        Raw simulated pack total values produced by the Monte Carlo engine.
        Must be non-empty.
    num_bins:
        Number of equal-width bins to produce.  Defaults to 50.

    Returns
    -------
    List of dicts, one per bin, with keys:
        bin_floor, bin_ceiling, occurrence_count, probability,
        cumulative_probability, survival_probability.

    The list is ordered from lowest bin to highest bin.

    Guarantees:
    - Every value in *values* lands in exactly one bin.
    - sum(occurrence_count) == len(values).
    - probability == occurrence_count / len(values).
    - cumulative_probability is monotonically non-decreasing; final value == 1.0.
    - survival_probability is monotonically non-increasing; first value == 1.0.
    - max(values) is included in the final bin.
    """
    n = len(values)
    if n == 0:
        raise ValueError(
            "compute_simulation_value_distribution_bins: values list must not be empty."
        )
    if num_bins < 1:
        raise ValueError(
            f"compute_simulation_value_distribution_bins: num_bins must be >= 1, got {num_bins}."
        )

    min_val = min(values)
    max_val = max(values)

    # ── Single-value edge case ────────────────────────────────────────────────
    if min_val == max_val:
        return [
            {
                "bin_floor": min_val,
                "bin_ceiling": min_val,
                "occurrence_count": n,
                "probability": 1.0,
                "cumulative_probability": 1.0,
                "survival_probability": 1.0,
            }
        ]

    # ── Normal case: build num_bins equal-width bins ──────────────────────────
    bin_width = (max_val - min_val) / num_bins

    occurrence_counts = [0] * num_bins
    for v in values:
        if v >= max_val:
            # Clamp max_val into the final bin (avoids float-division edge case).
            idx = num_bins - 1
        else:
            idx = int((v - min_val) / bin_width)
            # Guard against any floating-point overshoot.
            if idx < 0:
                idx = 0
            elif idx >= num_bins:
                idx = num_bins - 1
        occurrence_counts[idx] += 1

    # Build rows (without probabilities stats yet).
    rows: list[dict[str, Any]] = []
    for i in range(num_bins):
        rows.append(
            {
                "bin_floor": min_val + i * bin_width,
                "bin_ceiling": min_val + (i + 1) * bin_width,
                "occurrence_count": occurrence_counts[i],
                "probability": occurrence_counts[i] / n,
                # placeholders filled in below
                "cumulative_probability": None,
                "survival_probability": None,
            }
        )
    # The final bin ceiling must exactly equal max_val so that the DB stores the
    # true range and floating-point rounding doesn't create a gap.
    rows[-1]["bin_ceiling"] = max_val

    # ── Cumulative probability (ascending) ───────────────────────────────────
    cumulative = 0.0
    for row in rows:
        cumulative += row["probability"]
        row["cumulative_probability"] = cumulative

    # ── Survival probability (descending) ────────────────────────────────────
    # survival_probability[i] = P(pack value >= bin_floor[i])
    #                         = sum(probability[i..last])
    survival = 0.0
    for row in reversed(rows):
        survival += row["probability"]
        row["survival_probability"] = survival

    return rows
