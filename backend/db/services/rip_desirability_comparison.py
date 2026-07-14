"""RIP with/without desirability comparison helpers."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional

RIP_COMPARISON_VERSION = "rip_desirability_comparison_v1"
RIP_PRESENTATION_NORMALIZATION_VERSION = "rip_cohort_min_max_v1"
RIP_WITH_DESIRABILITY_WEIGHTS = {
    "profit_score": 45.0,
    "safety_score": 25.0,
    "desirability_score": 20.0,
    "stability_score": 10.0,
}
RIP_WITHOUT_DESIRABILITY_WEIGHTS = {
    "profit_score": 45.0,
    "safety_score": 25.0,
    "stability_score": 10.0,
}


def _to_optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _weighted_score(row: Dict[str, Any], weights: Dict[str, float]) -> Optional[float]:
    values: Dict[str, float] = {}
    for key in weights:
        value = _to_optional_float(row.get(key))
        if value is None:
            return None
        values[key] = value

    total_weight = float(sum(weights.values()))
    if total_weight <= 0:
        return None
    return sum(values[key] * (weight / total_weight) for key, weight in weights.items())


def calculate_rip_score_with_desirability(row: Dict[str, Any]) -> Optional[float]:
    """Calculate the intended four-pillar RIP score from component scores."""

    score = _weighted_score(row, RIP_WITH_DESIRABILITY_WEIGHTS)
    return round(score, 2) if score is not None else None


def calculate_rip_score_without_desirability(row: Dict[str, Any]) -> Optional[float]:
    """Calculate financial-only RIP by excluding desirability and re-normalizing."""

    score = _weighted_score(row, RIP_WITHOUT_DESIRABILITY_WEIGHTS)
    return round(score, 2) if score is not None else None


def _rank_scores(rows: Iterable[Dict[str, Any]], score_key: str) -> Dict[str, Optional[int]]:
    scored = [
        (str(row.get("target_id")), _to_optional_float(row.get(score_key)))
        for row in rows
        if row.get("target_id")
    ]
    valid = [(target_id, score) for target_id, score in scored if score is not None]
    valid.sort(key=lambda item: (-item[1], item[0]))

    ranks: Dict[str, Optional[int]] = {target_id: None for target_id, _ in scored}
    for rank, (target_id, _score) in enumerate(valid, start=1):
        ranks[target_id] = rank
    return ranks


def _relative_scores(rows: Iterable[Dict[str, Any]], score_key: str) -> Dict[str, Optional[float]]:
    scored = [
        (str(row.get("target_id")), _to_optional_float(row.get(score_key)))
        for row in rows
        if row.get("target_id")
    ]
    valid_scores = [score for _target_id, score in scored if score is not None]
    if not valid_scores:
        return {target_id: None for target_id, _score in scored}

    score_min = min(valid_scores)
    score_max = max(valid_scores)
    if score_max <= score_min:
        return {
            target_id: (50.0 if score is not None else None)
            for target_id, score in scored
        }
    return {
        target_id: (
            round(100.0 * ((score - score_min) / (score_max - score_min)), 2)
            if score is not None
            else None
        )
        for target_id, score in scored
    }


def _tier_for_rank(rank: Optional[int], total: int) -> Optional[str]:
    if rank is None or total <= 0:
        return None
    buckets = (
        (0.05, "S"),
        (0.15, "A"),
        (0.30, "B"),
        (0.50, "C"),
        (0.75, "D"),
    )
    for fraction, tier in buckets:
        if rank <= max(1, math.ceil(total * fraction)):
            return tier
    return "F"


def _comparison_label(score_delta: Optional[float], rank_delta: Optional[int]) -> str:
    if score_delta is None or rank_delta is None:
        return "Missing desirability"
    if rank_delta >= 2:
        return "Rank lift"
    if rank_delta <= -2:
        return "Rank drag"
    if score_delta >= 2.0:
        return "Score lift"
    if score_delta <= -2.0:
        return "Score drag"
    return "Minimal impact"


def build_rip_desirability_comparison_payload(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return copied rows enriched with comparison fields plus diagnostics."""

    enriched: List[Dict[str, Any]] = []
    for row in rows:
        copied = dict(row)
        without_score = calculate_rip_score_without_desirability(copied)
        with_score = calculate_rip_score_with_desirability(copied)
        score_delta = (
            round(with_score - without_score, 2)
            if with_score is not None and without_score is not None
            else None
        )
        copied.update(
            {
                "rip_score_without_desirability": without_score,
                "rip_score_with_desirability": with_score,
                "rip_score_delta": score_delta,
                "desirability_component_score": _to_optional_float(copied.get("desirability_score")),
                "rip_desirability_comparison_version": RIP_COMPARISON_VERSION,
            }
        )
        enriched.append(copied)

    without_ranks = _rank_scores(enriched, "rip_score_without_desirability")
    with_ranks = _rank_scores(enriched, "rip_score_with_desirability")
    relative_without_scores = _relative_scores(enriched, "rip_score_without_desirability")
    relative_with_scores = _relative_scores(enriched, "rip_score_with_desirability")
    total_core_scored = sum(1 for row in enriched if row.get("rip_score_without_desirability") is not None)
    total_final_scored = sum(1 for row in enriched if row.get("rip_score_with_desirability") is not None)

    valid_count = 0
    raises_rank_count = 0
    lowers_rank_count = 0
    minimal_impact_count = 0
    missing_desirability_count = 0

    for row in enriched:
        target_id = str(row.get("target_id"))
        without_rank = without_ranks.get(target_id)
        with_rank = with_ranks.get(target_id)
        rank_delta = (
            without_rank - with_rank
            if without_rank is not None and with_rank is not None
            else None
        )
        row["rip_rank_without_desirability"] = without_rank
        row["rip_rank_with_desirability"] = with_rank
        row["rip_rank_delta"] = rank_delta
        row["rip_desirability_impact_label"] = _comparison_label(row.get("rip_score_delta"), rank_delta)
        row["relative_rip_core_score"] = relative_without_scores.get(target_id)
        row["rip_core_rank"] = without_rank
        row["rip_core_tier"] = _tier_for_rank(without_rank, total_core_scored)
        row["relative_pack_score"] = relative_with_scores.get(target_id)
        row["pack_score"] = row.get("rip_score_with_desirability")
        row["pack_rank"] = with_rank
        row["pack_tier"] = _tier_for_rank(with_rank, total_final_scored)
        row["rip_presentation_normalization_version"] = RIP_PRESENTATION_NORMALIZATION_VERSION
        row["relative_pack_score_normalization_version"] = RIP_PRESENTATION_NORMALIZATION_VERSION
        row["relative_rip_core_score_normalization_version"] = RIP_PRESENTATION_NORMALIZATION_VERSION

        if row.get("rip_score_with_desirability") is None:
            missing_desirability_count += 1
            continue
        if row.get("rip_score_without_desirability") is None:
            continue
        valid_count += 1
        if rank_delta is not None and rank_delta > 0:
            raises_rank_count += 1
        elif rank_delta is not None and rank_delta < 0:
            lowers_rank_count += 1
        else:
            minimal_impact_count += 1

    return {
        "rows": enriched,
        "diagnostics": {
            "version": RIP_COMPARISON_VERSION,
            "presentation_normalization_version": RIP_PRESENTATION_NORMALIZATION_VERSION,
            "total_sets": len(enriched),
            "valid_comparison_count": valid_count,
            "missing_desirability_count": missing_desirability_count,
            "raises_rank_count": raises_rank_count,
            "lowers_rank_count": lowers_rank_count,
            "minimal_impact_count": minimal_impact_count,
        },
    }
