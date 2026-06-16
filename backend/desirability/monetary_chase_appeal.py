from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional, Tuple


SCORING_VERSION = "monetary_chase_appeal_v1_30_20_20_15_15_data_quality"
BIG_HIT_PROBABILITY_MAX = 0.03

INPUT_FIELDS = [
    "top_card_value",
    "top_3_card_value",
    "top_5_card_value",
    "top1_card_value",
    "top3_card_value",
    "top5_card_value",
    "prob_big_hit",
    "p95_value_to_cost_ratio",
    "p99_value_to_cost_ratio",
    "hit_ev_per_pack",
    "mean_value_to_cost_ratio",
    "effective_chase_count",
    "hhi_ev_concentration",
    "top1_ev_share",
    "top3_ev_share",
    "top5_ev_share",
    "current_market_pack_cost",
    "pack_cost",
]

WEIGHTS = {
    "big_hit_upside_component": 0.30,
    "big_hit_probability_component": 0.20,
    "high_percentile_upside_component": 0.20,
    "chase_depth_component": 0.15,
    "concentration_component": 0.15,
}


def compute_monetary_chase_appeal(
    metrics: Mapping[str, Any],
) -> Dict[str, Any]:
    """Compute a 0-100 money-driven opening excitement score.

    This score is intentionally separate from Pure Desirability. It uses market
    value, EV, pull-upside, and value-spread inputs to answer whether a set has
    monetary chase excitement.
    """
    pack_cost = _first_float(metrics, "current_market_pack_cost", "pack_cost")
    pack_cost = pack_cost if pack_cost is not None and pack_cost > 0 else None

    components = {
        "big_hit_upside_component": _big_hit_upside_component(metrics, pack_cost),
        "big_hit_probability_component": _big_hit_probability_component(metrics),
        "high_percentile_upside_component": _high_percentile_upside_component(metrics),
        "chase_depth_component": _chase_depth_component(metrics),
        "concentration_component": _concentration_component(metrics),
    }
    data_quality = _data_quality(components)
    score = _weighted_score(components, WEIGHTS) if data_quality != "missing" else None
    available_fields, missing_fields = _input_field_status(metrics)

    return {
        "monetary_chase_appeal_score": _round_score(score) if score is not None else None,
        "monetary_data_quality": data_quality,
        "scoring_version": SCORING_VERSION,
        "component_scores_json": {
            "formula": (
                "0.30 * big_hit_upside_component + 0.20 * big_hit_probability_component "
                "+ 0.20 * high_percentile_upside_component + 0.15 * chase_depth_component "
                "+ 0.15 * concentration_component"
            ),
            "weights": dict(WEIGHTS),
            "monetary_data_quality": data_quality,
            "available_input_fields": available_fields,
            "missing_input_fields": missing_fields,
            "component_availability": {
                key: value is not None
                for key, value in components.items()
            },
            "anchors": {
                "big_hit_probability_component": {
                    "min": 0.0,
                    "max": BIG_HIT_PROBABILITY_MAX,
                    "description": "Fixed Pokemon pack-opening anchor; a 1.5% big-hit chance scores 50 before clamping.",
                },
                "top_card_value_to_pack_cost": {"min": 0.0, "max": 50.0},
                "top_3_value_to_pack_cost": {"min": 0.0, "max": 100.0},
                "top_5_value_to_pack_cost": {"min": 0.0, "max": 150.0},
                "p95_value_to_cost_ratio": {"min": 0.25, "max": 5.0},
                "p99_value_to_cost_ratio": {"min": 0.5, "max": 10.0},
                "hit_ev_to_pack_cost": {"min": 0.0, "max": 1.5},
                "mean_value_to_cost_ratio": {"min": 0.0, "max": 2.0},
                "effective_chase_count": {"min": 1.0, "max": 40.0},
            },
            "components": components,
            "input_summary": {
                "pack_cost": pack_cost,
                "top_card_value": _first_float(metrics, "top_card_value", "top1_card_value"),
                "top_3_card_value": _first_float(metrics, "top_3_card_value", "top3_card_value"),
                "top_5_card_value": _first_float(metrics, "top_5_card_value", "top5_card_value"),
                "prob_big_hit": _first_float(metrics, "prob_big_hit"),
                "p95_value_to_cost_ratio": _first_float(metrics, "p95_value_to_cost_ratio"),
                "p99_value_to_cost_ratio": _first_float(metrics, "p99_value_to_cost_ratio"),
                "hit_ev_per_pack": _first_float(metrics, "hit_ev_per_pack"),
                "mean_value_to_cost_ratio": _first_float(metrics, "mean_value_to_cost_ratio"),
                "effective_chase_count": _first_float(metrics, "effective_chase_count"),
                "hhi_ev_concentration": _first_float(metrics, "hhi_ev_concentration"),
                "top1_ev_share": _first_float(metrics, "top1_ev_share"),
                "top3_ev_share": _first_float(metrics, "top3_ev_share"),
                "top5_ev_share": _first_float(metrics, "top5_ev_share"),
            },
            "notes": [
                "This is not Pure Desirability and may correlate with EV, price, and profit.",
                "Missing component evidence is represented as null and is not averaged as zero.",
                "A score is emitted only when enough core monetary signals are available; otherwise monetary_chase_appeal_score is null.",
                "Concentration rewards monetary value spread; top-card excitement is captured separately in big_hit_upside_component.",
            ],
        },
    }


def _big_hit_upside_component(metrics: Mapping[str, Any], pack_cost: Optional[float]) -> Optional[float]:
    top_card_value = _first_float(metrics, "top_card_value", "top1_card_value")
    top3_value = _first_float(metrics, "top_3_card_value", "top3_card_value")
    top5_value = _first_float(metrics, "top_5_card_value", "top5_card_value")
    p99_ratio = _first_float(metrics, "p99_value_to_cost_ratio")

    candidates = []
    if top_card_value is not None and pack_cost is not None:
        candidates.append((_normalize(top_card_value / pack_cost, 0.0, 50.0), 0.50))
    if top3_value is not None and pack_cost is not None:
        candidates.append((_normalize(top3_value / pack_cost, 0.0, 100.0), 0.25))
    if top5_value is not None and pack_cost is not None:
        candidates.append((_normalize(top5_value / pack_cost, 0.0, 150.0), 0.15))
    if p99_ratio is not None:
        candidates.append((_normalize(p99_ratio, 0.5, 10.0), 0.10))

    return _weighted_candidates(candidates)


def _big_hit_probability_component(metrics: Mapping[str, Any]) -> Optional[float]:
    prob_big_hit = _first_float(metrics, "prob_big_hit")
    if prob_big_hit is None:
        return None
    return _normalize(prob_big_hit, 0.0, BIG_HIT_PROBABILITY_MAX)


def _high_percentile_upside_component(metrics: Mapping[str, Any]) -> Optional[float]:
    candidates = []
    p95_ratio = _first_float(metrics, "p95_value_to_cost_ratio")
    p99_ratio = _first_float(metrics, "p99_value_to_cost_ratio")
    hit_ev_ratio = _ratio_to_pack_cost(metrics, "hit_ev_per_pack")
    mean_ratio = _first_float(metrics, "mean_value_to_cost_ratio")

    if p95_ratio is not None:
        candidates.append((_normalize(p95_ratio, 0.25, 5.0), 0.40))
    if p99_ratio is not None:
        candidates.append((_normalize(p99_ratio, 0.5, 10.0), 0.30))
    if hit_ev_ratio is not None:
        candidates.append((_normalize(hit_ev_ratio, 0.0, 1.5), 0.20))
    if mean_ratio is not None:
        candidates.append((_normalize(mean_ratio, 0.0, 2.0), 0.10))

    return _weighted_candidates(candidates)


def _chase_depth_component(metrics: Mapping[str, Any]) -> Optional[float]:
    effective_chase_count = _first_float(metrics, "effective_chase_count")
    if effective_chase_count is None:
        return None
    return _normalize(effective_chase_count, 1.0, 40.0)


def _concentration_component(metrics: Mapping[str, Any]) -> Optional[float]:
    """Reward spread of monetary chase value, while upside is scored elsewhere."""
    top1_share = _first_float(metrics, "top1_ev_share")
    top3_share = _first_float(metrics, "top3_ev_share")
    top5_share = _first_float(metrics, "top5_ev_share")
    hhi = _first_float(metrics, "hhi_ev_concentration")

    risk_candidates = []
    if top1_share is not None:
        risk_candidates.append(_normalize(top1_share, 0.0, 0.60))
    if top3_share is not None:
        risk_candidates.append(_normalize(top3_share, 0.0, 0.85))
    if top5_share is not None:
        risk_candidates.append(_normalize(top5_share, 0.0, 1.0))
    if hhi is not None:
        risk_candidates.append(_normalize(hhi, 0.0, 0.60))

    if not risk_candidates:
        return None

    concentration_risk = max(risk_candidates)
    return _clamp(100.0 - concentration_risk)


def _data_quality(components: Mapping[str, Optional[float]]) -> str:
    available_components = {
        key for key, value in components.items()
        if value is not None
    }
    has_upside = bool(
        available_components
        & {"big_hit_upside_component", "high_percentile_upside_component"}
    )
    if not has_upside or len(available_components) < 2:
        return "missing"
    if len(available_components) >= 4:
        return "usable"
    return "partial"


def _weighted_score(components: Mapping[str, Optional[float]], weights: Mapping[str, float]) -> Optional[float]:
    total_weight = 0.0
    total = 0.0
    for key, weight in weights.items():
        value = _finite_float(components.get(key))
        if value is None:
            continue
        total += value * float(weight)
        total_weight += float(weight)
    if total_weight <= 0:
        return None
    return total / total_weight


def _weighted_candidates(candidates: Tuple[Tuple[float, float], ...] | list[Tuple[float, float]]) -> Optional[float]:
    total_weight = sum(weight for _, weight in candidates)
    if total_weight <= 0:
        return None
    return _clamp(sum(score * weight for score, weight in candidates) / total_weight)


def _ratio_to_pack_cost(metrics: Mapping[str, Any], field: str) -> Optional[float]:
    value = _first_float(metrics, field)
    pack_cost = _first_float(metrics, "current_market_pack_cost", "pack_cost")
    if value is None or pack_cost is None or pack_cost <= 0:
        return None
    return value / pack_cost


def _first_float(metrics: Mapping[str, Any], *fields: str) -> Optional[float]:
    for field in fields:
        parsed = _finite_float(metrics.get(field))
        if parsed is not None:
            return parsed
    return None


def _input_field_status(metrics: Mapping[str, Any]) -> Tuple[list[str], list[str]]:
    available = [
        field for field in INPUT_FIELDS
        if _finite_float(metrics.get(field)) is not None
    ]
    missing = [field for field in INPUT_FIELDS if field not in available]
    return available, missing


def _finite_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _normalize(value: Optional[float], min_value: float, max_value: float) -> float:
    if value is None or max_value <= min_value:
        return 0.0
    return _clamp(100.0 * ((float(value) - min_value) / (max_value - min_value)))


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _round_score(value: float) -> float:
    return round(_clamp(value), 4)
