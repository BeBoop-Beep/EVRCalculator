"""Pack Breakdown interpretation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import EvidenceItem, SectionInterpretation
from ..thresholds import format_percent, safe_percent_share


def interpret_pack_breakdown(data: Dict[str, Any]) -> SectionInterpretation:
    rip_stats = data.get("rip_statistics") or {}
    pack_paths = rip_stats.get("pack_paths") or {}
    normal_states = rip_stats.get("normal_pack_states") or {}

    if not pack_paths:
        return SectionInterpretation(
            summary="Pack path data is limited, so path-level behavior cannot yet be characterized reliably.",
            label="Pack path data limited",
            reason_code="no_pack_paths",
            severity="data_limited",
            confidence="low",
        )

    ordered_paths = sorted(pack_paths.items(), key=lambda item: item[1], reverse=True)
    lead_name, lead_count = ordered_paths[0]
    total = sum(int(value or 0) for _, value in ordered_paths)

    if total <= 0:
        return SectionInterpretation(
            summary="Pack path data is present but does not show meaningful frequency separation yet.",
            label="Pack path data limited",
            reason_code="zero_path_total",
            severity="data_limited",
            confidence="low",
        )

    lead_share = safe_percent_share(float(lead_count), float(total)) or 0.0

    special_count = 0
    for path_name, count in ordered_paths:
        lowered = str(path_name or "").lower()
        if any(token in lowered for token in ("special", "god", "demi", "bonus")):
            special_count += int(count or 0)
    special_share = safe_percent_share(float(special_count), float(total)) or 0.0

    top_state_name: Optional[str] = None
    top_state_share = 0.0
    if normal_states:
        ordered_states = sorted(normal_states.items(), key=lambda item: item[1], reverse=True)
        top_state_name_raw, top_state_count = ordered_states[0]
        top_state_name = str(top_state_name_raw)
        total_states = sum(int(value or 0) for _, value in ordered_states)
        top_state_share = safe_percent_share(float(top_state_count), float(total_states)) or 0.0

    if lead_share >= 0.55:
        summary = "Most packs follow the same basic path, so there is not much variety in how value shows up."
        label = "Most packs follow one path"
        reason_code = "dominant_path"
        severity = "neutral"
    elif special_share >= 0.15 and lead_share < 0.60:
        summary = "Special pack types can add upside, but they are not common enough to drive the whole set."
        label = "Special packs add occasional upside"
        reason_code = "special_paths_present"
        severity = "positive"
    elif top_state_name and top_state_share >= 0.45:
        summary = "Most packs run through a single standard type, making outcomes fairly predictable."
        label = "Standard pack structure"
        reason_code = "dominant_normal_state"
        severity = "neutral"
    else:
        summary = "Most packs follow the standard path, but there is some variety in how they resolve."
        label = "Mostly standard, some variety"
        reason_code = "distributed_normal_paths"
        severity = "neutral"

    confidence = "high" if len(ordered_paths) >= 3 and total >= 50 else ("medium" if total >= 5 else "low")

    evidence: List[EvidenceItem] = [
        EvidenceItem("Dominant path", str(lead_name)),
        EvidenceItem("Dominant path share", format_percent(lead_share)),
        EvidenceItem("Special path share", format_percent(special_share)),
    ]
    if top_state_name:
        evidence.append(EvidenceItem("Top normal state", top_state_name))
        evidence.append(EvidenceItem("Top normal state share", format_percent(top_state_share)))

    return SectionInterpretation(
        summary=summary,
        label=label,
        reason_code=reason_code,
        severity=severity,
        confidence=confidence,
        evidence=evidence,
        signals={
            "lead_share": lead_share,
            "special_share": special_share,
            "top_state_share": top_state_share,
            "path_count": len(ordered_paths),
        },
    )
