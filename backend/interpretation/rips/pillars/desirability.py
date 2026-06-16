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
    source_metric = summary_data.get("desirability_source_metric") or "opening_desirability_score"
    scoring_version = summary_data.get("desirability_scoring_version") or "opening_desirability_v1"
    rip_source = summary_data.get("rip_desirability_source") or "missing"

    if is_fallback:
        if rip_source == "collector_appeal_fallback":
            label = "Collector-only appeal"
            summary = "Opening Desirability needs chase data for this set, so this pillar is temporarily using Collector Appeal."
            reason_code = "collector_appeal_fallback"
        else:
            label = "Neutral Opening Desirability"
            summary = "Opening Desirability data is not available yet, so this pillar is using a neutral score."
            reason_code = "neutral_desirability_fallback"
        severity = "neutral"
        confidence = "low"
    elif strength is not None and strength >= 4:
        label = "High Opening Desirability"
        summary = "Opening Desirability is strong compared with other sets."
        reason_code = "high_opening_desirability"
        severity = "positive"
        confidence = "high"
    elif strength is not None and strength <= 1:
        label = "Lower Opening Desirability"
        summary = "Opening Desirability is weaker than most sets in the current data."
        reason_code = "low_opening_desirability"
        severity = "caution"
        confidence = "high"
    else:
        label = "Average Opening Desirability"
        summary = "Opening Desirability is around the middle of the current set data."
        reason_code = "average_opening_desirability"
        severity = "neutral"
        confidence = "medium" if score is not None else "low"

    evidence = [
        EvidenceItem("Opening Desirability", f"{score:.1f}/100" if score is not None else "N/A"),
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
        "rip_desirability_source": rip_source,
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
