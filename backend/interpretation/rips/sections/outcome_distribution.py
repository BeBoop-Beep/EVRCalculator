"""Outcome Distribution interpretation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import EvidenceItem, SectionInterpretation
from ..thresholds import format_currency, format_percent, format_ratio, get_numeric


def _read_p99_ratio(data: Dict[str, Any], pack_cost: Optional[float]) -> Optional[float]:
    summary_data = data.get("summary") if isinstance(data.get("summary"), dict) else data
    p99 = get_numeric(summary_data, "p99_value_to_cost_ratio")
    if p99 is not None:
        return p99
    percentiles = data.get("percentiles") or []
    for row in percentiles:
        percentile = get_numeric(row if isinstance(row, dict) else {}, "percentile")
        if percentile is None or int(percentile) != 99:
            continue
        p99_value = get_numeric(row if isinstance(row, dict) else {}, "value")
        if p99_value is not None and pack_cost is not None and pack_cost > 0:
            return p99_value / pack_cost
    return None


def _to_ratio(value: Optional[float], pack_cost: Optional[float]) -> Optional[float]:
    if value is None or pack_cost is None or pack_cost <= 0:
        return None
    return value / pack_cost


def interpret_outcome_distribution(data: Dict[str, Any]) -> SectionInterpretation:
    summary_data = data.get("summary") if isinstance(data.get("summary"), dict) else data
    pack_cost = get_numeric(summary_data, "pack_cost")
    prob_profit = get_numeric(summary_data, "prob_profit")
    prob_big_hit = get_numeric(summary_data, "prob_big_hit")
    median_value = get_numeric(summary_data, "median_value")
    tail_value_p05 = get_numeric(summary_data, "tail_value_p05")
    p5_value = get_numeric(summary_data, "p5_value")
    max_value = get_numeric(summary_data, "max_value")
    big_hit_threshold = get_numeric(summary_data, "big_hit_threshold")
    p95_ratio = get_numeric(summary_data, "p95_value_to_cost_ratio")
    p99_ratio = _read_p99_ratio(data, pack_cost)
    median_to_cost_ratio = get_numeric(summary_data, "median_value_to_cost_ratio")
    p95_value = get_numeric(summary_data, "p95_value")

    median_to_cost = median_to_cost_ratio
    if median_to_cost is None and median_value is not None and pack_cost and pack_cost > 0:
        median_to_cost = median_value / pack_cost
    p95_to_cost = p95_ratio if p95_ratio is not None else _to_ratio(p95_value, pack_cost)
    p5_value_effective = p5_value if p5_value is not None else tail_value_p05
    p5_to_cost = _to_ratio(p5_value_effective, pack_cost)
    max_to_cost = _to_ratio(max_value, pack_cost)
    big_hit_to_cost = _to_ratio(big_hit_threshold, pack_cost)

    if median_to_cost is not None and median_to_cost < 0.30 and p95_to_cost is not None and p95_to_cost < 1.00:
        summary = "Normal packs are weak, and even the better outcomes struggle to clear the pack price."
        label = "Low floor, weak ceiling"
        reason_code = "low_floor_weak_ceiling"
        severity = "negative"
    elif median_to_cost is not None and median_to_cost < 0.30 and p95_to_cost is not None and p95_to_cost < 1.25:
        summary = "Normal packs are weak, and the better outcomes only barely clear the pack price."
        label = "Low floor, thin upside"
        reason_code = "low_floor_thin_upside"
        severity = "caution"
    elif median_to_cost is not None and median_to_cost < 0.20 and p95_to_cost is not None and p95_to_cost < 1.50:
        summary = "Most packs come in low, and even the stronger outcomes do not separate much from the pack price."
        label = "Weak payout shape"
        reason_code = "weak_distribution"
        severity = "negative"
    elif max_to_cost is not None and max_to_cost >= 100 and (
        (p99_ratio is not None and p99_ratio < 15)
        or (p99_ratio is None and median_to_cost is not None and median_to_cost < 0.35)
    ):
        summary = "Most outcomes stay low, but the very top end has a rare outlier that stretches the chart."
        label = "Extreme outlier at the top"
        reason_code = "extreme_outlier_shape"
        severity = "neutral"
    elif prob_big_hit is not None and prob_big_hit < 0.01 and p95_to_cost is not None and p95_to_cost >= 2.00:
        summary = "There is real upside here, but the stronger outcomes are hard to reach and most packs stay below them."
        label = "Big hits are hard to reach"
        reason_code = "chase_heavy_distribution"
        severity = "neutral"
    elif median_to_cost is not None and median_to_cost < 0.30 and p95_to_cost is not None and p95_to_cost >= 2.50:
        summary = "Most packs land well below cost, but the better outcomes can jump several times above the pack price."
        label = "Low floor, big ceiling"
        reason_code = "low_floor_big_ceiling"
        severity = "neutral"
    elif median_to_cost is not None and median_to_cost >= 0.35 and p95_to_cost is not None and p95_to_cost < 2.50:
        summary = "Normal packs hold up better than most, but the high-end jump is more limited."
        label = "Smoother, lower ceiling"
        reason_code = "smoother_midrange"
        severity = "positive"
    elif median_to_cost is not None and median_to_cost >= 0.25 and p95_to_cost is not None and p95_to_cost >= 1.75:
        summary = "Typical packs still trail the price, but the better outcomes give the set some room to run."
        label = "Some floor, some upside"
        reason_code = "midrange_with_some_upside"
        severity = "neutral"
    else:
        summary = "Most packs are below cost, but a few bigger outcomes pull the average higher."
        label = "Most packs miss, hits carry value"
        reason_code = "most_packs_miss_hits_carry"
        severity = "neutral"

    outcome_profile = reason_code

    confidence: str
    key_fields = [prob_profit, p95_to_cost, median_to_cost]
    filled = sum(1 for f in key_fields if f is not None)
    confidence = "high" if filled == 3 else ("medium" if filled >= 1 else "low")

    evidence: List[EvidenceItem] = [
        EvidenceItem("Pack Cost", format_currency(pack_cost)),
        EvidenceItem("P5", format_currency(p5_value_effective)),
        EvidenceItem("Median", format_currency(median_value)),
        EvidenceItem("P95", format_ratio(p95_to_cost)),
        EvidenceItem("P99", format_ratio(p99_ratio)),
        EvidenceItem("Big Hit", format_currency(big_hit_threshold)),
        EvidenceItem("Max", format_currency(max_value)),
    ]

    return SectionInterpretation(
        summary=summary,
        label=label,
        reason_code=reason_code,
        severity=severity,
        confidence=confidence,
        evidence=evidence,
        signals={
            "outcome_profile": outcome_profile,
            "median_to_cost": median_to_cost,
            "p95_to_cost": p95_to_cost,
            "p99_to_cost": p99_ratio,
            "max_to_cost": max_to_cost,
            "p5_to_cost": p5_to_cost,
            "big_hit_to_cost": big_hit_to_cost,
            "prob_big_hit": prob_big_hit,
            "prob_profit": prob_profit,
        },
    )
