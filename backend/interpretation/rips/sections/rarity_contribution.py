"""Rarity Contribution interpretation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import EvidenceItem, SectionInterpretation
from ..thresholds import TOP_RARITY_EV_CONCENTRATION_HIGH_MIN, format_percent, normalize_rarity_name, safe_percent_share


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_low_value_bucket(rarity: str) -> bool:
    rarity_l = rarity.lower()
    return any(
        token in rarity_l
        for token in ("common", "uncommon", "reverse", "regular", "normal", "holo")
    )


def interpret_rarity_contribution(data: Dict[str, Any]) -> SectionInterpretation:
    rankings: List[Dict[str, Any]] = data.get("rankings") or []

    if not rankings:
        return SectionInterpretation(
            summary="Rarity contribution data is limited, so value concentration by rarity cannot be fully assessed.",
            label="Data limited",
            reason_code="no_rankings_data",
            severity="data_limited",
            confidence="low",
        )

    scored_rows = []
    for row in rankings:
        rarity = normalize_rarity_name(row.get("rarity_bucket"))
        total_value = _to_float(row.get("total_sampled_value"))
        pulled_count = _to_float(row.get("pulled_count")) or 0.0
        avg_sampled_value = _to_float(row.get("avg_sampled_value"))
        if total_value is None:
            continue
        scored_rows.append(
            {
                "rarity": rarity,
                "total_value": total_value,
                "pulled_count": pulled_count,
                "avg_sampled_value": avg_sampled_value,
            }
        )

    if not scored_rows:
        return SectionInterpretation(
            summary="Rarity contribution rows are present but do not contain consistent value totals.",
            label="Data limited",
            reason_code="no_valid_rarity_rows",
            severity="data_limited",
            confidence="low",
        )

    scored_rows.sort(key=lambda item: item["total_value"], reverse=True)
    lead = scored_rows[0]
    total_value = sum(row["total_value"] for row in scored_rows)

    if total_value <= 0:
        return SectionInterpretation(
            summary="Rarity contribution totals are near zero, so rarity-level impact remains inconclusive.",
            label="Data limited",
            reason_code="near_zero_totals",
            severity="data_limited",
            confidence="low",
        )

    lead_share = safe_percent_share(lead["total_value"], total_value) or 0.0
    top2_share = safe_percent_share(sum(row["total_value"] for row in scored_rows[:2]), total_value) or 0.0

    total_pulls = sum(row["pulled_count"] for row in scored_rows)
    pulls_sorted = sorted(scored_rows, key=lambda item: item["pulled_count"], reverse=True)
    pull_leader = pulls_sorted[0] if pulls_sorted else lead
    pull_leader_share = safe_percent_share(pull_leader["pulled_count"], total_pulls) or 0.0

    lead_is_frequent = lead["rarity"] == pull_leader["rarity"] and pull_leader_share >= 0.35
    lead_is_infrequent = lead["rarity"] != pull_leader["rarity"] and lead["pulled_count"] < pull_leader["pulled_count"]
    ev_pull_aligned = lead["rarity"] == pull_leader["rarity"]

    if lead_share >= TOP_RARITY_EV_CONCENTRATION_HIGH_MIN and lead_is_infrequent:
        summary = (
            "You will mostly pull lower-value cards, while most of the money comes from rarer hits. "
            "The set can feel cold until a meaningful hit lands."
        )
        label = "Value concentrated in rare pulls"
        reason_code = "ev_concentrated_infrequent"
        severity = "caution"
    elif lead_share >= TOP_RARITY_EV_CONCENTRATION_HIGH_MIN and lead_is_frequent:
        summary = (
            "The cards you pull most often also carry most of the value \u2014 that makes returns more accessible."
        )
        label = "Accessible value structure"
        reason_code = "ev_concentrated_frequent"
        severity = "positive"
    elif pull_leader_share >= 0.45 and _is_low_value_bucket(pull_leader["rarity"]) and not ev_pull_aligned:
        summary = (
            "You will mostly pull lower-value cards, while most of the money comes from rarer hits. "
            "Most packs will feel below cost until a hit from a higher rarity lands."
        )
        label = "Pulls don't match value"
        reason_code = "pull_freq_low_value_bucket"
        severity = "caution"
    elif top2_share < 0.75:
        summary = (
            "Several rarity groups help carry the value, which makes the set feel less dependent on one kind of hit."
        )
        label = "Broad rarity value base"
        reason_code = "broad_ev_spread"
        severity = "positive"
    else:
        summary = (
            "Value is mostly carried by one or two rarity tiers, but other buckets still contribute something meaningful."
        )
        label = "Moderate rarity spread"
        reason_code = "moderate_concentration"
        severity = "neutral"

    confidence = "high" if len(scored_rows) >= 3 and total_pulls > 0 else ("medium" if scored_rows else "low")

    evidence: List[EvidenceItem] = [
        EvidenceItem("EV-leading rarity", lead["rarity"].title()),
        EvidenceItem("EV-leading rarity share", format_percent(lead_share)),
        EvidenceItem("Pull-frequency-leading rarity", pull_leader["rarity"].title()),
        EvidenceItem("Pull leader share", format_percent(pull_leader_share)),
        EvidenceItem("Top 2 rarity EV share", format_percent(top2_share)),
        EvidenceItem("EV and pull aligned", "Yes" if ev_pull_aligned else "No"),
    ]

    return SectionInterpretation(
        summary=summary,
        label=label,
        reason_code=reason_code,
        severity=severity,
        confidence=confidence,
        evidence=evidence,
        signals={
            "lead_share": lead_share,
            "top2_share": top2_share,
            "pull_leader_share": pull_leader_share,
            "ev_pull_aligned": ev_pull_aligned,
            "lead_is_infrequent": lead_is_infrequent,
        },
    )
