"""Independent interpretation logic for the Safety pillar."""

from __future__ import annotations

from typing import Any, Dict

from ..models import EvidenceItem, SafetyInterpretation, SectionInterpretation
from ..thresholds import (
    P05_TAIL_RECOVERY_SEVERE_MULTIPLIER,
    classify_probability,
    classify_ratio_high_medium_low,
    classify_score_strength,
    format_currency,
    format_percent,
    format_ratio,
    format_score,
    get_numeric,
)


def interpret_safety(data: Dict[str, Any]) -> SafetyInterpretation:
    summary_data = data.get("summary") if isinstance(data.get("summary"), dict) else data

    score = get_numeric(summary_data, "safety_score", "relative_safety_score")
    pack_cost = get_numeric(summary_data, "pack_cost")
    expected_loss_fraction = get_numeric(summary_data, "expected_loss_when_losing_fraction")
    median_loss_fraction = get_numeric(summary_data, "median_loss_when_losing_fraction")
    p05_shortfall = get_numeric(summary_data, "p05_shortfall_to_cost")
    expected_loss_when_losing = get_numeric(summary_data, "expected_loss_when_losing")
    median_loss_when_losing = get_numeric(summary_data, "median_loss_when_losing")
    tail_value_p05 = get_numeric(summary_data, "tail_value_p05")

    score_strength = classify_score_strength(score)

    loss_depth_driver = max(
        [value for value in (expected_loss_fraction, median_loss_fraction, p05_shortfall) if value is not None],
        default=None,
    )
    # downside_pressure: high means more downside pressure (worse safety); high safety_score means safer
    downside_pressure = classify_ratio_high_medium_low(
        loss_depth_driver,
        high_min=0.70,
        medium_min=0.35,
        missing=score_strength,
    )

    absolute_loss_ratio = None
    if pack_cost and pack_cost > 0 and expected_loss_when_losing is not None:
        absolute_loss_ratio = expected_loss_when_losing / pack_cost

    # loss_depth: high means losses are deeper (worse)
    loss_depth = classify_ratio_high_medium_low(
        median_loss_fraction if median_loss_fraction is not None else absolute_loss_ratio,
        high_min=0.65,
        medium_min=0.35,
        missing=score_strength,
    )

    severe_tail_recovery = (
        tail_value_p05 is not None
        and pack_cost is not None
        and pack_cost > 0
        and tail_value_p05 < (pack_cost * P05_TAIL_RECOVERY_SEVERE_MULTIPLIER)
    )
    severe_shortfall = p05_shortfall is not None and p05_shortfall >= 0.75
    low_loss_probability_support = classify_probability(get_numeric(summary_data, "prob_profit"), missing="medium") == "low"

    if severe_tail_recovery and severe_shortfall:
        summary = "Risk is high because the worst packs give back very little of what you paid."
        label = "Severe downside tail"
        reason_code = "severe_tail_recovery"
        severity = "negative"
    elif downside_pressure == "high" and loss_depth == "high":
        summary = "When this set misses, it usually gives back much less than the pack cost."
        label = "Deep losses when behind"
        reason_code = "high_downside_pressure"
        severity = "negative"
    elif downside_pressure in {"low", "medium"} and loss_depth == "low":
        summary = "Misses still happen, but they are not as painful as most risky sets."
        label = "Controlled losses"
        reason_code = "controlled_downside"
        severity = "positive"
    elif low_loss_probability_support and median_loss_when_losing is not None and median_loss_when_losing < (pack_cost or 0):
        summary = "Even when packs lose, they do not lose too much — the damage is limited."
        label = "Manageable losses"
        reason_code = "manageable_loss_depth"
        severity = "neutral"
    else:
        summary = "Risk is in the middle — packs miss often enough, but the worst outcomes are not catastrophic."
        label = "Mixed safety"
        reason_code = "mixed_safety"
        severity = "neutral"

    confidence: str
    if score is not None and expected_loss_fraction is not None and tail_value_p05 is not None:
        confidence = "high"
    elif score is not None:
        confidence = "medium"
    else:
        confidence = "low"

    evidence = [
        EvidenceItem("Safety score", format_score(score)),
        EvidenceItem("Avg loss fraction (when losing)", format_percent(expected_loss_fraction)),
        EvidenceItem("Median loss fraction (when losing)", format_percent(median_loss_fraction)),
        EvidenceItem("Worst-case shortfall to cost", format_percent(p05_shortfall)),
        EvidenceItem("Worst-case pack value (p05)", format_currency(tail_value_p05)),
        EvidenceItem("Pack cost", format_currency(pack_cost)),
    ]

    signals: Dict[str, Any] = {
        "downside_pressure": downside_pressure,
        "loss_depth": loss_depth,
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

    return SafetyInterpretation(
        summary=summary,
        signals=signals,  # type: ignore[arg-type]
        score=score,
        meta=meta,
    )
