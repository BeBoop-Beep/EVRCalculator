"""Historical Trend interpretation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import EvidenceItem, SectionInterpretation
from ..thresholds import TREND_MEANINGFUL_DELTA_MIN, classify_directional_delta, format_ratio


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def interpret_historical_trend(data: Dict[str, Any]) -> SectionInterpretation:
    rows: List[Dict[str, Any]] = data.get("history_trend") or []

    if len(rows) < 2:
        return SectionInterpretation(
            summary="Historical trend is limited, so directionality is currently inconclusive.",
            label="Trend data limited",
            reason_code="insufficient_history",
            severity="data_limited",
            confidence="low",
        )

    first = rows[0]
    last = rows[-1]
    point_count = len(rows)

    first_mean = _to_float(first.get("simulated_mean_pack_value_vs_pack_cost"))
    last_mean = _to_float(last.get("simulated_mean_pack_value_vs_pack_cost"))
    first_median = _to_float(first.get("simulated_median_pack_value_vs_pack_cost"))
    last_median = _to_float(last.get("simulated_median_pack_value_vs_pack_cost"))

    if first_mean is None or last_mean is None:
        return SectionInterpretation(
            summary="Historical trend data is present but insufficient for a consistent directional read.",
            label="Trend data limited",
            reason_code="missing_mean_values",
            severity="data_limited",
            confidence="low",
        )

    mean_delta = last_mean - first_mean
    median_delta = (last_median - first_median) if (first_median is not None and last_median is not None) else None

    mean_direction = classify_directional_delta(mean_delta)
    median_direction = classify_directional_delta(median_delta, missing="flat")

    # Low confidence when fewer than 3 data points
    confidence = "high" if point_count >= 5 else ("medium" if point_count >= 3 else "low")

    if mean_direction == "up" and last_mean < 1.0:
        summary = "The set is improving, but the average pack is still below cost."
        label = "Improving, but still below cost"
        reason_code = "improving_below_cost"
        severity = "neutral"
    elif mean_direction == "up" and median_direction == "flat":
        summary = "The best hits are getting stronger, but normal packs have not improved much."
        label = "Top end improving, not typical packs"
        reason_code = "mean_up_median_flat"
        severity = "positive"
    elif mean_direction == "up" and last_mean >= 1.0 and (last_median is None or last_median >= 0.95):
        summary = "This set is holding steady above break-even \u2014 recent data shows consistent value support."
        label = "Stable above break-even"
        reason_code = "improving_above_cost"
        severity = "positive"
    elif mean_direction == "flat" and last_mean >= 1.0:
        summary = "This set has stayed above break-even across recent data \u2014 a sign of consistent value."
        label = "Stable above break-even"
        reason_code = "flat_above_cost"
        severity = "positive"
    elif mean_direction == "flat" and last_mean < 1.0:
        summary = "The set is not getting better or worse, but it is still below what packs cost \u2014 not improving."
        label = "Flat and still below break-even"
        reason_code = "flat_below_cost"
        severity = "caution"
    elif mean_direction == "down" and median_direction == "down":
        summary = "Both the average and typical pack returns are falling \u2014 the set is getting harder to justify."
        label = "Weakening"
        reason_code = "both_down"
        severity = "negative"
    elif abs(mean_delta) >= TREND_MEANINGFUL_DELTA_MIN:
        summary = "The overall trend is heading down, though not every metric is moving the same way."
        label = "Weakening"
        reason_code = "mean_down_median_mixed"
        severity = "negative"
    else:
        summary = "Recent data is hard to read \u2014 the average and typical returns are moving in different directions."
        label = "Mixed trend"
        reason_code = "mixed_trend"
        severity = "neutral"

    evidence: List[EvidenceItem] = [
        EvidenceItem("Data points", str(point_count)),
        EvidenceItem("First mean-to-cost", format_ratio(first_mean)),
        EvidenceItem("Latest mean-to-cost", format_ratio(last_mean)),
        EvidenceItem("Mean delta", format_ratio(mean_delta) if mean_delta is not None else "N/A"),
        EvidenceItem("First median-to-cost", format_ratio(first_median)),
        EvidenceItem("Latest median-to-cost", format_ratio(last_median)),
        EvidenceItem("Median delta", format_ratio(median_delta) if median_delta is not None else "N/A"),
    ]

    return SectionInterpretation(
        summary=summary,
        label=label,
        reason_code=reason_code,
        severity=severity,
        confidence=confidence,
        evidence=evidence,
        signals={
            "mean_direction": mean_direction,
            "median_direction": median_direction,
            "mean_delta": mean_delta,
            "median_delta": median_delta,
            "point_count": point_count,
        },
    )
