"""Top EV Drivers interpretation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import EvidenceItem, SectionInterpretation
from ..thresholds import (
    TOP_SHARE_HIGH_MIN,
    classify_share_concentration,
    format_percent,
    normalize_rarity_name,
    safe_percent_share,
)


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bucket_profile_label(rarity: str) -> str:
    """Internal classification — not exposed as-is to users."""
    if "special illustration rare" in rarity or "hyper" in rarity or "secret" in rarity:
        return "chase"
    if "illustration rare" in rarity:
        return "illustration"
    if "ultra rare" in rarity or rarity in {"ex", "double rare"}:
        return "premium"
    return "mixed"


def interpret_top_ev_drivers(data: Dict[str, Any]) -> SectionInterpretation:
    hits: List[Dict[str, Any]] = data.get("top_hits") or []

    if not hits:
        return SectionInterpretation(
            summary="Top EV driver data is limited, so contribution leadership is not currently resolved.",
            label="Data limited",
            reason_code="no_hits_data",
            severity="data_limited",
            confidence="low",
        )

    rows: List[Dict[str, Any]] = []
    for hit in hits:
        ev = _to_float(hit.get("ev_contribution"))
        if ev is None or ev < 0:
            continue
        rows.append(
            {
                "ev": ev,
                "card_name": str(hit.get("card_name") or ""),
                "rarity_bucket": normalize_rarity_name(hit.get("rarity_bucket")),
            }
        )

    if not rows:
        return SectionInterpretation(
            summary="Top EV drivers are present but contribution magnitudes are not reliably measurable from current data.",
            label="Data limited",
            reason_code="no_valid_ev_rows",
            severity="data_limited",
            confidence="low",
        )

    total = sum(row["ev"] for row in rows)
    top_share = safe_percent_share(rows[0]["ev"], total) or 0.0
    top3_share = safe_percent_share(sum(row["ev"] for row in rows[:3]), total) or 0.0
    top_share_level = classify_share_concentration(top_share)

    rarity_available = any(row["rarity_bucket"] != "unknown" for row in rows)
    rarity_totals: Dict[str, float] = {}
    for row in rows:
        rarity = row["rarity_bucket"]
        if rarity == "unknown":
            continue
        rarity_totals[rarity] = rarity_totals.get(rarity, 0.0) + row["ev"]

    lead_name = rows[0]["card_name"] if rows else ""
    lead_rarity = ""
    lead_rarity_share = 0.0
    rarity_diversity = 0
    profile = "mixed"

    if rarity_available and rarity_totals:
        ranked_rarities = sorted(rarity_totals.items(), key=lambda item: item[1], reverse=True)
        lead_rarity, lead_rarity_value = ranked_rarities[0]
        lead_rarity_share = safe_percent_share(lead_rarity_value, total) or 0.0
        rarity_diversity = len(ranked_rarities)
        profile = _bucket_profile_label(lead_rarity)

    concentration_risk = top_share >= 0.40

    # Choose user-facing label, summary, reason_code based on profile — no "premium-led" in output
    if profile == "chase" and lead_rarity_share >= 0.45:
        label = "Chase cards carry EV"
        summary = "Most of the value comes from the hardest cards to pull."
        reason_code = "chase_led"
        severity = "neutral"
    elif profile == "illustration" and lead_rarity_share >= 0.40:
        label = "Art rares support EV"
        summary = "Art rare cards provide a more accessible value base, reducing how much the set relies on the hardest-to-hit chase cards."
        reason_code = "illustration_led"
        severity = "positive"
    elif profile == "premium":
        label = "Mid-tier hits carry EV"
        summary = "A lot of the value comes from easier hits like ex, Ultra Rare, or Double Rare cards."
        reason_code = "mid_tier_led"
        severity = "neutral"
    elif rarity_available and rarity_diversity >= 3 and lead_rarity_share < 0.50 and top_share < TOP_SHARE_HIGH_MIN:
        label = "Value is spread out"
        summary = "Value comes from several types of cards, not just one chase card."
        reason_code = "broad_spread"
        severity = "positive"
    elif top_share_level == "high" and top3_share >= 0.70:
        label = "Concentrated in a few cards"
        summary = (
            f"A small number of cards carry most of the value \u2014 {lead_name} leads."
            " Hitting a specific card matters a lot here."
            if lead_name
            else "A small number of cards carry most of the value, so hitting a specific card matters a lot."
        )
        reason_code = "concentrated_few_cards"
        severity = "caution"
    else:
        label = "Value is spread out"
        summary = "Value comes from several types of cards, not just one chase card."
        reason_code = "broad_spread"
        severity = "positive"

    confidence = "high" if rarity_available and len(rows) >= 3 else ("medium" if rows else "low")

    evidence: List[EvidenceItem] = []
    if lead_name:
        evidence.append(EvidenceItem("Leading card", lead_name))
    evidence.append(EvidenceItem("Top card EV share", format_percent(top_share if rows else None)))
    evidence.append(EvidenceItem("Top 3 EV share", format_percent(top3_share if len(rows) >= 2 else None)))
    if lead_rarity:
        evidence.append(EvidenceItem("Leading value group", lead_rarity.title()))
        evidence.append(EvidenceItem("Leading group EV share", format_percent(lead_rarity_share)))
    if rarity_diversity:
        evidence.append(EvidenceItem("Rarity groups represented", str(rarity_diversity)))
    if concentration_risk:
        evidence.append(EvidenceItem("Read", "Top card is a concentration risk"))

    return SectionInterpretation(
        summary=summary,
        label=label,
        reason_code=reason_code,
        severity=severity,
        confidence=confidence,
        evidence=evidence,
        signals={
            "top_share": top_share,
            "top3_share": top3_share,
            "rarity_profile": profile,
            "lead_rarity": lead_rarity,
            "concentration_risk": concentration_risk,
        },
    )
