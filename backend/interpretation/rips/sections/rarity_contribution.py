"""Rarity Contribution interpretation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import EvidenceItem, SectionInterpretation
from ..thresholds import format_percent, format_rarity_label, normalize_rarity_name, safe_percent_share


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_low_value_bucket(rarity: str) -> bool:
    rarity_l = rarity.lower()
    return any(token in rarity_l for token in ("common", "uncommon", "reverse", "regular", "normal", "holo"))


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
    if _is_low_value_bucket(rarity):
        return "low_rarity_led"
    return "mixed_hit_base"


def _to_plural_label(label: str) -> str:
    if label.endswith("s"):
        return label
    return f"{label}s"


def _dominant_copy(reason_code: str, rarity_label: str, *, strong: bool) -> tuple[str, str, str]:
    rarity_plural = _to_plural_label(rarity_label)

    if reason_code == "illustration_led":
        if strong:
            return (
                "Illustration Rares carry the pool",
                "Illustration Rares make up the biggest share of value, while other rarities add support behind them.",
                "positive",
            )
        return (
            "Illustration Rares lead the pool",
            "Illustration Rares contribute the largest value share, with support from other rarity groups.",
            "positive",
        )

    if reason_code == "sir_led":
        if strong:
            return (
                "Special Illustration Rares carry the pool",
                "Most of the value pool is driven by hard-to-pull Special Illustration Rares.",
                "caution",
            )
        return (
            "Special Illustration Rares lead the pool",
            "Special Illustration Rares contribute the largest value share, with other rarities adding support behind them.",
            "caution",
        )

    if reason_code == "ex_ultra_led":
        return (
            "ex and Ultra Rares carry the pool",
            "A large share of value comes from ex and Ultra Rares, so value is not only tied to the rarest cards.",
            "positive",
        )

    if reason_code == "double_rare_led":
        return (
            "Double Rares carry the pool",
            "Double Rares are a major part of the value pool, giving this set more support from accessible hits.",
            "positive",
        )

    if reason_code == "hyper_led":
        return (
            "Hyper Rares carry the pool",
            "Hyper Rares contribute the largest share of value, so outcomes lean on rarer high-end pulls.",
            "caution",
        )

    if reason_code == "ace_spec_led":
        return (
            "Ace Spec cards carry the pool",
            "Ace Spec cards contribute the largest share of value, with other rarities adding support.",
            "neutral",
        )

    if reason_code == "low_rarity_led":
        return (
            "Low rarities carry the pool",
            "Lower-rarity cards contribute the largest share of value, making returns less dependent on elite chase pulls.",
            "positive",
        )

    if reason_code == "chase_led":
        return (
            "Chase cards carry the pool",
            "High-end chase rarities make up most of the value pool, so outcomes depend on premium hits.",
            "caution",
        )

    return (
        f"{rarity_plural} carry the pool",
        f"{rarity_plural} make up the largest share of the value pool, with support from other rarities.",
        "neutral",
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
        rarity = normalize_rarity_name(row.get("rarity_bucket") or row.get("rarity") or row.get("card_rarity"))
        total_value = _to_float(row.get("total_sampled_value"))
        pulled_count = _to_float(row.get("pulled_count")) or 0.0
        avg_sampled_value = _to_float(row.get("avg_sampled_value"))
        if total_value is None or rarity == "unknown":
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
    rarity_diversity = len(scored_rows)
    ev_leader_rarity = lead["rarity"]
    ev_leader_reason = _classify_leading_rarity(ev_leader_rarity)

    total_pulls = sum(row["pulled_count"] for row in scored_rows)
    pulls_sorted = sorted(scored_rows, key=lambda item: item["pulled_count"], reverse=True)
    pull_leader = pulls_sorted[0] if pulls_sorted else lead
    pull_leader_share = safe_percent_share(pull_leader["pulled_count"], total_pulls) or 0.0

    lead_is_frequent = lead["rarity"] == pull_leader["rarity"] and pull_leader_share >= 0.35
    lead_is_infrequent = lead["rarity"] != pull_leader["rarity"] and lead["pulled_count"] < pull_leader["pulled_count"]
    ev_pull_aligned = lead["rarity"] == pull_leader["rarity"]

    ev_leader_high_value = not _is_low_value_bucket(ev_leader_rarity)
    pull_leader_low_value = _is_low_value_bucket(pull_leader["rarity"])
    pull_value_mismatch = pull_leader_low_value and ev_leader_high_value and not ev_pull_aligned

    if lead_share >= 0.45:
        reason_code = ev_leader_reason
        label, summary, severity = _dominant_copy(reason_code, format_rarity_label(ev_leader_rarity), strong=True)
    elif lead_share >= 0.35:
        reason_code = ev_leader_reason
        label, summary, severity = _dominant_copy(reason_code, format_rarity_label(ev_leader_rarity), strong=False)
    elif top2_share >= 0.70:
        reason_code = "mixed_hit_base"
        label = "Two rarity groups carry most value"
        summary = "Most of the value pool comes from two rarity groups, with lighter support from the rest."
        severity = "neutral"
    elif rarity_diversity >= 5 and lead_share < 0.35:
        reason_code = "broad_value_base"
        label = "Value is spread out"
        summary = "Value is spread across many rarity groups, which lowers dependence on one exact hit type."
        severity = "positive"
    else:
        reason_code = "mixed_hit_base"
        label = "Several hit types help"
        summary = "Value is shared across multiple hit types, so the set is not relying on only one rarity group."
        severity = "neutral"

    if pull_value_mismatch:
        ev_label = format_rarity_label(ev_leader_rarity)
        summary = (
            f"{summary} You will mostly pull lower-value cards, but most of the money comes from {ev_label}s."
            if not summary.endswith(".")
            else f"{summary} You will mostly pull lower-value cards, but most of the money comes from {ev_label}s."
        )

    if lead_share >= 0.35:
        blocked_phrases = ("several rarity groups", "broad rarity value base")
        if any(phrase in summary.lower() for phrase in blocked_phrases):
            summary = f"{format_rarity_label(ev_leader_rarity)}s make up the largest value share, with support from other rarities."
            label = f"{format_rarity_label(ev_leader_rarity)}s carry the pool"

    confidence = "high" if len(scored_rows) >= 3 and total_pulls > 0 else ("medium" if scored_rows else "low")

    evidence: List[EvidenceItem] = [
        EvidenceItem("EV-leading rarity", format_rarity_label(lead["rarity"])),
        EvidenceItem("EV-leading rarity share", format_percent(lead_share)),
        EvidenceItem("Most common pull type", format_rarity_label(pull_leader["rarity"])),
        EvidenceItem("Most common pull type share", format_percent(pull_leader_share)),
        EvidenceItem("Top two rarity share", format_percent(top2_share)),
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
            "ev_leader_rarity": ev_leader_rarity,
            "ev_leader_share": lead_share,
            "top2_ev_share": top2_share,
            "pull_leader_rarity": pull_leader["rarity"],
            "pull_leader_share": pull_leader_share,
            "rarity_diversity": rarity_diversity,
            "ev_pull_aligned": ev_pull_aligned,
            "lead_is_frequent": lead_is_frequent,
            "lead_is_infrequent": lead_is_infrequent,
            "pull_value_mismatch": pull_value_mismatch,
        },
    )
