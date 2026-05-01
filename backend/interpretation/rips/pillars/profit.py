"""Independent interpretation logic for the Profit pillar."""

from __future__ import annotations

from typing import Any, Dict

from ..models import EvidenceItem, ProfitInterpretation, SectionInterpretation
from ..thresholds import (
    build_profit_context,
    format_percent,
    format_ratio,
    get_numeric,
    get_summary_data,
)


def interpret_profit(data: Dict[str, Any]) -> ProfitInterpretation:
    summary_data = get_summary_data(data)
    context = build_profit_context(summary_data)

    score = context["score"]
    tier = context["tier"]
    strength = context["strength"]
    prob_profit = get_numeric(summary_data, "prob_profit")
    mean_to_cost = get_numeric(summary_data, "mean_value_to_cost_ratio")
    median_to_cost = get_numeric(summary_data, "median_value_to_cost_ratio")
    p95_to_cost = get_numeric(summary_data, "p95_value_to_cost_ratio")

    if prob_profit is None:
        probability_anchor = "Profit frequency is unclear from the available sample."
        profit_frequency = "unknown"
    elif prob_profit < 0.08:
        probability_anchor = "Profitable packs are very rare."
        profit_frequency = "very_low"
    elif prob_profit < 0.15:
        probability_anchor = "Most packs will not be profitable."
        profit_frequency = "low"
    elif prob_profit < 0.25:
        probability_anchor = "Winning packs are uncommon."
        profit_frequency = "uncommon"
    else:
        probability_anchor = "This set has a reasonable chance to pay off."
        profit_frequency = "reasonable"

    p95_high = p95_to_cost is not None and p95_to_cost >= 2.5
    mean_strong = mean_to_cost is not None and mean_to_cost >= 0.70
    median_weak = median_to_cost is not None and median_to_cost < 0.20

    if p95_high:
        ev_structure = "When it does hit, the best pulls are strong enough to carry the return."
        structure_code = "high_p95"
    elif mean_strong:
        ev_structure = "Average value holds up better than most sets."
        structure_code = "strong_mean"
    elif median_weak:
        ev_structure = "Most packs still come in well below cost."
        structure_code = "weak_median"
    else:
        ev_structure = "Returns are modest and not consistent."
        structure_code = "modest_returns"

    summary = f"{probability_anchor} {ev_structure}"

    high_tier = strength is not None and strength >= 4
    low_tier = strength is not None and strength <= 1

    if profit_frequency == "very_low" and p95_high:
        label = "Rare wins, big hits"
        reason_code = "rare_wins_big_hits"
    elif prob_profit is not None and prob_profit < 0.25 and mean_strong:
        label = "Low hit rate, solid average"
        reason_code = "low_hit_rate_solid_average"
    elif prob_profit is not None and prob_profit < 0.25 and median_weak:
        label = "Low hit rate, weak normal packs"
        reason_code = "low_hit_rate_weak_normal"
    elif high_tier and p95_high:
        label = "Strong hits carry return"
        reason_code = "high_tier_hits_carry_return"
    elif low_tier:
        label = "Weak return"
        reason_code = "low_tier_weak_return"
    elif p95_high:
        label = "Strong hits carry return"
        reason_code = "hits_carry_return"
    elif mean_strong:
        label = "Solid average return"
        reason_code = "solid_average_return"
    elif median_weak:
        label = "Weak normal pack returns"
        reason_code = "weak_normal_pack_returns"
    else:
        label = "Mixed return profile"
        reason_code = "mixed_return_profile"

    if strength is not None and strength >= 4:
        severity = "positive"
    elif strength is not None and strength <= 1:
        severity = "negative"
    else:
        severity = "neutral"

    confidence: str
    if score is not None and prob_profit is not None and p95_to_cost is not None:
        confidence = "high"
    elif score is not None:
        confidence = "medium"
    else:
        confidence = "low"

    evidence = [
        EvidenceItem("Chance to profit", format_percent(prob_profit)),
        EvidenceItem("Average pack return", format_ratio(mean_to_cost)),
        EvidenceItem("Typical pack return", format_ratio(median_to_cost)),
        EvidenceItem("Big-hit range", format_ratio(p95_to_cost)),
    ]

    signals: Dict[str, Any] = {
        "profit_frequency": profit_frequency,
        "ev_structure": structure_code,
        "probability_anchor": probability_anchor,
        "tier": tier,
        "strength": strength,
    }

    meta = SectionInterpretation(
        summary=summary,
        label=label,
        reason_code=reason_code,
        severity=severity,
        confidence=confidence,
        evidence=evidence,
        signals=signals,
    )

    return ProfitInterpretation(
        summary=summary,
        signals=signals,  # type: ignore[arg-type]
        score=score,
        meta=meta,
    )
