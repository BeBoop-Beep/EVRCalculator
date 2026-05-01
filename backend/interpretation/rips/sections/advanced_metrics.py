"""Advanced Metrics interpretation - consistency-check layer."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import EvidenceItem, SectionInterpretation
from ..thresholds import classify_tail_strength, format_currency, format_ratio, get_numeric


def _resolve_decision_category(
    data: Dict[str, Any],
    pack_context: Optional[Dict[str, Any]],
) -> str:
    if isinstance(pack_context, dict):
        signals = pack_context.get("signals")
        if isinstance(signals, dict):
            category = signals.get("decision_category")
            if isinstance(category, str) and category:
                return category

    summary_data = data.get("summary") if isinstance(data.get("summary"), dict) else data
    pack_tier = str(summary_data.get("pack_tier") or "").strip().upper()
    pack_score = get_numeric(summary_data, "pack_score", "relative_pack_score")

    if pack_tier == "S" or (pack_score is not None and pack_score >= 85.0):
        return "elite_open"
    if pack_tier == "A" or (pack_score is not None and pack_score >= 70.0):
        return "good_open"
    if pack_tier in {"D", "F"} or (pack_score is not None and pack_score < 40.0):
        return "weak_open"
    return "good_open"


def interpret_advanced_metrics(
    data: Dict[str, Any],
    pack_context: Optional[Dict[str, Any]] = None,
) -> SectionInterpretation:
    summary_data = data.get("summary") if isinstance(data.get("summary"), dict) else data
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
    decision_category = _resolve_decision_category(data, pack_context)
    risk_flags = high_volatility or high_concentration or severe_losing_profile or thin_depth or loss_drag
    clean_profile = low_volatility and broad_depth and not high_concentration and not severe_losing_profile

    if decision_category == "strong_but_risky" and risk_flags:
        summary = "The deeper numbers support the main read: this set has strong hits, but bad packs can still hurt."
        label = "Risk check"
        reason_code = "supports_strong_but_risky"
        severity = "caution"
    elif decision_category == "elite_open" and clean_profile:
        summary = "The deeper numbers support the high score: value is strong and the risk is not enough to cancel it out."
        label = "Numbers back it up"
        reason_code = "supports_elite_open"
        severity = "positive"
    elif decision_category in {"elite_open", "strong_but_risky"} and risk_flags:
        summary = "The deeper numbers still support the main read, but they flag a catch: results depend on avoiding rough packs."
        label = "Support with a catch"
        reason_code = "supports_with_catch"
        severity = "caution"
    elif decision_category == "good_open" and (high_concentration or thin_depth):
        summary = "The set still looks solid, but more of the value depends on landing the right hits."
        label = "Watch the hit spread"
        reason_code = "good_open_concentration_catch"
        severity = "neutral"
    elif decision_category == "weak_open":
        summary = "The deeper numbers agree with the low score: the set is not paying back the pack price well enough."
        label = "Numbers confirm the weakness"
        reason_code = "confirms_weak_open"
        severity = "negative"
    elif clean_profile:
        summary = "The deeper numbers mostly confirm the read: value is spread well enough and downside stays controlled."
        label = "Mostly confirms the read"
        reason_code = "mostly_confirms_read"
        severity = "positive"
    else:
        summary = "The deeper numbers are mixed: they do not overturn the main read, but they do highlight some risk concentration."
        label = "Mixed confirmation"
        reason_code = "mixed_confirmation"
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
            "decision_category": decision_category,
            "high_volatility": high_volatility,
            "high_concentration": high_concentration,
            "broad_depth": broad_depth,
            "thin_depth": thin_depth,
            "loss_drag": loss_drag,
            "severe_losing_profile": severe_losing_profile,
            "strong_tail": strong_tail,
        },
    )
