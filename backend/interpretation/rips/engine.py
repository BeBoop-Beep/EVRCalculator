"""RIP interpretation engine orchestrating pillar + synthesis layers."""

from __future__ import annotations

import dataclasses
from typing import Any, Dict

from .models import SectionInterpretation
from .pillars.profit import interpret_profit
from .pillars.safety import interpret_safety
from .pillars.stability import interpret_stability
from .sections.advanced_metrics import interpret_advanced_metrics
from .sections.historical_trend import interpret_historical_trend
from .sections.outcome_distribution import interpret_outcome_distribution
from .sections.pack_breakdown import interpret_pack_breakdown
from .sections.rarity_contribution import interpret_rarity_contribution
from .sections.top_ev_drivers import interpret_top_ev_drivers
from .synthesis.pack_score import interpret_pack_score
from .thresholds import get_summary_data, get_tier


def _section_to_dict(section: SectionInterpretation) -> Dict[str, Any]:
    """Serialize a SectionInterpretation (and its nested EvidenceItems) to a plain dict."""
    return dataclasses.asdict(section)


def _is_high_tier(tier: Any) -> bool:
    return str(tier or "").strip().upper() in {"S", "A"}


def _contains_word(value: str, needle: str) -> bool:
    return needle.lower() in (value or "").lower()


def _replace_punishing_label(section: SectionInterpretation, replacement: str) -> None:
    if _contains_word(section.label, "punishing"):
        section.label = replacement


def validate_interpretation_consistency(
    data: Dict[str, Any],
    pack_score: Any,
    profit: Any,
    safety: Any,
    stability: Any,
    advanced_metrics: SectionInterpretation,
) -> None:
    summary_data = get_summary_data(data)
    decision_category = None
    if pack_score.meta and isinstance(pack_score.meta.signals, dict):
        decision_category = pack_score.meta.signals.get("decision_category")

    profit_tier = get_tier(summary_data, "profit_tier")
    safety_tier = get_tier(summary_data, "safety_tier")
    stability_tier = get_tier(summary_data, "stability_tier")

    if safety.meta and _is_high_tier(safety_tier):
        if safety.meta.severity in {"negative", "caution"}:
            safety.meta.severity = "neutral"
        _replace_punishing_label(safety.meta, "Safer misses")

    if profit.meta and _is_high_tier(profit_tier) and profit.meta.severity in {"negative", "caution"}:
        profit.meta.severity = "neutral"

    if stability.meta and _is_high_tier(stability_tier) and stability.meta.severity in {"negative", "caution"}:
        if "better than most" not in stability.meta.summary.lower():
            stability.meta.summary = f"{stability.meta.summary} It is still better than most sets in this category."
        stability.meta.severity = "neutral"

    if decision_category in {"elite_open", "strong_but_risky"}:
        advanced_metrics.summary = (
            "The deeper numbers support the main read, with a catch: there is still downside risk in weaker packs."
            if advanced_metrics.severity in {"negative", "caution"}
            else advanced_metrics.summary
        )
        if advanced_metrics.severity == "negative":
            advanced_metrics.severity = "caution"

    if decision_category == "weak_open":
        for pillar in (profit.meta, safety.meta, stability.meta):
            if pillar and pillar.severity == "positive":
                pillar.severity = "neutral"
                pillar.summary = f"{pillar.summary} This helps, but it is not enough to offset the weak overall open profile."


def build_rip_interpretation(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the full RIP interpretation payload.

    Returns all existing string keys unchanged (backwards-compatible contract),
    plus a new ``meta`` key containing structured SectionInterpretation dicts
    for every section and pillar.
    """
    profit = interpret_profit(data)
    safety = interpret_safety(data)
    stability = interpret_stability(data)

    pack_score = interpret_pack_score(profit, safety, stability, data)

    outcome_dist = interpret_outcome_distribution(data)
    hist_trend = interpret_historical_trend(data)
    pack_bdown = interpret_pack_breakdown(data)
    top_ev = interpret_top_ev_drivers(data)
    rarity_contrib = interpret_rarity_contribution(data)
    adv_metrics = interpret_advanced_metrics(data, _section_to_dict(pack_score.meta) if pack_score.meta else None)
    validate_interpretation_consistency(data, pack_score, profit, safety, stability, adv_metrics)

    # Build meta — structured dicts for every section and pillar
    meta: Dict[str, Any] = {
        "packScore": _section_to_dict(pack_score.meta) if pack_score.meta else None,
        "profit": _section_to_dict(profit.meta) if profit.meta else None,
        "safety": _section_to_dict(safety.meta) if safety.meta else None,
        "stability": _section_to_dict(stability.meta) if stability.meta else None,
        "outcomeDistribution": _section_to_dict(outcome_dist),
        "historicalTrend": _section_to_dict(hist_trend),
        "packBreakdown": _section_to_dict(pack_bdown),
        "topEvDrivers": _section_to_dict(top_ev),
        "rarityContribution": _section_to_dict(rarity_contrib),
        "advancedMetrics": _section_to_dict(adv_metrics),
    }

    return {
        # Existing string keys — unchanged contract
        "packScore": pack_score.summary,
        "outcomeDistribution": outcome_dist.summary,
        "historicalTrend": hist_trend.summary,
        "packBreakdown": pack_bdown.summary,
        "topEvDrivers": top_ev.summary,
        "rarityContribution": rarity_contrib.summary,
        "advancedMetrics": adv_metrics.summary,
        # New structured metadata
        "meta": meta,
    }
