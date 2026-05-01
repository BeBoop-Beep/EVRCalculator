"""Independent interpretation logic for the Safety pillar."""

from __future__ import annotations

from typing import Any, Dict

from ..models import EvidenceItem, SafetyInterpretation, SectionInterpretation
from ..thresholds import (
    build_safety_context,
    format_currency,
    format_percent,
    get_numeric,
    get_summary_data,
)


def interpret_safety(data: Dict[str, Any]) -> SafetyInterpretation:
    summary_data = get_summary_data(data)
    context = build_safety_context(summary_data)

    score = context["score"]
    tier = context["tier"]
    strength = context["strength"]
    pack_cost = get_numeric(summary_data, "pack_cost")
    expected_loss_fraction = get_numeric(summary_data, "expected_loss_when_losing_fraction")
    median_loss_fraction = get_numeric(summary_data, "median_loss_when_losing_fraction")
    p05_shortfall = get_numeric(summary_data, "p05_shortfall_to_cost")
    expected_loss_per_pack = get_numeric(summary_data, "expected_loss_per_pack")

    if expected_loss_fraction is None:
        label = "Miss profile unclear"
        summary = "Loss behavior on misses is unclear with the available sample."
        reason_code = "missing_expected_loss_fraction"
    elif expected_loss_fraction >= 0.85:
        label = "Brutal misses"
        summary = "Misses are extremely punishing. Most losing packs give back almost nothing."
        reason_code = "brutal_misses"
    elif expected_loss_fraction >= 0.80:
        label = "Very rough misses"
        summary = "Bad packs give back very little, so cold streaks can hurt fast."
        reason_code = "very_rough_misses"
    elif expected_loss_fraction >= 0.75:
        label = "Rough misses"
        summary = "Misses are rough. Losing packs give back very little for the cost."
        reason_code = "rough_misses"
    elif expected_loss_fraction >= 0.70:
        label = "Manageable misses"
        summary = "Misses still lose money, but they are easier to handle than most sets."
        reason_code = "manageable_misses"
    else:
        label = "Safer misses"
        summary = "Misses are easier to handle. Losing packs give back more than most sets."
        reason_code = "safer_misses"

    # Keep S/A safety framing relative and avoid alarmist wording.
    if strength is not None and strength >= 4:
        summary = "Misses still lose money, but compared to other sets, they are easier to handle here."
        if label in {"Brutal misses", "Very rough misses", "Rough misses"}:
            label = "Manageable misses"
            reason_code = "high_tier_relative_manageable_misses"

    if strength is not None and strength >= 4:
        severity = "positive"
    elif strength is not None and strength <= 1:
        severity = "negative"
    else:
        severity = "neutral"

    confidence: str
    if score is not None and expected_loss_fraction is not None and p05_shortfall is not None:
        confidence = "high"
    elif score is not None:
        confidence = "medium"
    else:
        confidence = "low"

    evidence = [
        EvidenceItem("Loss on losing packs", format_percent(expected_loss_fraction)),
        EvidenceItem("Typical loss", format_percent(median_loss_fraction)),
        EvidenceItem("Worst-pack shortfall", format_percent(p05_shortfall)),
        EvidenceItem("Loss per pack", format_currency(expected_loss_per_pack)),
    ]

    signals: Dict[str, Any] = {
        "expected_loss_when_losing_fraction": expected_loss_fraction,
        "median_loss_when_losing_fraction": median_loss_fraction,
        "p05_shortfall_to_cost": p05_shortfall,
        "pack_cost": pack_cost,
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

    return SafetyInterpretation(
        summary=summary,
        signals=signals,  # type: ignore[arg-type]
        score=score,
        meta=meta,
    )
