"""Top EV Drivers interpretation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import EvidenceItem, SectionInterpretation
from ..thresholds import (
    format_rarity_label,
    format_percent,
    normalize_rarity_name,
    safe_percent_share,
)


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_low_rarity(rarity: str) -> bool:
    return rarity in {"common", "uncommon", "rare", "regular reverse", "reverse holo"}


def _classify_leading_rarity(rarity: str) -> str:
    if rarity == "illustration rare":
        return "illustration_led"
    if rarity == "special illustration rare":
        return "sir_led"
    if rarity in {"ultra rare", "ex"}:
        return "ex_ultra_led"
    if rarity == "double rare":
        return "double_rare_led"
    if rarity == "hyper rare":
        return "hyper_led"
    if rarity == "ace spec rare":
        return "ace_spec_led"
    if "secret" in rarity:
        return "chase_led"
    if _is_low_rarity(rarity):
        return "low_rarity_led"
    return "mixed_hit_base"


def _top3_leading_rarity(rows: List[Dict[str, Any]], n: int = 3) -> tuple[str, int, str]:
    """Return (lead_rarity, lead_count, lead_profile) for the top n rows by EV."""
    top_rows = rows[:n]
    totals: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for row in top_rows:
        rarity = row["rarity_bucket"]
        if rarity == "unknown":
            continue
        totals[rarity] = totals.get(rarity, 0.0) + row["ev"]
        counts[rarity] = counts.get(rarity, 0) + 1
    if not totals:
        return "", 0, "data_limited"
    lead_rarity = max(totals, key=totals.__getitem__)
    return lead_rarity, counts[lead_rarity], _classify_leading_rarity(lead_rarity)


_TOP3_PROFILE_MAP: Dict[str, str] = {
    "sir_led": "sir_led_top3",
    "illustration_led": "ir_led_top3",
    "ex_ultra_led": "ex_ultra_led_top3",
}


def _reason_to_copy(reason_code: str, leading_label: str, *, strong: bool) -> tuple[str, str, str]:
    # ── Tier 0: single-card heavy ─────────────────────────────────────────
    if reason_code == "single_card_dependent":
        return (
            "One card carries value",
            "One card carries a huge share of the value, so this set depends heavily on landing that card.",
            "caution",
        )

    # ── Tier 1: top-card led (clear leader gap) ───────────────────────────
    if reason_code == "top_card_led":
        return (
            "Top card leads value",
            "The top card is well ahead of the next card, so this set leans heavily on that top hit "
            "even though other cards still add value.",
            "caution",
        )

    # ── Tier 2a: top-three carry value ────────────────────────────────────
    if reason_code == "top_three_carry_value":
        return (
            "Top cards carry value",
            "The top three cards carry a large share of the value, so this set depends heavily on "
            "landing one of the best hits.",
            "caution",
        )

    # ── Tier 2b: top-five carry value ─────────────────────────────────────
    if reason_code == "top_five_carry_value":
        return (
            "Top five carry value",
            "The top five cards carry much of the value, so this set is still driven by a small "
            "group of key hits.",
            "caution",
        )

    # ── Tier 2c: top-three concentration, rarity-specific ─────────────────
    if reason_code == "sir_led_top3":
        return (
            "Special Illustration Rares drive value",
            "A small group of Special Illustration Rares carries a large share of the value, "
            "so this set depends heavily on landing the right high-end hits.",
            "caution",
        )

    if reason_code == "ir_led_top3":
        return (
            "Illustration Rares drive value",
            "A small group of Illustration Rares carries a large share of the value, "
            "so these art cards are doing most of the work.",
            "positive",
        )

    if reason_code == "ex_ultra_led_top3":
        return (
            "ex and Ultra Rares drive value",
            "A small group of ex or Ultra Rare cards carries a large share of the value, "
            "so the set depends on landing those stronger hits.",
            "positive",
        )

    # Legacy alias kept for backward compat
    if reason_code == "top_cards_carry_value":
        return (
            "Top cards carry value",
            "A small group of cards carries a large share of the value, "
            "so this profile depends heavily on landing one of them.",
            "caution",
        )

    # ── Tier 3: dominant rarity / full-pool rarity share ─────────────────
    if reason_code == "illustration_led":
        label = "Illustration Rares lead value"
        summary = (
            "Illustration Rares are doing most of the work here, but the value is spread across "
            "several of them instead of one single card."
        )
        return label, summary, "positive"

    if reason_code == "sir_led":
        label = "Special Illustration Rares lead value"
        summary = "Special Illustration Rares are the main value driver, so the set leans on harder-to-pull chase cards."
        return label, summary, "caution"

    if reason_code == "chase_led":
        label = "Chase cards lead value"
        summary = "Most of the value comes from top-end chase cards, so outcomes lean heavily on high-end hits."
        return label, summary, "caution"

    if reason_code == "ex_ultra_led":
        label = "ex and Ultra Rares help carry value"
        summary = (
            "A lot of the value comes from ex and Ultra Rare cards, "
            "making the set less dependent on only the rarest pulls."
        )
        return label, summary, "positive"

    if reason_code == "double_rare_led":
        label = "Double Rares carry value"
        summary = "Double Rares are doing more of the work than usual, giving the set value from more accessible hits."
        return label, summary, "positive"

    if reason_code == "hyper_led":
        label = "Hyper Rares carry value"
        summary = "Hyper Rares are a major value driver, so the set leans on rarer high-end pulls."
        return label, summary, "caution"

    if reason_code == "ace_spec_led":
        label = "Ace Spec cards carry value"
        summary = "Ace Spec cards are the main value driver, with supporting value from other hit types."
        return label, summary, "neutral"

    if reason_code == "low_rarity_led":
        label = "Low rarities carry value"
        summary = "Lower-rarity cards are doing more value work than usual, so returns are less tied to elite chase hits."
        return label, summary, "positive"

    if reason_code == "broad_value_base":
        return (
            "Value is spread out",
            "Value is spread across many cards and rarities, which lowers dependence on one perfect pull.",
            "positive",
        )

    if strong:
        return (
            f"{leading_label}s lead value" if not leading_label.endswith("s") else f"{leading_label} lead value",
            f"{leading_label}s are the clear value leader, with support from other rarities behind them.",
            "neutral",
        )

    return (
        "Several hit types help",
        "Value is shared across multiple hit types, so the set is not relying on only one rarity group.",
        "neutral",
    )


def interpret_top_ev_drivers(data: Dict[str, Any]) -> SectionInterpretation:
    hits: List[Dict[str, Any]] = data.get("top_hits") or []
    rankings: List[Dict[str, Any]] = data.get("rankings") or []

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

    rows.sort(key=lambda item: item["ev"], reverse=True)

    total = sum(row["ev"] for row in rows)
    top_share = safe_percent_share(rows[0]["ev"], total) or 0.0
    top3_share = safe_percent_share(sum(row["ev"] for row in rows[:3]), total) or 0.0
    top5_share = safe_percent_share(sum(row["ev"] for row in rows[:5]), total) or 0.0

    # Leader-gap ratio: how far ahead is the top card vs the second card
    top_card_ev = rows[0]["ev"] if rows else 0.0
    second_card_ev = rows[1]["ev"] if len(rows) >= 2 else None
    top_card_to_second_ratio: Optional[float] = None
    if second_card_ev is not None and second_card_ev > 0:
        top_card_to_second_ratio = top_card_ev / second_card_ev

    rarity_available = any(row["rarity_bucket"] != "unknown" for row in rows)
    rarity_source = "top_hits"
    rarity_totals: Dict[str, float] = {}
    rarity_counts: Dict[str, int] = {}
    for row in rows:
        rarity = row["rarity_bucket"]
        if rarity == "unknown":
            continue
        rarity_totals[rarity] = rarity_totals.get(rarity, 0.0) + row["ev"]
        rarity_counts[rarity] = rarity_counts.get(rarity, 0) + 1

    if not rarity_totals and rankings:
        for ranking in rankings:
            rarity = normalize_rarity_name(
                ranking.get("rarity_bucket") or ranking.get("rarity") or ranking.get("card_rarity")
            )
            value = _to_float(ranking.get("total_sampled_value"))
            if rarity == "unknown" or value is None or value <= 0:
                continue
            rarity_totals[rarity] = rarity_totals.get(rarity, 0.0) + value

        if rarity_totals:
            rarity_available = True
            rarity_source = "rankings"

    lead_name = rows[0]["card_name"] if rows else ""
    lead_rarity = ""
    lead_rarity_share = 0.0
    rarity_diversity = 0
    profile = "data_limited"
    lead_rarity_count = 0

    if rarity_available and rarity_totals:
        ranked_rarities = sorted(rarity_totals.items(), key=lambda item: item[1], reverse=True)
        lead_rarity, lead_rarity_value = ranked_rarities[0]
        lead_denom = total if rarity_source == "top_hits" else sum(rarity_totals.values())
        lead_rarity_share = safe_percent_share(lead_rarity_value, lead_denom) or 0.0
        lead_rarity_count = rarity_counts.get(lead_rarity, 0)
        rarity_diversity = len(ranked_rarities)
        profile = _classify_leading_rarity(lead_rarity)

    # Pull full-pool top shares from summary when available; fall back to within-hits shares
    summary_data = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    effective_top_share = _to_float((summary_data or {}).get("top1_ev_share"))
    if effective_top_share is None:
        effective_top_share = top_share
    effective_top3_share = _to_float((summary_data or {}).get("top3_ev_share"))
    if effective_top3_share is None:
        effective_top3_share = top3_share
    effective_top5_share = _to_float((summary_data or {}).get("top5_ev_share"))
    if effective_top5_share is None:
        effective_top5_share = top5_share

    # Detect dominant rarity in top 3 cards for concentration-first copy
    top3_lead_rarity, top3_lead_count, top3_lead_profile = _top3_leading_rarity(rows)

    concentration_risk = effective_top_share >= 0.25

    # ── Decision priority ─────────────────────────────────────────────────
    # 1. One-card dependent: extreme top-card concentration (full-pool share)
    if effective_top_share >= 0.40:
        reason_code = "single_card_dependent"
    # 2. Top-card led: clear leader gap — use within-hits share since the ratio
    #    is also computed from within-hits data; effective_top_share from the full
    #    pool dilutes the signal with commons/uncommons.
    elif top_share >= 0.25 and top_card_to_second_ratio is not None and top_card_to_second_ratio >= 1.75:
        reason_code = "top_card_led"
    # 3. Top-three heavy (strong threshold)
    elif effective_top3_share >= 0.50:
        if top3_lead_count >= 2 and top3_lead_profile not in ("mixed_hit_base", "data_limited"):
            reason_code = _TOP3_PROFILE_MAP.get(top3_lead_profile, "top_three_carry_value")
        else:
            reason_code = "top_three_carry_value"
    # 4. Top-five heavy
    elif effective_top5_share >= 0.65:
        reason_code = "top_five_carry_value"
    # 5. Top-three moderate concentration
    elif effective_top3_share >= 0.45:
        if top3_lead_count >= 2 and top3_lead_profile not in ("mixed_hit_base", "data_limited"):
            reason_code = _TOP3_PROFILE_MAP.get(top3_lead_profile, "top_three_carry_value")
        else:
            reason_code = "top_three_carry_value"
    # 6. Dominant rarity across full hit pool
    elif lead_rarity_share >= 0.35:
        reason_code = profile
    # 7. Broad — only when ALL concentration signals are low
    elif (
        effective_top_share < 0.20
        and effective_top3_share < 0.40
        and effective_top5_share < 0.60
        and lead_rarity_share < 0.35
        and rarity_diversity >= 4
    ):
        reason_code = "broad_value_base"
    else:
        reason_code = "mixed_hit_base"

    lead_label = format_rarity_label(lead_rarity)
    label, summary, severity = _reason_to_copy(
        reason_code,
        lead_label,
        strong=lead_rarity_share >= 0.45,
    )

    # Inject card name into single-card and top-card-led summaries
    if reason_code == "single_card_dependent" and lead_name:
        summary = f"{lead_name} carries a huge share of the value, so this set depends heavily on landing that card."
    if reason_code == "top_card_led" and lead_name:
        summary = (
            f"{lead_name} is well ahead of the next card, so this set leans heavily on that top hit "
            "even though other cards still add value."
        )

    if reason_code == "mixed_hit_base" and lead_rarity_share >= 0.35 and lead_label != "Unknown":
        label = f"{lead_label}s lead value" if not lead_label.endswith("s") else f"{lead_label} lead value"
        summary = f"{lead_label}s do the most work, with support from other hit types behind them."

    confidence = "high" if rarity_available and len(rows) >= 3 else ("medium" if rows else "low")

    evidence: List[EvidenceItem] = []
    if lead_name:
        evidence.append(EvidenceItem("Leading card", lead_name))
    evidence.append(EvidenceItem("Top card EV share", format_percent(effective_top_share if rows else None)))
    evidence.append(EvidenceItem("Top 3 EV share", format_percent(effective_top3_share if len(rows) >= 2 else None)))
    if len(rows) >= 5:
        evidence.append(EvidenceItem("Top 5 EV share", format_percent(effective_top5_share)))
    if top_card_to_second_ratio is not None:
        evidence.append(EvidenceItem("Lead over next card", f"{top_card_to_second_ratio:.1f}x"))
    if lead_rarity:
        evidence.append(EvidenceItem("Leading value type", format_rarity_label(lead_rarity)))

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
            "top5_share": top5_share,
            "effective_top_share": effective_top_share,
            "effective_top3_share": effective_top3_share,
            "effective_top5_share": effective_top5_share,
            "top_card_to_second_ratio": top_card_to_second_ratio,
            "top3_lead_rarity": top3_lead_rarity,
            "top3_lead_count": top3_lead_count,
            "rarity_source": rarity_source,
            "leading_rarity": lead_rarity,
            "leading_rarity_ev_share": lead_rarity_share,
            "leading_rarity_card_count": lead_rarity_count,
            "rarity_diversity": rarity_diversity,
            "concentration_risk": concentration_risk,
        },
    )
