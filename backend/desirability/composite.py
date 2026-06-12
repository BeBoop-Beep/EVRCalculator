from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.desirability.google_trends import (
    DEFAULT_GEO,
    QUERY_TYPE_SEARCH_TERM,
    SOURCE_NAME as GOOGLE_TRENDS_SOURCE_NAME,
)
from backend.desirability.normalization import SCORING_VERSION as FAN_SCORING_VERSION
from backend.desirability.trends_normalization import (
    RECENT_TIMEFRAME,
    RECENT_TREND_SCORE,
    TREND_SCORING_VERSION,
    normalize_timeframe_rows,
)


FAVORITEPOKEMON_SOURCE_NAME = "favoritepokemon"
COMPOSITE_SCORING_VERSION = "pokemon_desirability_composite_v1"
EXPECTED_POKEMON_COUNT = 1025
FAN_WEIGHT = 0.75
CURRENT_TREND_WEIGHT = 0.25
PYTRENDS_PROVIDER_NAME = "pytrends"
RECENT_WINDOW_ROLE = "recent"
CAPTURED_RELATIVE_SEARCH_INTEREST_STATUS = "captured_relative_search_interest"


logger = logging.getLogger(__name__)


def build_composite_scores(
    *,
    references: Iterable[Dict[str, Any]],
    fan_scores: Iterable[Dict[str, Any]],
    fan_snapshot_id: Any,
    current_trend_scores: Iterable[Dict[str, Any]],
    current_trend_snapshot_id: Any = None,
    scoring_version: str = COMPOSITE_SCORING_VERSION,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    fan_score_rows = list(fan_scores)
    current_trend_score_rows = list(current_trend_scores)
    references_by_id = {
        reference.get("id"): reference
        for reference in references
        if reference.get("id") is not None
    }
    trend_by_ref = {
        row.get("pokemon_reference_id"): row
        for row in current_trend_score_rows
        if row.get("pokemon_reference_id") is not None
    }

    rows: List[Dict[str, Any]] = []
    for fan in fan_score_rows:
        reference_id = fan.get("pokemon_reference_id")
        if reference_id is None:
            continue

        reference = references_by_id.get(reference_id, {})
        trend = trend_by_ref.get(reference_id)
        fan_score = _as_float(fan.get("normalized_score"))
        if fan_score is None:
            continue

        current_trend_score = _as_float((trend or {}).get("relative_search_interest_score"))
        trend_snapshot_id = (trend or {}).get("primary_snapshot_id") or (trend or {}).get("snapshot_id")
        if trend_snapshot_id is None:
            trend_snapshot_id = current_trend_snapshot_id
        trend_missing = current_trend_score is None
        if trend_missing:
            desirability_score = fan_score
        else:
            desirability_score = FAN_WEIGHT * fan_score + CURRENT_TREND_WEIGHT * current_trend_score

        rounded_score = round(_bounded(desirability_score), 4)
        rows.append(
            {
                "pokemon_reference_id": reference_id,
                "pokedex_number": fan.get("pokedex_number") or reference.get("pokedex_number"),
                "pokemon_name": (
                    fan.get("pokemon_name")
                    or reference.get("display_name")
                    or reference.get("canonical_name")
                ),
                "fan_popularity_score": round(_bounded(fan_score), 4),
                "fan_popularity_rank": fan.get("normalized_rank"),
                "fan_popularity_snapshot_id": fan_snapshot_id,
                "current_trend_score": round(_bounded(current_trend_score), 4) if current_trend_score is not None else None,
                "current_trend_rank": (trend or {}).get("normalized_rank"),
                "current_trend_snapshot_id": trend_snapshot_id,
                "desirability_score": rounded_score,
                "desirability_rank": None,
                "desirability_tier": assign_composite_tier(rounded_score),
                "scoring_version": scoring_version,
                "score_components_json": {
                    "formula": "0.75 * fan_popularity_score + 0.25 * current_trend_score",
                    "fan_popularity_weight": FAN_WEIGHT,
                    "current_trend_weight": CURRENT_TREND_WEIGHT,
                    "fan_popularity_score": round(_bounded(fan_score), 4),
                    "current_trend_score": round(_bounded(current_trend_score), 4)
                    if current_trend_score is not None
                    else None,
                    "current_trend_snapshot_id": trend_snapshot_id,
                    "current_trend_query_term": (trend or {}).get("query_term"),
                    "current_trend_raw_interest_value": (trend or {}).get("raw_interest_value"),
                    "current_trend_relative_to_anchor": (trend or {}).get("relative_to_anchor"),
                    "trend_missing_fallback": trend_missing,
                    "current_trend_label": "Current Trend Score / 30-Day Search Interest Score",
                    "measurement_note": (
                        "Google Trends component is normalized 30-day relative search interest, "
                        "not absolute search volume, long-term popularity, or trend momentum."
                    ),
                },
            }
        )

    ranked = sorted(
        rows,
        key=lambda row: (
            row.get("desirability_score") or 0.0,
            row.get("fan_popularity_score") or 0.0,
            row.get("current_trend_score") or -1.0,
            -int(row.get("pokedex_number") or 0),
        ),
        reverse=True,
    )
    for rank, row in enumerate(ranked, start=1):
        row["desirability_rank"] = rank

    return ranked, {
        "total_pokemon_processed": len(ranked),
        "fan_scores_found": len([row for row in fan_score_rows if row.get("pokemon_reference_id") is not None]),
        "trend_scores_found": len(trend_by_ref),
        "missing_trend_count": sum(1 for row in ranked if (row.get("score_components_json") or {}).get("trend_missing_fallback")),
        "trend_rows_by_snapshot_id": _counts_by_snapshot(ranked, "current_trend_snapshot_id"),
        "scoring_version": scoring_version,
    }


def build_composite_report(
    *,
    repository: Any,
    dry_run: bool,
    min_coverage: float = 0.95,
    expected_reference_count: int = EXPECTED_POKEMON_COUNT,
) -> Dict[str, Any]:
    references = repository.list_pokemon_references()
    fan_selection = select_latest_complete_fan_scores(
        repository=repository,
        min_coverage=min_coverage,
        expected_reference_count=expected_reference_count,
    )
    if fan_selection is None:
        return {
            "status": "missing_complete_favoritepokemon_scores",
            "dry_run": dry_run,
            "min_coverage": min_coverage,
            "scoring_version": COMPOSITE_SCORING_VERSION,
        }

    trend_selection = select_latest_current_trend_scores_by_pokemon(
        repository=repository,
        min_coverage=min_coverage,
        expected_reference_count=expected_reference_count,
    )
    if trend_selection is None:
        return {
            "status": "missing_complete_current_30_day_trend_scores",
            "dry_run": dry_run,
            "min_coverage": min_coverage,
            "scoring_version": COMPOSITE_SCORING_VERSION,
            "measurement_note": "V1 requires recent_trend_score derived from today 1-m only.",
        }

    fan_snapshot, fan_scores = fan_selection
    trend_snapshots, trend_scores, trend_selection_summary = trend_selection
    composite_scores, summary = build_composite_scores(
        references=references,
        fan_scores=fan_scores,
        fan_snapshot_id=fan_snapshot["id"],
        current_trend_scores=trend_scores,
    )
    inserted_rows = [] if dry_run else repository.insert_desirability_composite_scores(composite_scores)
    trend_snapshot_counts = _counts_by_snapshot(composite_scores, "current_trend_snapshot_id")
    missing_trend_count = summary["missing_trend_count"]

    logger.info("Selected fan popularity snapshot id=%s", fan_snapshot["id"])
    logger.info(
        "Valid current trend snapshot ids considered=%s",
        [snapshot.get("id") for snapshot in trend_snapshots],
    )
    logger.info("Current trend rows used by snapshot id=%s", trend_snapshot_counts)
    logger.info("Missing current trend rows/fallbacks=%s", missing_trend_count)

    return {
        "status": "dry_run" if dry_run else "committed",
        "dry_run": dry_run,
        "fan_popularity_snapshot_id": fan_snapshot["id"],
        "valid_current_trend_snapshot_ids": [snapshot.get("id") for snapshot in trend_snapshots],
        "scoring_version": COMPOSITE_SCORING_VERSION,
        "inserted_composite_scores": len(inserted_rows),
        "diagnostics": {
            **summary,
            **trend_selection_summary,
            "trend_rows_by_snapshot_id": trend_snapshot_counts,
            "top_25_by_fan_popularity": _top_rows(composite_scores, "fan_popularity_score", "fan_popularity_rank"),
            "top_25_by_current_trend": _top_rows(composite_scores, "current_trend_score", "current_trend_rank"),
            "top_25_by_composite_desirability": _top_rows(
                composite_scores,
                "desirability_score",
                "desirability_rank",
            ),
            "biggest_trend_boost_examples": _biggest_trend_boosts(composite_scores),
        },
        "guardrails": {
            "google_trends_label": "Current 30-day relative search interest.",
            "measurement_note": "No absolute search volume or long-term search popularity claim is made.",
            "not_modified": [
                "card-hit mapping",
                "RIP Score",
                "Opening Experience",
                "frontend UI",
                "simulations",
            ],
        },
    }


def select_latest_complete_fan_scores(
    *,
    repository: Any,
    min_coverage: float,
    expected_reference_count: int,
) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    snapshots = repository.list_latest_desirability_source_snapshots(
        source_name=FAVORITEPOKEMON_SOURCE_NAME,
        limit=10,
    )
    for snapshot in snapshots:
        scores = repository.list_desirability_scores_for_snapshot(
            snapshot["id"],
            scoring_version=FAN_SCORING_VERSION,
        )
        if _coverage(scores, expected_reference_count) >= min_coverage:
            return snapshot, scores
    return None


def select_latest_complete_current_trend_scores(
    *,
    repository: Any,
    min_coverage: float,
    expected_reference_count: int,
) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    snapshots = repository.list_usable_trend_snapshots(
        source_name=GOOGLE_TRENDS_SOURCE_NAME,
        provider_name=None,
        geo="US",
        timeframe="today 1-m",
        limit=10,
    )
    for snapshot in snapshots:
        scores = repository.list_trend_scores_for_snapshot(
            primary_snapshot_id=snapshot["id"],
            score_name=RECENT_TREND_SCORE,
            scoring_version=TREND_SCORING_VERSION,
        )
        if _coverage(scores, expected_reference_count) >= min_coverage:
            return snapshot, scores
    return None


def select_latest_current_trend_scores_by_pokemon(
    *,
    repository: Any,
    min_coverage: float,
    expected_reference_count: int,
) -> Optional[Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]]:
    snapshots = repository.list_valid_current_trend_source_snapshots(
        source_name=GOOGLE_TRENDS_SOURCE_NAME,
        provider_name=PYTRENDS_PROVIDER_NAME,
        geo=DEFAULT_GEO,
        timeframe=RECENT_TIMEFRAME,
        window_role=RECENT_WINDOW_ROLE,
        query_type=QUERY_TYPE_SEARCH_TERM,
        status=CAPTURED_RELATIVE_SEARCH_INTEREST_STATUS,
        limit=50,
    )
    if not snapshots:
        return None

    latest_rows_by_ref: Dict[Any, Dict[str, Any]] = {}
    rows_seen_by_snapshot: Dict[Any, int] = {}
    for snapshot in snapshots:
        snapshot_id = snapshot.get("id")
        rows = repository.list_trend_source_rows_for_snapshot(snapshot_id)
        usable_rows = [
            row
            for row in rows
            if row.get("pokemon_reference_id") is not None
            and _as_float(row.get("relative_to_anchor")) is not None
        ]
        rows_seen_by_snapshot[snapshot_id] = len(usable_rows)
        for row in usable_rows:
            reference_id = row.get("pokemon_reference_id")
            if reference_id not in latest_rows_by_ref:
                latest_rows_by_ref[reference_id] = row

    latest_rows = list(latest_rows_by_ref.values())
    if _coverage(latest_rows, expected_reference_count) < min_coverage:
        return None

    normalized_rows, normalization_summary = normalize_timeframe_rows(latest_rows)
    source_row_by_ref = {
        row.get("pokemon_reference_id"): row
        for row in latest_rows
        if row.get("pokemon_reference_id") is not None
    }
    current_trend_scores: List[Dict[str, Any]] = []
    for normalized in normalized_rows:
        source_row = source_row_by_ref.get(normalized.get("pokemon_reference_id"), {})
        current_trend_scores.append(
            {
                "pokemon_reference_id": normalized.get("pokemon_reference_id"),
                "source_name": normalized.get("source_name") or GOOGLE_TRENDS_SOURCE_NAME,
                "score_name": RECENT_TREND_SCORE,
                "relative_search_interest_score": normalized.get("normalized_relative_search_interest_score"),
                "normalized_rank": normalized.get("normalized_rank"),
                "confidence": normalized.get("confidence"),
                "scoring_version": TREND_SCORING_VERSION,
                "primary_snapshot_id": source_row.get("snapshot_id") or normalized.get("snapshot_id"),
                "contributing_snapshot_ids": [source_row.get("snapshot_id") or normalized.get("snapshot_id")],
                "query_term": source_row.get("query_term") or normalized.get("query_term"),
                "raw_interest_value": source_row.get("raw_interest_value"),
                "relative_to_anchor": source_row.get("relative_to_anchor"),
                "score_components_json": {
                    "source": "latest_valid_today_1m_source_row_per_pokemon",
                    "measurement_note": (
                        "Current Trend Score is normalized from the latest valid per-Pokemon "
                        "today 1-m Google Trends source row. It is relative search interest, "
                        "not absolute search volume."
                    ),
                },
            }
        )

    return snapshots, current_trend_scores, {
        "valid_current_trend_snapshot_ids_considered": [snapshot.get("id") for snapshot in snapshots],
        "trend_source_rows_seen_by_snapshot_id": {str(key): value for key, value in rows_seen_by_snapshot.items()},
        "latest_trend_rows_selected": len(latest_rows),
        "latest_trend_rows_normalization_summary": normalization_summary,
    }


def assign_composite_tier(score: float) -> str:
    bounded = _bounded(score)
    if bounded >= 90:
        return "S"
    if bounded >= 75:
        return "A"
    if bounded >= 55:
        return "B"
    if bounded >= 35:
        return "C"
    if bounded >= 15:
        return "D"
    return "F"


def _coverage(rows: Iterable[Dict[str, Any]], expected_reference_count: int) -> float:
    if expected_reference_count <= 0:
        return 0.0
    reference_ids = {row.get("pokemon_reference_id") for row in rows if row.get("pokemon_reference_id") is not None}
    return len(reference_ids) / expected_reference_count


def _counts_by_snapshot(rows: Iterable[Dict[str, Any]], snapshot_key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        snapshot_id = row.get(snapshot_key)
        if snapshot_id is None:
            continue
        key = str(snapshot_id)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _top_rows(rows: List[Dict[str, Any]], score_key: str, rank_key: str, limit: int = 25) -> List[Dict[str, Any]]:
    scored = [row for row in rows if row.get(score_key) is not None]
    return [
        {
            "pokemon_reference_id": row.get("pokemon_reference_id"),
            "pokedex_number": row.get("pokedex_number"),
            "pokemon_name": row.get("pokemon_name"),
            "score": row.get(score_key),
            "rank": row.get(rank_key),
        }
        for row in sorted(scored, key=lambda item: item.get(score_key) or 0.0, reverse=True)[:limit]
    ]


def _biggest_trend_boosts(rows: List[Dict[str, Any]], limit: int = 25) -> List[Dict[str, Any]]:
    boosted = [
        {
            "pokemon_reference_id": row.get("pokemon_reference_id"),
            "pokedex_number": row.get("pokedex_number"),
            "pokemon_name": row.get("pokemon_name"),
            "fan_popularity_score": row.get("fan_popularity_score"),
            "current_trend_score": row.get("current_trend_score"),
            "trend_minus_fan": round(
                float(row.get("current_trend_score")) - float(row.get("fan_popularity_score")),
                4,
            ),
            "desirability_score": row.get("desirability_score"),
            "desirability_rank": row.get("desirability_rank"),
        }
        for row in rows
        if row.get("current_trend_score") is not None and row.get("fan_popularity_score") is not None
    ]
    return sorted(boosted, key=lambda row: row["trend_minus_fan"], reverse=True)[:limit]


def _bounded(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
