"""Advanced Metrics interpretation — statistical check layer."""

from __future__ import annotations

from typing import Any, Dict, List

from ..models import EvidenceItem, SectionInterpretation
from ..thresholds import classify_tail_strength, format_currency, format_ratio, format_score, get_numeric


def interpret_advanced_metrics(data: Dict[str, Any]) -> SectionInterpretation:
    summary_data = data.get("summary") if isinstance(data.get("summary"), dict) else data
    headline_score = get_numeric(summary_data, "pack_score", "relative_pack_score")
    profit_score = get_numeric(summary_data, "profit_score", "relative_profit_score")
    safety_score = get_numeric(summary_data, "safety_score", "relative_safety_score")
    stability_score = get_numeric(summary_data, "stability_score", "relative_stability_score")

    expected_loss_per_pack = get_numeric(summary_data, "expected_loss_per_pack")
    expected_loss_when_losing = get_numeric(summary_data, "expected_loss_when_losing")
    median_loss_when_losing = get_numeric(summary_data, "median_loss_when_losing")
    cv = get_numeric(summary_data, "coefficient_of_variation")
    p95_ratio = get_numeric(summary_data, "p95_value_to_cost_ratio")
    hhi = get_numeric(summary_data, "hhi_ev_concentration")
    effective_chase_count = get_numeric(summary_data, "effective_chase_count")

    high_volatility = cv is not None and cv >= 1.6
    low_volatility = cv is not None and cv <= 0.9
    high_concentration = hhi is not None and hhi >= 0.22
    broad_depth = effective_chase_count is not None and effective_chase_count >= 10
    thin_depth = effective_chase_count is not None and effective_chase_count < 5
    loss_drag = expected_loss_per_pack is not None and expected_loss_per_pack > 0
    severe_losing_profile = (
        expected_loss_when_losing is not None
        and median_loss_when_losing is not None
        and expected_loss_when_losing >= median_loss_when_losing
        and expected_loss_when_losing > 0
    )
    strong_tail = classify_tail_strength(p95_ratio, missing="medium") == "high"

    headline_is_strong = any(
        score is not None and score >= 70.0
        for score in (headline_score, profit_score, safety_score, stability_score)
    )

    if high_volatility and strong_tail and loss_drag:
        summary = "The numbers swing a lot and there is real upside, but the losses are also real \u2014 this is not a smooth set to rip."
        label = "High swings, real upside and losses"
        reason_code = "volatile_tail_loss_drag"
        severity = "caution"
    elif low_volatility and broad_depth and not high_concentration and not severe_losing_profile:
        summary = "The deeper numbers back up the headline score \u2014 the set is consistent and spread out."
        label = "Stats support the headline"
        reason_code = "stats_confirm_headline"
        severity = "positive"
    elif high_concentration and thin_depth:
        summary = "The headline score looks good, but the deeper numbers show extra risk \u2014 value depends on too few cards."
        label = "Good score, but concentrated risk"
        reason_code = "high_concentration_thin_depth"
        severity = "caution"
    elif low_volatility and (p95_ratio is not None and p95_ratio < 1.3) and loss_drag:
        summary = "Losses are kept in check here, but big wins are limited \u2014 this is a safer but not exciting set."
        label = "Controlled losses, limited upside"
        reason_code = "low_volatility_capped_upside"
        severity = "neutral"
    elif headline_is_strong and (high_concentration or high_volatility) and severe_losing_profile:
        summary = "The headline score looks good, but the deeper numbers show extra risk."
        label = "Headline vs. hidden risk"
        reason_code = "stats_flag_caution"
        severity = "caution"
    else:
        summary = "The deeper numbers are mixed: there is some upside, but the risk is still noticeable."
        label = "Mixed stats"
        reason_code = "mixed_stats"
        severity = "neutral"

    key_fields = [cv, hhi, effective_chase_count, p95_ratio]
    filled = sum(1 for f in key_fields if f is not None)
    confidence = "high" if filled >= 3 else ("medium" if filled >= 1 else "low")

    cv_str = f"{cv:.2f}" if cv is not None else "N/A"
    hhi_str = f"{hhi:.3f}" if hhi is not None else "N/A"

    evidence: List[EvidenceItem] = [
        EvidenceItem("Coefficient of variation", cv_str),
        EvidenceItem("Value spread", hhi_str),
        EvidenceItem("Effective contributor count", str(int(round(effective_chase_count))) if effective_chase_count is not None else "N/A"),
        EvidenceItem("Expected loss per pack", format_currency(expected_loss_per_pack)),
        EvidenceItem("Expected loss when losing", format_currency(expected_loss_when_losing)),
        EvidenceItem("Median loss when losing", format_currency(median_loss_when_losing)),
        EvidenceItem("Big-hit range (p95)", format_ratio(p95_ratio)),
    ]

    return SectionInterpretation(
        summary=summary,
        label=label,
        reason_code=reason_code,
        severity=severity,
        confidence=confidence,
        evidence=evidence,
        signals={
            "high_volatility": high_volatility,
            "high_concentration": high_concentration,
            "broad_depth": broad_depth,
            "thin_depth": thin_depth,
            "loss_drag": loss_drag,
            "severe_losing_profile": severe_losing_profile,
            "strong_tail": strong_tail,
        },
    )
