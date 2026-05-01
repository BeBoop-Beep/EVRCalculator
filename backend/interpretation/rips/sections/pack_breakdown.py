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

    normal_count = 0
    god_count = 0
    demi_god_count = 0

    special_count = 0
    for path_name, count in ordered_paths:
        lowered = str(path_name or "").lower()
        numeric_count = int(count or 0)
        if "normal" in lowered:
            normal_count += numeric_count
        if "demi" in lowered and "god" in lowered:
            demi_god_count += numeric_count
        if "god" in lowered and "demi" not in lowered:
            god_count += numeric_count
        if any(token in lowered for token in ("special", "god", "demi", "bonus")):
            special_count += numeric_count

    normal_share = safe_percent_share(float(normal_count), float(total)) or 0.0
    special_share = safe_percent_share(float(special_count), float(total)) or 0.0
    god_share = safe_percent_share(float(god_count), float(total)) or 0.0
    demi_god_share = safe_percent_share(float(demi_god_count), float(total)) or 0.0

    top_state_name: Optional[str] = None
    top_state_share = 0.0
    baseline_share = 0.0
    normal_state_count = len(normal_states)
    if normal_states:
        ordered_states = sorted(normal_states.items(), key=lambda item: item[1], reverse=True)
        top_state_name_raw, top_state_count = ordered_states[0]
        top_state_name = str(top_state_name_raw)
        total_states = sum(int(value or 0) for _, value in ordered_states)
        top_state_share = safe_percent_share(float(top_state_count), float(total_states)) or 0.0

        baseline_candidates = 0
        for state_name, count in ordered_states:
            lowered = str(state_name or "").lower()
            if any(token in lowered for token in ("baseline", "miss", "no_hit", "bulk")):
                baseline_candidates += int(count or 0)
        baseline_share = safe_percent_share(float(baseline_candidates), float(total_states)) or 0.0

    if god_share > 0:
        summary = "There is a rare god-pack path in the simulation, but normal packs still make up nearly all results."
        label = "God pack chance exists"
        reason_code = "god_pack_present"
        severity = "neutral"
    elif special_share >= 0.01:
        summary = "Special pack paths show up often enough to matter, adding more variety to how value appears."
        label = "Special path matters"
        reason_code = "special_path_matters"
        severity = "positive"
    elif special_share > 0:
        summary = "Special paths exist, but they are rare enough that most packs still behave like normal packs."
        label = "Rare special path"
        reason_code = "rare_special_path"
        severity = "neutral"
    elif normal_share >= 0.995 and baseline_share < 0.60 and normal_state_count >= 5:
        summary = "Nearly every pack follows the normal path, but there is more variety in the hit states underneath."
        label = "Normal packs, varied hits"
        reason_code = "normal_with_hit_variety"
        severity = "neutral"
    elif lead_share >= 0.9999 and special_share == 0:
        summary = "Almost every simulated pack follows the same path, so value mostly depends on what happens inside normal packs."
        label = "One main pack path"
        reason_code = "one_path_only"
        severity = "neutral"
    elif normal_share >= 0.995 and baseline_share >= 0.60:
        summary = "Most packs follow the normal path, and the baseline state makes up most results."
        label = "Mostly normal packs"
        reason_code = "mostly_normal_baseline"
        severity = "neutral"
    else:
        summary = "Most packs follow the normal path, with some variation in how the normal states resolve."
        label = "Mostly normal packs"
        reason_code = "mostly_normal_baseline"
        severity = "neutral"

    confidence = "high" if len(ordered_paths) >= 3 and total >= 50 else ("medium" if total >= 5 else "low")

    evidence: List[EvidenceItem] = [
        EvidenceItem("Dominant path", str(lead_name)),
        EvidenceItem("Dominant path share", format_percent(lead_share)),
        EvidenceItem("Special path share", format_percent(special_share)),
        EvidenceItem("God pack share", format_percent(god_share)),
    ]
    if top_state_name:
        evidence.append(EvidenceItem("Top normal state", top_state_name))
        evidence.append(EvidenceItem("Top normal state share", format_percent(top_state_share)))
        evidence.append(EvidenceItem("Baseline share", format_percent(baseline_share)))

    return SectionInterpretation(
        summary=summary,
        label=label,
        reason_code=reason_code,
        severity=severity,
        confidence=confidence,
        evidence=evidence,
        signals={
            "pack_breakdown_profile": reason_code,
            "dominant_path_share": lead_share,
            "special_path_share": special_share,
            "normal_path_share": normal_share,
            "god_pack_share": god_share,
            "demi_god_pack_share": demi_god_share,
            "baseline_share": baseline_share,
            "normal_state_count": normal_state_count,
            "top_normal_state": top_state_name,
        },
    )
