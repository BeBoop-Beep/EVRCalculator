from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Tuple


TREND_SCORING_VERSION = "pokemon_google_trends_relative_interest_v1"

SEARCH_POPULARITY_SCORE = "search_popularity_score"
RECENT_TREND_SCORE = "recent_trend_score"
TREND_MOMENTUM_SCORE = "trend_momentum_score"

CURRENT_TIMEFRAME = "today 12-m"
RECENT_TIMEFRAME = "today 1-m"
BASELINE_TIMEFRAME = "today 5-y"


def normalize_timeframe_rows(rows: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    row_list = list(rows)
    usable = [
        row
        for row in row_list
        if row.get("pokemon_reference_id") is not None and _as_float(row.get("relative_to_anchor")) is not None
    ]
    if not usable:
        return [], {
            "signal": "relative_to_anchor",
            "confidence": "insufficient",
            "input_rows": len(row_list),
            "normalized_rows": 0,
            "reason": "No usable relative-to-anchor Google Trends search interest values were captured.",
        }

    max_relative = max(_as_float(row.get("relative_to_anchor")) or 0.0 for row in usable)
    sorted_rows = sorted(usable, key=lambda row: _as_float(row.get("relative_to_anchor")) or 0.0, reverse=True)
    normalized: List[Dict[str, Any]] = []

    for rank, row in enumerate(sorted_rows, start=1):
        relative_value = _as_float(row.get("relative_to_anchor")) or 0.0
        if max_relative <= 0:
            normalized_score = 0.0
        else:
            normalized_score = 100.0 * math.log1p(relative_value) / math.log1p(max_relative)
        normalized.append(
            {
                "pokemon_reference_id": row.get("pokemon_reference_id"),
                "pokedex_number": row.get("pokedex_number"),
                "pokemon_name": row.get("pokemon_name"),
                "query_term": row.get("query_term"),
                "source_name": row.get("source_name"),
                "snapshot_id": row.get("snapshot_id"),
                "geo": row.get("geo"),
                "timeframe": row.get("timeframe"),
                "window_role": row.get("window_role"),
                "relative_to_anchor": relative_value,
                "normalized_relative_search_interest_score": round(_bounded(normalized_score), 4),
                "normalized_rank": rank,
                "confidence": _confidence_for_timeframe_row(row),
                "is_ambiguous": bool(row.get("is_ambiguous")),
                "scoring_version": TREND_SCORING_VERSION,
            }
        )

    return normalized, {
        "signal": "relative_to_anchor",
        "confidence": _primary_confidence(normalized),
        "input_rows": len(row_list),
        "normalized_rows": len(normalized),
        "coverage_ratio": round(len(normalized) / len(row_list), 4) if row_list else 0.0,
        "max_relative_to_anchor": round(max_relative, 8),
        "measurement_note": "Normalized Google Trends relative search interest, not absolute search volume.",
    }


def calculate_derived_trend_scores(
    normalized_by_timeframe: Dict[str, List[Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    current_by_ref = _by_reference(normalized_by_timeframe.get(CURRENT_TIMEFRAME, []))
    baseline_by_ref = _by_reference(normalized_by_timeframe.get(BASELINE_TIMEFRAME, []))
    recent_by_ref = _by_reference(normalized_by_timeframe.get(RECENT_TIMEFRAME, []))

    search_popularity = _calculate_search_popularity(current_by_ref, baseline_by_ref)
    recent_trends = _calculate_recent_trend(recent_by_ref)
    momentum = _calculate_momentum(recent_by_ref, current_by_ref, baseline_by_ref)

    scores = search_popularity + recent_trends + momentum
    return scores, {
        "search_popularity_scores": len(search_popularity),
        "recent_trend_scores": len(recent_trends),
        "trend_momentum_scores": len(momentum),
        "measurement_note": (
            "Search Popularity Score and Recent Trend Score are normalized relative search-interest scores. "
            "Trend Momentum Score compares recent relative interest against baseline relative interest. "
            "None of these are absolute search-volume estimates."
        ),
    }


def build_trend_diagnostics(
    *,
    source_rows_by_timeframe: Dict[str, List[Dict[str, Any]]],
    normalized_by_timeframe: Dict[str, List[Dict[str, Any]]],
    derived_scores: List[Dict[str, Any]],
) -> Dict[str, Any]:
    search_scores = [score for score in derived_scores if score.get("score_name") == SEARCH_POPULARITY_SCORE]
    recent_scores = [score for score in derived_scores if score.get("score_name") == RECENT_TREND_SCORE]
    momentum_scores = [score for score in derived_scores if score.get("score_name") == TREND_MOMENTUM_SCORE]

    all_rows = [row for rows in source_rows_by_timeframe.values() for row in rows]
    ambiguous_rows = [row for row in all_rows if row.get("is_ambiguous")]
    zero_or_insufficient = [
        row
        for row in all_rows
        if row.get("extraction_confidence") == "insufficient"
        or (_as_float(row.get("raw_interest_value")) is not None and (_as_float(row.get("raw_interest_value")) or 0.0) <= 0)
    ]

    return {
        "top_long_term_searched_pokemon": _top_scores(
            normalized_by_timeframe.get(BASELINE_TIMEFRAME, []),
            score_field="normalized_relative_search_interest_score",
            limit=20,
        ),
        "top_current_search_popularity_pokemon": _top_scores(search_scores, score_field="score_value", limit=20),
        "top_current_trending_pokemon": _top_scores(recent_scores, score_field="score_value", limit=20),
        "top_momentum_gainers": sorted(
            _score_preview(momentum_scores, "score_value"),
            key=lambda item: item.get("momentum_log_ratio") or 0.0,
            reverse=True,
        )[:20],
        "ambiguous_noisy_search_terms": _dedupe_preview(ambiguous_rows),
        "zero_or_insufficient_data_pokemon": _dedupe_preview(zero_or_insufficient),
        "measurement_note": "All Google Trends diagnostics are based on normalized relative search interest, not total searches.",
    }


def _calculate_search_popularity(
    current_by_ref: Dict[Any, Dict[str, Any]],
    baseline_by_ref: Dict[Any, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    reference_ids = set(current_by_ref) | set(baseline_by_ref)
    rows: List[Dict[str, Any]] = []
    for reference_id in reference_ids:
        current = current_by_ref.get(reference_id)
        baseline = baseline_by_ref.get(reference_id)
        if current and baseline:
            score_value = (
                0.75 * float(current["normalized_relative_search_interest_score"])
                + 0.25 * float(baseline["normalized_relative_search_interest_score"])
            )
            confidence = _combined_confidence(current, baseline)
            contributing = [current, baseline]
        elif current:
            score_value = float(current["normalized_relative_search_interest_score"])
            confidence = _downgrade_confidence(current.get("confidence"))
            contributing = [current]
        elif baseline:
            score_value = float(baseline["normalized_relative_search_interest_score"])
            confidence = _downgrade_confidence(baseline.get("confidence"))
            contributing = [baseline]
        else:
            continue

        rows.append(_derived_score_payload(reference_id, SEARCH_POPULARITY_SCORE, score_value, confidence, contributing))
    return _rank_scores(rows)


def _calculate_recent_trend(recent_by_ref: Dict[Any, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [
        _derived_score_payload(
            reference_id,
            RECENT_TREND_SCORE,
            float(row["normalized_relative_search_interest_score"]),
            row.get("confidence") or "medium",
            [row],
        )
        for reference_id, row in recent_by_ref.items()
    ]
    return _rank_scores(rows)


def _calculate_momentum(
    recent_by_ref: Dict[Any, Dict[str, Any]],
    current_by_ref: Dict[Any, Dict[str, Any]],
    baseline_by_ref: Dict[Any, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    raw_rows: List[Dict[str, Any]] = []
    for reference_id, recent in recent_by_ref.items():
        baseline = baseline_by_ref.get(reference_id) or current_by_ref.get(reference_id)
        if baseline is None:
            continue

        recent_relative = float(recent.get("relative_to_anchor") or 0.0)
        baseline_relative = float(baseline.get("relative_to_anchor") or 0.0)
        momentum_log_ratio = math.log((recent_relative + 0.01) / (baseline_relative + 0.01))
        confidence = _combined_confidence(recent, baseline)
        raw_rows.append(
            {
                "reference_id": reference_id,
                "recent": recent,
                "baseline": baseline,
                "momentum_log_ratio": momentum_log_ratio,
                "confidence": confidence,
            }
        )

    max_abs = max((abs(row["momentum_log_ratio"]) for row in raw_rows), default=0.0)
    rows: List[Dict[str, Any]] = []
    for row in raw_rows:
        if max_abs <= 0:
            score_value = 50.0
        else:
            score_value = 50.0 + 50.0 * (row["momentum_log_ratio"] / max_abs)
        payload = _derived_score_payload(
            row["reference_id"],
            TREND_MOMENTUM_SCORE,
            score_value,
            row["confidence"],
            [row["recent"], row["baseline"]],
        )
        payload["score_components"]["momentum_log_ratio"] = round(row["momentum_log_ratio"], 8)
        payload["score_components"]["recent_relative_to_anchor"] = row["recent"].get("relative_to_anchor")
        payload["score_components"]["baseline_relative_to_anchor"] = row["baseline"].get("relative_to_anchor")
        payload["score_components"]["baseline_timeframe"] = row["baseline"].get("timeframe")
        rows.append(payload)
    return _rank_scores(rows)


def _derived_score_payload(
    reference_id: Any,
    score_name: str,
    score_value: float,
    confidence: str,
    contributing_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    first = contributing_rows[0]
    snapshot_ids = [row.get("snapshot_id") for row in contributing_rows if row.get("snapshot_id") is not None]
    return {
        "pokemon_reference_id": reference_id,
        "pokemon_name": first.get("pokemon_name"),
        "query_term": first.get("query_term"),
        "source_name": first.get("source_name"),
        "score_name": score_name,
        "score_value": round(_bounded(score_value), 4),
        "normalized_rank": None,
        "confidence": confidence if confidence in {"high", "medium", "low", "insufficient"} else "medium",
        "scoring_version": TREND_SCORING_VERSION,
        "primary_snapshot_id": snapshot_ids[0] if snapshot_ids else None,
        "contributing_snapshot_ids": snapshot_ids,
        "score_components": {
            "timeframes": [row.get("timeframe") for row in contributing_rows],
            "measurement_note": "Relative Google Trends search interest; not absolute search volume.",
        },
    }


def _rank_scores(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = sorted(rows, key=lambda row: row.get("score_value") or 0.0, reverse=True)
    for rank, row in enumerate(ranked, start=1):
        row["normalized_rank"] = rank
    return ranked


def _by_reference(rows: List[Dict[str, Any]]) -> Dict[Any, Dict[str, Any]]:
    return {row.get("pokemon_reference_id"): row for row in rows if row.get("pokemon_reference_id") is not None}


def _top_scores(rows: List[Dict[str, Any]], *, score_field: str, limit: int) -> List[Dict[str, Any]]:
    return sorted(_score_preview(rows, score_field), key=lambda item: item.get("score") or 0.0, reverse=True)[:limit]


def _score_preview(rows: List[Dict[str, Any]], score_field: str) -> List[Dict[str, Any]]:
    return [
        {
            "pokemon_name": row.get("pokemon_name"),
            "query_term": row.get("query_term"),
            "score": row.get(score_field),
            "rank": row.get("normalized_rank"),
            "confidence": row.get("confidence"),
            "timeframe": row.get("timeframe"),
            "momentum_log_ratio": (row.get("score_components") or {}).get("momentum_log_ratio"),
        }
        for row in rows
    ]


def _dedupe_preview(rows: List[Dict[str, Any]], limit: int = 50) -> List[Dict[str, Any]]:
    seen: set[Any] = set()
    preview: List[Dict[str, Any]] = []
    for row in rows:
        key = row.get("pokemon_reference_id") or (row.get("pokemon_name"), row.get("query_term"))
        if key in seen:
            continue
        seen.add(key)
        preview.append(
            {
                "pokemon_name": row.get("pokemon_name"),
                "query_term": row.get("query_term"),
                "timeframe": row.get("timeframe"),
                "raw_interest_value": row.get("raw_interest_value"),
                "confidence": row.get("extraction_confidence"),
                "is_ambiguous": row.get("is_ambiguous"),
            }
        )
        if len(preview) >= limit:
            break
    return preview


def _confidence_for_timeframe_row(row: Dict[str, Any]) -> str:
    confidence = row.get("extraction_confidence") or "medium"
    if confidence == "high" and row.get("is_ambiguous"):
        return "low"
    if confidence in {"high", "medium", "low", "insufficient"}:
        return confidence
    return "medium"


def _combined_confidence(*rows: Dict[str, Any]) -> str:
    order = {"high": 3, "medium": 2, "low": 1, "insufficient": 0}
    weakest = min((order.get(str(row.get("confidence") or "medium"), 2) for row in rows), default=2)
    for label, score in order.items():
        if score == weakest:
            return label
    return "medium"


def _downgrade_confidence(confidence: Any) -> str:
    if confidence == "high":
        return "medium"
    if confidence in {"medium", "low", "insufficient"}:
        return str(confidence)
    return "medium"


def _primary_confidence(rows: List[Dict[str, Any]]) -> str:
    counts: Dict[str, int] = {}
    for row in rows:
        confidence = str(row.get("confidence") or "unknown")
        counts[confidence] = counts.get(confidence, 0) + 1
    if not counts:
        return "insufficient"
    return max(counts.items(), key=lambda item: item[1])[0]


def _bounded(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
