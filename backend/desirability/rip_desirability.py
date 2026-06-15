from __future__ import annotations

import math
from typing import Any, Dict, Optional


SCORING_VERSION = "rip_desirability_prototype_v1"
PRIMARY_BLEND_KEY = "rip_desirability_score_70_30"
BLENDS = {
    "rip_desirability_score_80_20": (0.80, 0.20),
    "rip_desirability_score_70_30": (0.70, 0.30),
    "rip_desirability_score_60_40": (0.60, 0.40),
}


def compute_rip_desirability(
    *,
    pure_desirability_score: Any,
    monetary_chase_appeal_score: Any,
) -> Dict[str, Any]:
    """Blend Pure Desirability with Monetary Chase Appeal downstream.

    This prototype does not replace or mutate Pure Desirability. It simply
    models opening desire as a blend of collector subject appeal and monetary
    upside.
    """
    pure = _score_or_none(pure_desirability_score)
    monetary = _score_or_none(monetary_chase_appeal_score)

    scores: Dict[str, Optional[float]] = {}
    for key, (pure_weight, monetary_weight) in BLENDS.items():
        scores[key] = _blend(pure, monetary, pure_weight, monetary_weight)

    return {
        "pure_desirability_score": pure,
        "monetary_chase_appeal_score": monetary,
        "rip_desirability_score_80_20": scores["rip_desirability_score_80_20"],
        "rip_desirability_score_70_30": scores["rip_desirability_score_70_30"],
        "rip_desirability_score_60_40": scores["rip_desirability_score_60_40"],
        "primary_rip_desirability_score": scores[PRIMARY_BLEND_KEY],
        "primary_blend_key": PRIMARY_BLEND_KEY,
        "scoring_version": SCORING_VERSION,
        "component_scores_json": {
            "formulae": {
                key: f"{pure_weight:.2f} * pure_desirability_score + {monetary_weight:.2f} * monetary_chase_appeal_score"
                for key, (pure_weight, monetary_weight) in BLENDS.items()
            },
            "primary_blend_key": PRIMARY_BLEND_KEY,
            "inputs": {
                "pure_desirability_score": pure,
                "monetary_chase_appeal_score": monetary,
            },
            "notes": [
                "Prototype only; does not overwrite current V2 Pure Desirability.",
                "Pure Desirability remains independent from price and EV.",
            ],
        },
    }


def _blend(
    pure_desirability_score: Optional[float],
    monetary_chase_appeal_score: Optional[float],
    pure_weight: float,
    monetary_weight: float,
) -> Optional[float]:
    if pure_desirability_score is None or monetary_chase_appeal_score is None:
        return None
    score = pure_desirability_score * pure_weight + monetary_chase_appeal_score * monetary_weight
    return round(_clamp(score), 4)


def _score_or_none(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return _clamp(parsed)


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, float(value)))
