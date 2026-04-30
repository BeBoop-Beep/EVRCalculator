"""Pack Score synthesis from independent pillar interpretations."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ..models import (
    EvidenceItem,
    PackScoreInterpretation,
    ProfitInterpretation,
    SafetyInterpretation,
    SectionInterpretation,
    StabilityInterpretation,
)
from ..thresholds import IMBALANCE_GAP_POINTS, classify_score_strength, format_score, get_numeric


def _pillar_scores(
    profit: ProfitInterpretation,
    safety: SafetyInterpretation,
    stability: StabilityInterpretation,
    data: Dict[str, Any],
) -> Dict[str, Optional[float]]:
    summary_data = data.get("summary") if isinstance(data.get("summary"), dict) else data
    return {
        "profit": profit.score if profit.score is not None else get_numeric(summary_data, "profit_score"),
        "safety": safety.score if safety.score is not None else get_numeric(summary_data, "safety_score"),
        "stability": stability.score if stability.score is not None else get_numeric(summary_data, "stability_score"),
    }


def _strongest_weakest(scores: Dict[str, Optional[float]]) -> Tuple[str, str]:
    scored = [(pillar, score) for pillar, score in scores.items() if score is not None]
    if not scored:
        return ("profit", "safety")
    strongest = max(scored, key=lambda row: row[1])[0]
    weakest_candidates = sorted(scored, key=lambda row: row[1])
    weakest = weakest_candidates[0][0]
    if weakest == strongest and len(weakest_candidates) > 1:
        weakest = weakest_candidates[1][0]
    return strongest, weakest


def interpret_pack_score(
    profit: ProfitInterpretation,
    safety: SafetyInterpretation,
    stability: StabilityInterpretation,
    data: Dict[str, Any] | None = None,
) -> PackScoreInterpretation:
    payload = data or {}
    scores = _pillar_scores(profit, safety, stability, payload)

    strengths = {
        "profit": classify_score_strength(scores["profit"]),
        "safety": classify_score_strength(scores["safety"]),
        "stability": classify_score_strength(scores["stability"]),
    }

    strongest, weakest = _strongest_weakest(scores)

    numeric_scores = [s for s in scores.values() if s is not None]
    imbalance = False
    if len(numeric_scores) >= 2:
        imbalance = (max(numeric_scores) - min(numeric_scores)) >= IMBALANCE_GAP_POINTS

    unique_strengths = set(strengths.values())
    if unique_strengths == {"high"}:
        alignment = "all_strong"
    elif unique_strengths == {"low"}:
        alignment = "all_weak"
    elif len(unique_strengths) == 1:
        alignment = "uniform_mid"
    else:
        alignment = "mixed"

    summary_data = payload.get("summary") if isinstance(payload.get("summary"), dict) else payload
    pack_score_val = get_numeric(summary_data, "pack_score", "relative_pack_score")
    pack_tier = summary_data.get("pack_tier") or summary_data.get("tier")
    pack_rank = summary_data.get("pack_rank")

    profit_high = strengths["profit"] == "high"
    safety_high = strengths["safety"] == "high"
    stability_high = strengths["stability"] == "high"
    profit_low = strengths["profit"] == "low"
    safety_low = strengths["safety"] == "low"
    stability_low = strengths["stability"] == "low"

    profit_tail_driven = (
        profit.signals.get("upside_strength") == "high"
        and profit.signals.get("profit_frequency") in {"low", "medium"}
    )
    # Safety signals use downside_pressure (high = more pressure = worse safety)
    safety_tail_pressure = safety.signals.get("downside_pressure") == "high"
    stability_constrained = (
        stability.signals.get("volatility") == "high"
        or stability.signals.get("concentration") == "high"
    )

    if alignment == "all_strong":
        summary = "This is one of the better sets to rip: it has good upside, less painful misses, and value spread across multiple cards."
        label = "Strong across the board"
        reason_code = "all_strong"
        severity = "positive"
    elif alignment == "all_weak":
        summary = "This is a rough set to rip: the wins are limited, the misses hurt, and the value is not spread out well."
        label = "Weak across the board"
        reason_code = "all_weak"
        severity = "negative"
    elif profit_high and safety_low and strongest == "profit" and weakest == "safety":
        summary = "This set has big wins available, but most losing packs still hurt."
        label = "Strong upside, weak safety"
        reason_code = "profit_strong_safety_weak"
        severity = "caution"
    elif profit_high and stability_low and strongest == "profit" and weakest == "stability":
        summary = "Strong wins are possible, but the results swing a lot — too much value depends on hitting one specific card."
        label = "Strong upside, unstable returns"
        reason_code = "profit_strong_stability_weak"
        severity = "caution"
    elif stability_high and profit_low and strongest == "stability" and weakest == "profit":
        summary = "This set is predictable, but the rewards are not strong enough to make ripping exciting."
        label = "Stable but underwhelming"
        reason_code = "stability_strong_profit_weak"
        severity = "neutral"
    elif safety_high and profit_low and strongest == "safety" and weakest == "profit":
        summary = "Losing packs are not as painful as most risky sets, but the best hits are not strong enough to stand out."
        label = "Safe but low-upside"
        reason_code = "safety_strong_profit_weak"
        severity = "neutral"
    elif profit_high and safety_low and (profit_tail_driven or safety_tail_pressure):
        summary = "This set can pay off, but the wins are not easy to hit, and losing packs still give back very little."
        label = "High upside, real loss risk"
        reason_code = "high_upside_downside_pressure"
        severity = "caution"
    elif profit_high and stability_low and stability_constrained:
        summary = "The numbers can look good, but the wins are not easy to hit — results swing a lot."
        label = "Good upside, uneven delivery"
        reason_code = "profit_high_stability_constrained"
        severity = "caution"
    elif profit_low and safety_high:
        summary = "Losing packs are not too painful here, but the upside is not enough to make this set exciting to rip."
        label = "Controlled losses, limited upside"
        reason_code = "low_profit_safe"
        severity = "neutral"
    elif stability_high and profit_low:
        summary = "This set rips consistently, but consistent does not mean profitable — the rewards just are not there."
        label = "Consistent but not rewarding"
        reason_code = "stable_low_profit"
        severity = "neutral"
    elif alignment == "uniform_mid":
        summary = "This set is average across the board — nothing stands out as great or terrible."
        label = "Balanced mid-range"
        reason_code = "uniform_mid"
        severity = "neutral"
    elif weakest == "safety":
        summary = f"This set scores well on {strongest}, but the worst packs give back very little."
        label = f"Led by {strongest}, safety lags"
        reason_code = f"{strongest}_led_safety_weak"
        severity = "caution"
    elif weakest == "stability":
        summary = f"This set scores well on {strongest}, but results can swing a lot from pack to pack."
        label = f"Led by {strongest}, uneven delivery"
        reason_code = f"{strongest}_led_stability_weak"
        severity = "caution"
    elif weakest == "profit":
        summary = f"This set holds up on {strongest}, but the returns are just not strong enough."
        label = f"Led by {strongest}, weak returns"
        reason_code = f"{strongest}_led_profit_weak"
        severity = "neutral"
    else:
        summary = f"This set is mixed overall — {strongest} holds up best, but {weakest} is the weak point."
        label = "Mixed results"
        reason_code = "mixed"
        severity = "neutral"

    # Tier and rank are shown in the UI — do not append them to the summary sentence

    score_gap: Optional[float] = None
    if len(numeric_scores) >= 2:
        score_gap = max(numeric_scores) - min(numeric_scores)

    evidence = [
        EvidenceItem("Pack score", format_score(pack_score_val)),
        EvidenceItem("Pack tier", str(pack_tier) if pack_tier else "N/A"),
        EvidenceItem("Pack rank", f"#{int(pack_rank)}" if pack_rank is not None else "N/A"),
        EvidenceItem("Profit score", format_score(scores.get("profit"))),
        EvidenceItem("Safety score", format_score(scores.get("safety"))),
        EvidenceItem("Stability score", format_score(scores.get("stability"))),
        EvidenceItem("Strongest pillar", strongest),
        EvidenceItem("Weakest pillar", weakest),
        EvidenceItem("Score gap", format_score(score_gap)),
    ]

    meta = SectionInterpretation(
        summary=summary,
        label=label,
        reason_code=reason_code,
        severity=severity,
        confidence="high" if len(numeric_scores) == 3 else ("medium" if numeric_scores else "low"),
        evidence=evidence,
        signals={
            "alignment": alignment,
            "imbalance": imbalance,
            "strongest": strongest,
            "weakest": weakest,
            **{f"{k}_strength": v for k, v in strengths.items()},
        },
    )

    return PackScoreInterpretation(
        summary=summary,
        strongest_pillar=strongest,
        weakest_pillar=weakest,
        alignment=alignment,
        imbalance=imbalance,
        pillar_strengths=strengths,
        meta=meta,
    )
