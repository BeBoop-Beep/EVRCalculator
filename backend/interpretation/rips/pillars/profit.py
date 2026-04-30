"""Independent interpretation logic for the Profit pillar."""

from __future__ import annotations

from typing import Any, Dict

from ..models import EvidenceItem, ProfitInterpretation, SectionInterpretation
from ..thresholds import (
    MEDIAN_TO_COST_WEAK_MAX,
    classify_probability,
    classify_ratio_high_medium_low,
    classify_score_strength,
    classify_tail_strength,
    format_percent,
    format_ratio,
    format_score,
    get_numeric,
)


def interpret_profit(data: Dict[str, Any]) -> ProfitInterpretation:
    summary_data = data.get("summary") if isinstance(data.get("summary"), dict) else data

    score = get_numeric(summary_data, "profit_score", "relative_profit_score")
    prob_profit = get_numeric(summary_data, "prob_profit")
    mean_to_cost = get_numeric(summary_data, "mean_value_to_cost_ratio")
    median_to_cost = get_numeric(summary_data, "median_value_to_cost_ratio")
    p95_to_cost = get_numeric(summary_data, "p95_value_to_cost_ratio")
    roi_percent = get_numeric(summary_data, "roi_percent")

    score_strength = classify_score_strength(score)

    upside_strength = classify_tail_strength(p95_to_cost, missing=score_strength)
    profit_frequency = classify_probability(prob_profit, missing=score_strength)

    average_strength = classify_ratio_high_medium_low(
        mean_to_cost,
        high_min=1.05,
        medium_min=0.92,
        missing=score_strength,
    )
    median_strength = classify_ratio_high_medium_low(
        median_to_cost,
        high_min=1.0,
        medium_min=0.85,
        missing="medium",
    )

    if median_to_cost is not None and median_to_cost >= 1.02:
        typical_outcome = "above_cost"
    elif median_to_cost is not None and median_to_cost >= 0.9:
        typical_outcome = "near_cost"
    else:
        typical_outcome = "below_cost"

    if profit_frequency == "high" and average_strength == "high" and median_strength in {"high", "medium"}:
        summary = "Profit looks strong because both average packs and typical packs are holding up well against the pack price."
        label = "Strong, broad returns"
        reason_code = "broad_profit"
        severity = "positive"
    elif average_strength == "high" and median_strength == "low":
        summary = "The average looks good because of big hits, but normal packs are still weaker."
        label = "Upside-led returns"
        reason_code = "tail_driven_profit"
        severity = "neutral"
    elif upside_strength == "high" and profit_frequency in {"low", "medium"}:
        summary = "This set can pay off, but it usually needs one of the better hits to do it."
        label = "Occasional big wins"
        reason_code = "high_upside_low_frequency"
        severity = "neutral"
    elif median_to_cost is not None and median_to_cost < MEDIAN_TO_COST_WEAK_MAX and upside_strength == "low":
        summary = "This set struggles to return value because normal packs and big-hit upside are both weak."
        label = "Weak value returns"
        reason_code = "weak_profit_structure"
        severity = "negative"
    elif roi_percent is not None and roi_percent < 0 and typical_outcome == "below_cost":
        summary = "Most packs here are below cost, and the overall average is negative \u2014 this set is hard to justify ripping."
        label = "Returns below cost"
        reason_code = "sub_cost_typical_outcome"
        severity = "negative"
    else:
        summary = "Value is mixed here \u2014 there is some upside, but normal packs and big wins are not pulling in the same direction."
        label = "Mixed value returns"
        reason_code = "mixed_profit"
        severity = "neutral"

    confidence: str
    if score is not None and prob_profit is not None and p95_to_cost is not None:
        confidence = "high"
    elif score is not None:
        confidence = "medium"
    else:
        confidence = "low"

    roi_str = f"{roi_percent:.1f}%" if roi_percent is not None else "N/A"
    evidence = [
        EvidenceItem("Profit score", format_score(score)),
        EvidenceItem("Chance to profit", format_percent(prob_profit)),
        EvidenceItem("Average pack return", format_ratio(mean_to_cost)),
        EvidenceItem("Typical pack return", format_ratio(median_to_cost)),
        EvidenceItem("p95 value-to-cost", format_ratio(p95_to_cost)),
        EvidenceItem("Est. ROI", roi_str),
    ]

    signals: Dict[str, Any] = {
        "upside_strength": upside_strength,
        "profit_frequency": profit_frequency,
        "typical_outcome": typical_outcome,
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
