"""Independent interpretation logic for the Desirability pillar."""

from __future__ import annotations

from typing import Any, Dict

from ..models import DesirabilityInterpretation, EvidenceItem, SectionInterpretation
from ..thresholds import build_desirability_context, get_summary_data


def interpret_desirability(data: Dict[str, Any]) -> DesirabilityInterpretation:
    summary_data = get_summary_data(data)
    context = build_desirability_context(summary_data)

    score = context["score"]
    tier = context["tier"]
    strength = context["strength"]
    is_fallback = bool(summary_data.get("desirability_is_fallback"))
    source_metric = summary_data.get("desirability_source_metric") or "weighted_average_hit_desirability_score"
    scoring_version = summary_data.get("desirability_scoring_version") or "pokemon_set_hit_desirability_v1"

    if is_fallback:
        label = "Neutral collector appeal"
        summary = "Desirability data is not available yet, so this pillar is using a neutral score."
        reason_code = "neutral_desirability_fallback"
        severity = "neutral"
        confidence = "low"
    elif strength is not None and strength >= 4:
        label = "High collector appeal"
        summary = "Hit-card desirability is strong compared with other sets."
        reason_code = "high_hit_card_desirability"
        severity = "positive"
        confidence = "high"
    elif strength is not None and strength <= 1:
        label = "Lower collector appeal"
        summary = "Hit-card desirability is weaker than most sets in the current desirability data."
        reason_code = "low_hit_card_desirability"
        severity = "caution"
        confidence = "high"
    else:
        label = "Average collector appeal"
        summary = "Hit-card desirability is around the middle of the current set data."
        reason_code = "average_hit_card_desirability"
        severity = "neutral"
        confidence = "medium" if score is not None else "low"

    evidence = [
        EvidenceItem("Hit-card desirability", f"{score:.1f}/100" if score is not None else "N/A"),
        EvidenceItem("Source metric", source_metric),
        EvidenceItem("Version", scoring_version),
    ]
    if is_fallback:
        evidence.append(
            EvidenceItem(
                "Fallback",
                summary_data.get("desirability_fallback_reason") or "neutral score",
            )
        )

    signals: Dict[str, Any] = {
        "profile": reason_code,
        "tier": tier,
        "strength": strength,
        "source_metric": source_metric,
        "scoring_version": scoring_version,
        "is_fallback": is_fallback,
        "fallback_reason": summary_data.get("desirability_fallback_reason"),
    }

    meta = SectionInterpretation(
        summary=summary,
        label=label,
        reason_code=reason_code,
        severity=severity,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        evidence=evidence,
        signals=signals,
    )

    return DesirabilityInterpretation(
        summary=summary,
        signals=signals,
        score=score,
        meta=meta,
    )
