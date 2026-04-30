"""Independent interpretation logic for the Stability pillar."""

from __future__ import annotations

from typing import Any, Dict

from ..models import EvidenceItem, SectionInterpretation, StabilityInterpretation
from ..thresholds import (
    classify_ratio_high_medium_low,
    classify_share_concentration,
    classify_score_strength,
    format_cardinality,
    format_percent,
    format_ratio,
    format_score,
    get_numeric,
)


def interpret_stability(data: Dict[str, Any]) -> StabilityInterpretation:
    summary_data = data.get("summary") if isinstance(data.get("summary"), dict) else data

    score = get_numeric(summary_data, "stability_score", "relative_stability_score")
    coefficient_of_variation = get_numeric(summary_data, "coefficient_of_variation")
    hhi_ev_concentration = get_numeric(summary_data, "hhi_ev_concentration")
    top1_share = get_numeric(summary_data, "top1_ev_share")
    top3_share = get_numeric(summary_data, "top3_ev_share")
    top5_share = get_numeric(summary_data, "top5_ev_share")
    effective_chase_count = get_numeric(summary_data, "effective_chase_count")
    p95_to_cost = get_numeric(summary_data, "p95_value_to_cost_ratio")

    score_strength = classify_score_strength(score)

    volatility = classify_ratio_high_medium_low(
        coefficient_of_variation,
        high_min=1.6,
        medium_min=0.9,
        missing=score_strength,
    )

    share_concentration = classify_share_concentration(top1_share, missing=score_strength)
    hhi_concentration = classify_ratio_high_medium_low(
        hhi_ev_concentration,
        high_min=0.22,
        medium_min=0.12,
        missing=score_strength,
    )
    concentration = "high" if "high" in {share_concentration, hhi_concentration} else (
        "medium" if "medium" in {share_concentration, hhi_concentration} else "low"
    )

    if effective_chase_count is not None and effective_chase_count >= 12:
        distribution_quality = "broad"
    elif effective_chase_count is not None and effective_chase_count >= 6:
        distribution_quality = "moderate"
    else:
        distribution_quality = "narrow"

    single_card_dependence = top1_share is not None and top1_share >= 0.40
    top_heavy_cluster = (top3_share is not None and top3_share >= 0.70) or (
        top5_share is not None and top5_share >= 0.85
    )

    if volatility == "high" and concentration == "high":
        summary = "Results can swing a lot because too much value depends on a small number of cards."
        label = "High swings, few key cards"
        reason_code = "volatile_concentrated"
        severity = "caution"
    elif single_card_dependence:
        summary = "One card carries too much of the value, so the set depends heavily on hitting it."
        label = "Single-card dependence"
        reason_code = "single_card_dominance"
        severity = "caution"
    elif concentration == "high" or top_heavy_cluster:
        summary = "Most of the value is tied up in just a few cards, so the set is top-heavy."
        label = "Top-heavy value"
        reason_code = "top_heavy_concentration"
        severity = "caution"
    elif distribution_quality == "broad" and concentration == "low" and volatility in {"low", "medium"}:
        summary = "Value is spread across several good cards, so the set is not relying on one card only."
        label = "Broad, stable value base"
        reason_code = "broad_distribution"
        severity = "positive"
    elif volatility == "low" and distribution_quality in {"moderate", "broad"} and p95_to_cost is not None and p95_to_cost < 1.25:
        summary = "Results are steady here, but that steadiness comes at the cost of big wins."
        label = "Stable but capped upside"
        reason_code = "stable_low_upside"
        severity = "neutral"
    else:
        summary = "Results are somewhat predictable, but there is still enough swing to keep things uncertain."
        label = "Moderate stability"
        reason_code = "moderate_stability"
        severity = "neutral"

    confidence: str
    if score is not None and coefficient_of_variation is not None and hhi_ev_concentration is not None:
        confidence = "high"
    elif score is not None:
        confidence = "medium"
    else:
        confidence = "low"

    cv_str = f"{coefficient_of_variation:.2f}" if coefficient_of_variation is not None else "N/A"
    hhi_str = f"{hhi_ev_concentration:.3f}" if hhi_ev_concentration is not None else "N/A"
    evidence = [
        EvidenceItem("Stability score", format_score(score)),
        EvidenceItem("Coefficient of variation", cv_str),
        EvidenceItem("Value spread", hhi_str),
        EvidenceItem("Top card share", format_percent(top1_share)),
        EvidenceItem("Top card share", format_percent(top1_share)),
        EvidenceItem("Top 5 EV share", format_percent(top5_share)),
        EvidenceItem("Effective contributor count", format_cardinality(effective_chase_count)),
    ]

    signals: Dict[str, Any] = {
        "volatility": volatility,
        "concentration": concentration,
        "distribution_quality": distribution_quality,
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

    return StabilityInterpretation(
        summary=summary,
        signals=signals,  # type: ignore[arg-type]
        score=score,
        meta=meta,
    )
