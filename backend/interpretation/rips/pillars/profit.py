"""Independent interpretation logic for the Profit pillar."""

from __future__ import annotations

from typing import Any, Dict

from ..models import EvidenceItem, ProfitInterpretation, SectionInterpretation
from ..thresholds import (
    build_profit_context,
    format_percent,
    format_ratio,
    get_numeric,
    get_summary_data,
)


def _probability_band(prob_profit: float | None) -> str:
    if prob_profit is None:
        return "unknown"
    if prob_profit < 0.06:
        return "very_low"
    if prob_profit < 0.10:
        return "low"
    if prob_profit < 0.14:
        return "moderate"
    return "strong"


def _classify_high_end_impact(p95_to_cost: float | None) -> str:
    if p95_to_cost is None:
        return "missing"
    if p95_to_cost < 1.00:
        return "no_payoff"
    if p95_to_cost < 1.25:
        return "barely_clears"
    if p95_to_cost < 1.75:
        return "modest"
    if p95_to_cost < 2.50:
        return "solid"
    if p95_to_cost < 3.50:
        return "strong"
    return "huge"


def _median_band(median_to_cost: float | None) -> str:
    if median_to_cost is None:
        return "unknown"
    if median_to_cost < 0.15:
        return "very_weak"
    if median_to_cost < 0.25:
        return "weak"
    return "holds_up"


def _mean_band(mean_to_cost: float | None) -> str:
    if mean_to_cost is None:
        return "unknown"
    if mean_to_cost >= 0.70:
        return "strong"
    if mean_to_cost >= 0.55:
        return "decent"
    return "weak"


def _profit_quality_phrase(tier: Any, strength: Any, prob_profit: float | None) -> str:
    tier_key = str(tier or "").strip().upper()
    tier_map = {
        "S": "This is one of the strongest profit profiles in the current data.",
        "A": "This is a strong profit profile compared to most sets.",
        "B": "This is an above-average profit profile.",
        "C": "This is a middle-of-the-pack profit profile.",
        "D": "This is a below-average profit profile.",
        "F": "This is a weak profit profile.",
    }
    if tier_key in tier_map:
        return tier_map[tier_key]

    try:
        strength_value = int(strength) if strength is not None else None
    except (TypeError, ValueError):
        strength_value = None

    if strength_value is None:
        return "This is a middle-of-the-pack profit profile."
    if strength_value >= 5:
        return tier_map["S"]
    if strength_value == 4:
        return tier_map["A"]
    if strength_value == 3:
        if prob_profit is not None and prob_profit >= 0.10:
            return tier_map["B"]
        return tier_map["C"]
    if strength_value == 2:
        return tier_map["D"]
    return tier_map["F"]


def _upside_phrase(p95_to_cost: float | None) -> str:
    if p95_to_cost is None:
        return ""
    if p95_to_cost >= 3.50:
        return "The high-end upside is huge when the right hits land."
    if p95_to_cost >= 2.50:
        return "The high-end upside is strong when the right hits land."
    if p95_to_cost >= 1.25:
        return "The better outcomes can clear cost with solid payoff, but they are not as explosive as the very best sets."
    if p95_to_cost >= 1.00:
        return "The better outcomes can clear cost, but only by a thin margin."
    return "Even the better outcomes are not clearing the pack price."


def _profit_why_phrase(
    profile: str,
    prob_profit: float | None,
    mean_to_cost: float | None,
    median_to_cost: float | None,
    p95_to_cost: float | None,
) -> str:
    if profile == "strong_average_capped_upside":
        return "Expected Value is doing most of the work, even though normal packs still come in below cost."
    if profile == "rare_wins_huge_upside":
        return "The score is carried by big-hit potential, not by normal packs."
    if profile == "rare_wins_good_upside":
        return "The score is helped by strong hits, even though profitable packs are not common."
    if profile == "decent_chance_modest_upside":
        return "The score holds up because the win chance is better than many sets."
    if profile == "weak_chance_weak_upside":
        return "The score is weak because wins are rare and the better outcomes do not pay back enough."
    if profile == "low_impact_profit_profile":
        return "High-end payoff is weak at the current pack price."
    if profile == "weak_normal_packs_big_hits":
        return "The score depends on the better hits, because normal packs are weak."
    if profile == "average_return_mixed":
        return "The score lands in the middle because no single profit signal clearly stands out."
    if profile == "strong_chance_strong_upside":
        return "The score is strong because both win rate and upside are better than most sets."
    if profile == "steady_but_capped":
        return "The score comes from a better chance to win, even though big wins are limited."
    if profile == "data_limited":
        return ""

    # Fallback keeps copy concise while still explaining the grade driver.
    if prob_profit is not None and prob_profit >= 0.10:
        return "The score holds up because the win chance is better than many sets."
    if p95_to_cost is not None and p95_to_cost >= 2.50:
        return "The score is carried more by upside than by normal packs."
    if mean_to_cost is not None and mean_to_cost >= 0.70:
        return "Expected Value is doing most of the work in this score."
    if median_to_cost is not None and median_to_cost < 0.25:
        return "Normal packs are still below cost often enough to cap the score."
    return "The score lands in the middle because no single profit signal clearly stands out."


def _profile_summary_and_label(
    *,
    prob_profit: float | None,
    p95_to_cost: float | None,
    median_to_cost: float | None,
    mean_to_cost: float | None,
    tier: Any,
    strength: Any,
) -> tuple[str, str, str]:
    if prob_profit is None or p95_to_cost is None:
        return (
            "data_limited",
            "Profit profile unclear",
            "There is not enough data to judge how often packs profit or how big the better wins can be.",
        )

    tier_key = str(tier or "").strip().upper()
    try:
        strength_value = int(strength) if strength is not None else None
    except (TypeError, ValueError):
        strength_value = None
    high_tier_read = tier_key in {"S", "A", "B"} or (strength_value is not None and strength_value >= 3)

    if p95_to_cost < 1.00:
        if high_tier_read:
            return (
                "low_impact_profit_profile",
                "Low payoff ceiling",
                "The score has support from other metrics, but high-end payoff is weak because even better outcomes struggle to clear the pack price.",
            )
        return (
            "low_impact_profit_profile",
            "Low payoff ceiling",
            "This is a weak value-rip signal because even better outcomes are not clearing the pack price.",
        )

    if prob_profit >= 0.14 and p95_to_cost >= 2.50:
        return (
            "strong_chance_strong_upside",
            "Strong profit profile",
            "This set has one of the better profit profiles because it combines a better chance to win with strong high-end hits.",
        )

    if prob_profit < 0.14 and p95_to_cost >= 3.50:
        return (
            "rare_wins_huge_upside",
            "Rare wins, huge upside",
            "Most packs will not profit, but the best hits can pay back several times the pack price.",
        )

    if prob_profit < 0.14 and p95_to_cost >= 2.50:
        return (
            "rare_wins_good_upside",
            "Rare wins, strong upside",
            "Profitable packs are not common, but strong hits can still make the return attractive.",
        )

    if prob_profit >= 0.14 and p95_to_cost < 1.75:
        return (
            "steady_but_capped",
            "Better chance, capped upside",
            "This set gives you a better shot at profit, but the bigger wins are more limited.",
        )

    if prob_profit >= 0.10 and 1.75 <= p95_to_cost < 2.50:
        return (
            "decent_chance_modest_upside",
            "Decent chance, modest upside",
            "This set has a decent chance to return value, but the high-end wins are not as strong as the best sets.",
        )

    if mean_to_cost is not None and mean_to_cost >= 0.70 and p95_to_cost < 1.75 and prob_profit < 0.14:
        return (
            "strong_average_capped_upside",
            "Strong average, capped upside",
            "Average value is strong, but the biggest wins are more limited than the top upside sets.",
        )

    if median_to_cost is not None and median_to_cost < 0.20 and p95_to_cost >= 2.50:
        return (
            "weak_normal_packs_big_hits",
            "Weak normal packs, big hits",
            "Normal packs are weak, but the better hits are strong enough to keep profit interesting.",
        )

    if prob_profit < 0.10 and p95_to_cost < 1.25:
        return (
            "weak_chance_weak_upside",
            "Weak profit profile",
            "Profitable packs are rare, and even the stronger outcomes are not paying back enough.",
        )

    return (
        "average_return_mixed",
        "Mixed profit profile",
        "This set has some return potential, but neither the win chance nor the high-end upside clearly stands out.",
    )


def interpret_profit(data: Dict[str, Any]) -> ProfitInterpretation:
    summary_data = get_summary_data(data)
    context = build_profit_context(summary_data)

    score = context["score"]
    tier = context["tier"]
    strength = context["strength"]
    prob_profit = get_numeric(summary_data, "prob_profit")
    mean_to_cost = get_numeric(summary_data, "mean_value_to_cost_ratio")
    median_to_cost = get_numeric(summary_data, "median_value_to_cost_ratio")
    p95_to_cost = get_numeric(summary_data, "p95_value_to_cost_ratio")

    probability_band = _probability_band(prob_profit)
    impact_band = _classify_high_end_impact(p95_to_cost)
    median_band = _median_band(median_to_cost)
    mean_band = _mean_band(mean_to_cost)

    profit_profile, label, base_summary = _profile_summary_and_label(
        prob_profit=prob_profit,
        p95_to_cost=p95_to_cost,
        median_to_cost=median_to_cost,
        mean_to_cost=mean_to_cost,
        tier=tier,
        strength=strength,
    )

    quality_phrase = _profit_quality_phrase(tier=tier, strength=strength, prob_profit=prob_profit)
    upside_phrase = _upside_phrase(p95_to_cost)
    why_phrase = _profit_why_phrase(
        profile=profit_profile,
        prob_profit=prob_profit,
        mean_to_cost=mean_to_cost,
        median_to_cost=median_to_cost,
        p95_to_cost=p95_to_cost,
    )

    summary = " ".join([part for part in [quality_phrase, upside_phrase, why_phrase] if part]).strip()
    if profit_profile == "low_impact_profit_profile" and base_summary:
        summary = base_summary
    reason_code = profit_profile

    if profit_profile == "data_limited":
        severity = "data_limited"
    elif strength is not None and strength >= 4:
        severity = "positive"
    elif strength is not None and strength <= 1:
        severity = "negative"
    else:
        severity = "neutral"

    confidence: str
    if score is not None and prob_profit is not None and p95_to_cost is not None:
        confidence = "high"
    elif score is not None:
        confidence = "medium"
    else:
        confidence = "low"

    evidence = [
        EvidenceItem("Chance to profit", format_percent(prob_profit)),
        EvidenceItem("High-end upside vs cost", format_ratio(p95_to_cost)),
        EvidenceItem("Average pack return", format_ratio(mean_to_cost)),
        EvidenceItem("Typical pack return", format_ratio(median_to_cost)),
    ]

    signals: Dict[str, Any] = {
        "profit_profile": profit_profile,
        "probability_band": probability_band,
        "impact_band": impact_band,
        "high_end_impact_band": impact_band,
        "median_band": median_band,
        "mean_band": mean_band,
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

    return ProfitInterpretation(
        summary=summary,
        signals=signals,  # type: ignore[arg-type]
        score=score,
        meta=meta,
    )
