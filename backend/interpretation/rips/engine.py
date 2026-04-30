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


def _section_to_dict(section: SectionInterpretation) -> Dict[str, Any]:
    """Serialize a SectionInterpretation (and its nested EvidenceItems) to a plain dict."""
    return dataclasses.asdict(section)


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
    adv_metrics = interpret_advanced_metrics(data)

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
