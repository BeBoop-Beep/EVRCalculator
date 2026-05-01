"""Historical Trend interpretation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import EvidenceItem, SectionInterpretation
from ..thresholds import format_ratio


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _break_even_band(last_mean_ratio: Optional[float]) -> str:
    if last_mean_ratio is None:
        return "unknown"
    if last_mean_ratio >= 1.0:
        return "above_break_even"
    if last_mean_ratio >= 0.85:
        return "near_break_even"
    if last_mean_ratio >= 0.60:
        return "below_but_respectable"
    return "far_below_break_even"


def _p95_supplement(
    last_p95: Optional[float],
    first_p95: Optional[float],
    weakening: bool,
    improving: bool,
    flat: bool,
) -> Optional[str]:
    """Return one concise sentence adding P95 context, or None if P95 is absent."""
    if last_p95 is None:
        return None

    p95_delta = (last_p95 - first_p95) if first_p95 is not None else None
    p95_rising = p95_delta is not None and p95_delta >= 0.10
    p95_falling = p95_delta is not None and p95_delta <= -0.10

    if last_p95 < 1.0:
        return (
            "Even the high-end outcome is not clearing pack cost, "
            "which leaves little upside support at the current price."
        )
    if last_p95 >= 3.0:
        return (
            "The high-end tail is very strong relative to pack cost, "
            "so the set can still attract chase demand even if average returns are not favorable."
        )
    if weakening and last_p95 >= 1.0:
        if p95_falling:
            return (
                "Both average value and high-end upside are weakening, "
                "which makes the current pack price harder to justify."
            )
        return (
            "Average and typical outcomes are weak, but high-end upside still clears pack cost, "
            "so this is more of a chase-driven set than a steady-value pack."
        )
    if (flat or improving) and last_p95 >= 2.0:
        if p95_rising:
            return (
                "Upside is improving even though typical outcomes are not, "
                "suggesting the set is becoming more top-heavy."
            )
        return (
            "Typical outcomes remain low, but the high-end tail is still strong, "
            "meaning most of the appeal is concentrated in chase outcomes."
        )
    if p95_rising:
        return (
            "High-end upside is improving even while mean and median hold steady."
        )
    return None


def interpret_historical_trend(data: Dict[str, Any]) -> SectionInterpretation:
    rows: List[Dict[str, Any]] = data.get("history_trend") or []

    if len(rows) < 3:
        return SectionInterpretation(
            summary="There is not enough history yet to make a strong trend call.",
            label="Trend still forming",
            reason_code="trend_still_forming",
            severity="data_limited",
            confidence="low",
            signals={
                "trend_profile": "data_limited",
                "history_points_count": len(rows),
                "mean_delta": None,
                "median_delta": None,
                "p95_delta": None,
                "last_mean_ratio": None,
                "last_median_ratio": None,
                "last_p95_ratio": None,
                "break_even_band": "unknown",
            },
        )

    first = rows[0]
    last = rows[-1]
    point_count = len(rows)

    first_mean = _to_float(first.get("simulated_mean_pack_value_vs_pack_cost"))
    last_mean = _to_float(last.get("simulated_mean_pack_value_vs_pack_cost"))
    first_median = _to_float(first.get("simulated_median_pack_value_vs_pack_cost"))
    last_median = _to_float(last.get("simulated_median_pack_value_vs_pack_cost"))
    first_p95 = _to_float(first.get("p95_value_to_cost_ratio"))
    last_p95 = _to_float(last.get("p95_value_to_cost_ratio"))

    if first_mean is None or last_mean is None:
        return SectionInterpretation(
            summary="There is not enough history yet to make a strong trend call.",
            label="Trend still forming",
            reason_code="missing_mean_values",
            severity="data_limited",
            confidence="low",
            signals={
                "trend_profile": "data_limited",
                "history_points_count": point_count,
                "mean_delta": None,
                "median_delta": None,
                "p95_delta": None,
                "last_mean_ratio": last_mean,
                "last_median_ratio": last_median,
                "last_p95_ratio": last_p95,
                "break_even_band": _break_even_band(last_mean),
            },
        )

    mean_delta = last_mean - first_mean
    median_delta = (last_median - first_median) if (first_median is not None and last_median is not None) else None
    p95_delta = (last_p95 - first_p95) if (first_p95 is not None and last_p95 is not None) else None

    improving = mean_delta >= 0.03
    weakening = mean_delta <= -0.03
    flat = abs(mean_delta) < 0.03
    median_flat = median_delta is not None and abs(median_delta) < 0.02
    break_even_band = _break_even_band(last_mean)

    confidence = "high" if point_count >= 10 else ("medium" if point_count >= 5 else "low")

    if improving and median_flat:
        summary = "The bigger hits are helping the average, but normal packs have not improved much."
        label = "Hits improving, normal packs flat"
        reason_code = "mean_up_median_flat"
        severity = "neutral"
    elif improving and last_mean < 1.0:
        summary = "Average value is moving up, but it has not reached the pack price yet."
        label = "Improving, still below cost"
        reason_code = "improving_below_break_even"
        severity = "neutral"
    elif weakening:
        summary = "Average value has been slipping, which makes the set harder to justify at the current pack price."
        label = "Weakening trend"
        reason_code = "weakening_below_break_even"
        severity = "negative"
    elif flat and last_mean >= 0.85:
        summary = "The set is not moving much, but average value is staying close to pack cost."
        label = "Flat near break-even"
        reason_code = "flat_near_break_even"
        severity = "neutral"
    elif flat and last_mean >= 0.60:
        summary = "The set is not getting better or worse, and average value is still below the pack price."
        label = "Flat below break-even"
        reason_code = "flat_below_break_even"
        severity = "caution"
    else:
        summary = "The set is not moving much, and average value remains well below the pack price."
        label = "Flat and far below cost"
        reason_code = "flat_far_below_break_even"
        severity = "negative"

    if point_count <= 7:
        summary = f"So far, {summary[0].lower()}{summary[1:]}"

    # Append P95 upside context when it adds meaningful nuance.
    p95_note = _p95_supplement(last_p95, first_p95, weakening, improving, flat)
    if p95_note:
        summary = f"{summary} {p95_note}"

    trend_profile = reason_code

    evidence: List[EvidenceItem] = [
        EvidenceItem("Data points", str(point_count)),
        EvidenceItem("First mean-to-cost", format_ratio(first_mean)),
        EvidenceItem("Latest mean-to-cost", format_ratio(last_mean)),
        EvidenceItem("Mean delta", format_ratio(mean_delta) if mean_delta is not None else "N/A"),
        EvidenceItem("First median-to-cost", format_ratio(first_median)),
        EvidenceItem("Latest median-to-cost", format_ratio(last_median)),
        EvidenceItem("Median delta", format_ratio(median_delta) if median_delta is not None else "N/A"),
        EvidenceItem("Latest P95-to-cost", format_ratio(last_p95) if last_p95 is not None else "N/A"),
        EvidenceItem("P95 delta", format_ratio(p95_delta) if p95_delta is not None else "N/A"),
    ]

    return SectionInterpretation(
        summary=summary,
        label=label,
        reason_code=reason_code,
        severity=severity,
        confidence=confidence,
        evidence=evidence,
        signals={
            "trend_profile": trend_profile,
            "history_points_count": point_count,
            "mean_delta": mean_delta,
            "median_delta": median_delta,
            "p95_delta": p95_delta,
            "last_mean_ratio": last_mean,
            "last_median_ratio": last_median,
            "last_p95_ratio": last_p95,
            "break_even_band": break_even_band,
        },
    )

