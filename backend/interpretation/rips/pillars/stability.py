"""Independent interpretation logic for the Stability pillar."""

from __future__ import annotations

from typing import Any, Dict

from ..models import EvidenceItem, SectionInterpretation, StabilityInterpretation
from ..thresholds import (
    build_stability_context,
    format_percent,
    get_numeric,
    get_summary_data,
)


def interpret_stability(data: Dict[str, Any]) -> StabilityInterpretation:
    summary_data = get_summary_data(data)
    context = build_stability_context(summary_data)

    score = context["score"]
    tier = context["tier"]
    strength = context["strength"]
    coefficient_of_variation = get_numeric(summary_data, "coefficient_of_variation")
    hhi_ev_concentration = get_numeric(summary_data, "hhi_ev_concentration")
    top1_share = get_numeric(summary_data, "top1_ev_share")
    top3_share = get_numeric(summary_data, "top3_ev_share")
    effective_chase_count = get_numeric(summary_data, "effective_chase_count")
    top1_extreme = top1_share is not None and top1_share >= 0.30
    top3_extreme = top3_share is not None and top3_share >= 0.45
    high_tier = strength is not None and strength >= 4
    low_tier = strength is not None and strength <= 1

    if top1_extreme:
        label = "One card carries value"
        summary = "One card carries too much of the value, so this set depends heavily on landing it."
        reason_code = "single_card_dominance"
        profile = "single_card_dependent"
    elif top3_extreme:
        label = "Top cards carry value"
        summary = "A small group of cards carries a large share of the value, so results depend heavily on landing the right hits."
        reason_code = "top_heavy_concentration"
        profile = "top_heavy"
    elif effective_chase_count is not None and effective_chase_count >= 25:
        label = "Value is well spread"
        summary = "Value is spread across many cards, so the set is not relying on one perfect pull."
        reason_code = "well_spread_value"
        profile = "well_spread"
    elif effective_chase_count is not None and effective_chase_count >= 15:
        label = "Decent value spread"
        summary = "Value is spread across a decent group of cards, though the best hits still matter."
        reason_code = "decent_spread"
        profile = "decent_spread"
    else:
        label = "Thin value spread"
        summary = "Value is not spread across enough cards, so the set needs the right hits to feel strong."
        reason_code = "thin_spread"
        profile = "thin_spread"

    if high_tier and not top1_extreme and not top3_extreme and label == "Thin value spread":
        label = "Decent value spread"
        summary = "Compared to other sets, value is spread well enough to avoid leaning on one perfect pull."
        reason_code = "high_tier_relative_spread"
        profile = "high_tier_relative"

    if low_tier and not top1_extreme and not top3_extreme and effective_chase_count is not None and effective_chase_count < 25:
        summary = "Value is spread thin for this tier, so the path to strong returns stays fragile without the right hits."

    if high_tier:
        severity = "positive"
    elif low_tier and (top1_extreme or top3_extreme or (effective_chase_count is not None and effective_chase_count < 15)):
        severity = "caution"
    else:
        severity = "neutral"

    confidence: str
    if score is not None and top1_share is not None and top3_share is not None and effective_chase_count is not None:
        confidence = "high"
    elif score is not None:
        confidence = "medium"
    else:
        confidence = "low"

    concentration_proxy = max(
        [value for value in (top1_share, top3_share, hhi_ev_concentration) if value is not None],
        default=None,
    )
    if concentration_proxy is None:
        value_spread = "Unknown"
    elif concentration_proxy >= 0.45:
        value_spread = "Concentrated"
    elif concentration_proxy >= 0.25:
        value_spread = "Moderate"
    else:
        value_spread = "Broad"

    evidence = [
        EvidenceItem("Top card share", format_percent(top1_share)),
        EvidenceItem("Top 3 card share", format_percent(top3_share)),
        EvidenceItem("Chase depth", f"{effective_chase_count:.1f}" if effective_chase_count is not None else "N/A"),
        EvidenceItem("Value spread", value_spread),
    ]

    signals: Dict[str, Any] = {
        "profile": profile,
        "top1_ev_share": top1_share,
        "top3_ev_share": top3_share,
        "effective_chase_count": effective_chase_count,
        "hhi_ev_concentration": hhi_ev_concentration,
        "coefficient_of_variation": coefficient_of_variation,
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

    return StabilityInterpretation(
        summary=summary,
        signals=signals,  # type: ignore[arg-type]
        score=score,
        meta=meta,
    )
