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

    tier_key = str(tier or "").strip().upper()
    tier_copy = {
        "S": {
            "label": "Elite downside control",
            "summary": "Compared with other sets, misses are easier to handle and downside is unusually controlled. Losing packs still happen, but this profile gives back more value than most when it misses.",
            "reason_code": "elite_downside_control",
            "severity": "positive",
        },
        "A": {
            "label": "Strong downside control",
            "summary": "Relative to other sets, misses are less punishing. This does not make packs risk-free, but the downside profile is stronger than most.",
            "reason_code": "strong_downside_control",
            "severity": "positive",
        },
        "B": {
            "label": "Controlled misses",
            "summary": "Losing outcomes still happen, but compared with many sets, misses are more manageable. This is an above-average safety profile, but it does not remove the risk of missing.",
            "reason_code": "controlled_misses",
            "severity": "neutral",
        },
        "C": {
            "label": "Average safety profile",
            "summary": "Downside looks fairly typical compared with other ranked sets. Misses can still hurt, but this profile is neither unusually forgiving nor unusually punishing.",
            "reason_code": "average_safety_profile",
            "severity": "neutral",
        },
        "D": {
            "label": "Rougher misses",
            "summary": "Compared with other sets, misses are more punishing and downside is below average. This profile needs stronger hits to offset weak runs.",
            "reason_code": "rougher_misses",
            "severity": "caution",
        },
        "F": {
            "label": "Very punishing misses",
            "summary": "This is one of the more punishing downside profiles. When packs miss, they tend to give back very little compared with other sets.",
            "reason_code": "very_punishing_misses",
            "severity": "negative",
        },
    }

    selected = tier_copy.get(tier_key)
    if selected is not None:
        label = selected["label"]
        summary = selected["summary"]
        reason_code = selected["reason_code"]
        severity = selected["severity"]
    elif expected_loss_fraction is None:
        label = "Miss profile unclear"
        summary = "Loss behavior on misses is unclear with the available sample."
        reason_code = "missing_expected_loss_fraction"
        severity = "neutral"
    elif expected_loss_fraction >= 0.85:
        label = "Very punishing misses"
        summary = "Compared with other sets, this downside profile is harsh when it misses. Losing packs can give back very little for the cost."
        reason_code = "very_punishing_misses_fallback"
        severity = "negative"
    elif expected_loss_fraction >= 0.75:
        label = "Rougher misses"
        summary = "Downside looks rougher than average, so cold runs can be harder to absorb than in steadier sets."
        reason_code = "rougher_misses_fallback"
        severity = "caution"
    elif expected_loss_fraction >= 0.65:
        label = "Average safety profile"
        summary = "Downside appears around category average. Misses still hurt, but this profile is not unusually harsh."
        reason_code = "average_safety_profile_fallback"
        severity = "neutral"
    else:
        label = "Controlled misses"
        summary = "Misses still lose money, but downside appears more manageable than category average."
        reason_code = "controlled_misses_fallback"
        severity = "positive" if strength is not None and strength >= 4 else "neutral"

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
