"""Cost-relative opening outcome profiles derived from exact pack artifacts."""

from __future__ import annotations

import math
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from backend.research.ev_representativeness.distribution import compute_return_ratio_buckets

CONTRACT_VERSION = "opening_outcome_profile_v1"
RESEARCH_METHOD_VERSION = "opening_outcome_profile_research_v1"

PUBLIC_BUCKETS: tuple[tuple[str, float, Optional[float], str, str], ...] = (
    ("under_25", 0.00, 0.25, "Under 25%", "Less than 25% of opening cost returned in modeled card value."),
    ("recover_25_50", 0.25, 0.50, "25–50%", "Between 25% and 50% of opening cost returned."),
    ("recover_50_75", 0.50, 0.75, "50–75%", "Between 50% and 75% of opening cost returned."),
    ("recover_75_100", 0.75, 1.00, "75–100%", "Between 75% and 100% of opening cost returned."),
    ("recover_100_150", 1.00, 1.50, "1–1.5×", "Between 1 and 1.5 times opening cost returned."),
    ("recover_150_200", 1.50, 2.00, "1.5–2×", "Between 1.5 and 2 times opening cost returned."),
    ("recover_200_500", 2.00, 5.00, "2–5×", "Between 2 and 5 times opening cost returned."),
    ("recover_500_plus", 5.00, None, "5×+", "At least 5 times opening cost returned."),
)

CUMULATIVE_THRESHOLDS: tuple[tuple[str, str, str, float], ...] = (
    ("below_50", "below", "Under 50%", 0.50),
    ("at_least_cost", "at_least", "At least cost", 1.00),
    ("at_least_2x", "at_least", "At least 2×", 2.00),
    ("at_least_5x", "at_least", "At least 5×", 5.00),
)


def compute_profile(values: Sequence[float], opening_cost: float) -> dict[str, Any]:
    """Compute V1 from an exact outcome vector; every boundary is [floor, ceiling)."""
    raw = compute_return_ratio_buckets(np.asarray(values, dtype=np.float64), opening_cost,
                                       buckets=tuple((row[1], row[2]) for row in PUBLIC_BUCKETS))
    return profile_from_persisted(raw)


def profile_from_persisted(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and label the already-persisted exact V1 bucket calculation."""
    cost = _positive(raw.get("cost"))
    sample_size = int(raw.get("sampleSize") or 0)
    rows = raw.get("buckets")
    if cost is None or sample_size <= 0 or not isinstance(rows, list) or len(rows) != len(PUBLIC_BUCKETS):
        raise ValueError("opening outcome profile source is incomplete")
    buckets = []
    total_count = 0
    for source, definition in zip(rows, PUBLIC_BUCKETS):
        key, floor, ceiling, label, interpretation = definition
        if not isinstance(source, Mapping):
            raise ValueError("opening outcome profile bucket is invalid")
        source_floor = float(source.get("ratioFloor"))
        source_ceiling = source.get("ratioCeiling")
        source_ceiling = None if source_ceiling is None else float(source_ceiling)
        if source_floor != floor or source_ceiling != ceiling:
            raise ValueError("opening outcome profile bucket contract mismatch")
        count = int(source.get("occurrenceCount") or 0)
        probability = float(source.get("probability"))
        if count < 0 or not math.isfinite(probability) or probability < 0 or probability > 1:
            raise ValueError("opening outcome profile bucket value is invalid")
        total_count += count
        buckets.append({"key": key, "floorRatio": floor, "ceilingRatio": ceiling,
                        "probability": probability, "occurrenceCount": count,
                        "label": label, "interpretation": interpretation})
    if total_count != sample_size or not math.isclose(sum(row["probability"] for row in buckets), 1.0,
                                                        rel_tol=0, abs_tol=1e-9):
        raise ValueError("opening outcome profile does not partition the exact sample")
    cumulative = []
    for key, direction, label, threshold in CUMULATIVE_THRESHOLDS:
        if direction == "below":
            probability = sum(row["probability"] for row in buckets
                              if row["ceilingRatio"] is not None and row["ceilingRatio"] <= threshold)
        else:
            probability = sum(row["probability"] for row in buckets if row["floorRatio"] >= threshold)
        cumulative.append({"key": key, "direction": direction, "thresholdRatio": threshold,
                           "probability": probability, "label": label})
    return {"openingCost": cost, "sampleSize": sample_size, "buckets": buckets,
            "cumulativeProbabilities": cumulative}


def _positive(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None
