"""Outcome Distribution interpretation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import EvidenceItem, SectionInterpretation
from ..thresholds import classify_probability, classify_tail_strength, format_currency, format_percent, format_ratio, get_numeric


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


def interpret_outcome_distribution(data: Dict[str, Any]) -> SectionInterpretation:
    summary_data = data.get("summary") if isinstance(data.get("summary"), dict) else data
    pack_cost = get_numeric(summary_data, "pack_cost")
    prob_profit = get_numeric(summary_data, "prob_profit")
    prob_big_hit = get_numeric(summary_data, "prob_big_hit")
    median_value = get_numeric(summary_data, "median_value")
    tail_value_p05 = get_numeric(summary_data, "tail_value_p05")
    max_value = get_numeric(summary_data, "max_value")
    p95_ratio = get_numeric(summary_data, "p95_value_to_cost_ratio")
    p99_ratio = _read_p99_ratio(data, pack_cost)
    median_to_cost_ratio = get_numeric(summary_data, "median_value_to_cost_ratio")

    median_to_cost = median_to_cost_ratio
    if median_to_cost is None and median_value is not None and pack_cost and pack_cost > 0:
        median_to_cost = median_value / pack_cost
    p05_recovery_share = (tail_value_p05 / pack_cost) if (tail_value_p05 is not None and pack_cost and pack_cost > 0) else None

    profit_frequency = classify_probability(prob_profit, missing="medium")
    tail_strength = classify_tail_strength(p95_ratio, missing="medium")
    big_hit_access = classify_probability(prob_big_hit, strong_min=0.20, low_max=0.07, missing="medium")

    if median_to_cost is not None and median_to_cost < 1.0 and tail_strength == "high" and profit_frequency == "low":
        summary = "Most packs are below cost, but a few big hits pull the average higher."
        label = "Most packs miss, tail carries value"
        reason_code = "tail_heavy_below_cost"
        severity = "neutral"
    elif p05_recovery_share is not None and p05_recovery_share < 0.25 and tail_strength == "high":
        summary = "The best hits are much stronger than you would expect, but the worst packs give back almost nothing."
        label = "Strong top end, painful misses"
        reason_code = "strong_tail_weak_floor"
        severity = "caution"
    elif median_to_cost is not None and median_to_cost >= 0.92 and profit_frequency in {"medium", "high"} and tail_strength in {"medium", "high"}:
        summary = "Normal packs hold up close to cost and there is still room to hit something good \u2014 this is one of the better distributions."
        label = "Typical packs stay near cost"
        reason_code = "near_cost_healthy"
        severity = "positive"
    elif tail_strength == "high" and p99_ratio is not None and p95_ratio is not None and p99_ratio >= (p95_ratio * 1.25):
        summary = "The best hits are much stronger than the normal good hits, so the top end can jump fast."
        label = "Top-end can jump fast"
        reason_code = "extreme_tail_extension"
        severity = "positive"
    elif big_hit_access == "low" and max_value is not None and max_value > (pack_cost or 0) * 2:
        summary = "There are strong hits in the set, but they are hard to pull \u2014 most packs end up well below the best outcomes."
        label = "Strong hits, hard to access"
        reason_code = "low_big_hit_access"
        severity = "neutral"
    else:
        summary = "Most packs are below cost, but some upside is still there \u2014 just unevenly spread."
        label = "Mixed distribution"
        reason_code = "mixed_distribution"
        severity = "neutral"

    confidence: str
    key_fields = [prob_profit, p95_ratio, median_to_cost]
    filled = sum(1 for f in key_fields if f is not None)
    confidence = "high" if filled == 3 else ("medium" if filled >= 1 else "low")

    evidence: List[EvidenceItem] = [
        EvidenceItem("Typical pack return", format_ratio(median_to_cost)),
        EvidenceItem("Worst-pack value (p05)", format_percent(p05_recovery_share)),
        EvidenceItem("Big-hit range (p95)", format_ratio(p95_ratio)),
        EvidenceItem("p99 value-to-cost", format_ratio(p99_ratio)),
        EvidenceItem("Chance to profit", format_percent(prob_profit)),
        EvidenceItem("Chase hit frequency", format_percent(prob_big_hit)),
        EvidenceItem("Max observed value", format_currency(max_value)),
    ]

    return SectionInterpretation(
        summary=summary,
        label=label,
        reason_code=reason_code,
        severity=severity,
        confidence=confidence,
        evidence=evidence,
        signals={
            "profit_frequency": profit_frequency,
            "tail_strength": tail_strength,
            "big_hit_access": big_hit_access,
            "median_to_cost": median_to_cost,
            "p05_recovery_share": p05_recovery_share,
        },
    )
