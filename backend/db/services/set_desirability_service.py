"""Read set-level intrinsic desirability inputs for RIP scoring."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.db.clients.supabase_client import public_read_client

logger = logging.getLogger(__name__)

SUMMARY_TABLE = "pokemon_set_hit_desirability_summaries"
SOURCE_METRIC = "weighted_average_hit_desirability_score"
NEUTRAL_DESIRABILITY_SCORE = 50.0


def _to_optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _fallback_payload(reason: str) -> Dict[str, Any]:
    return {
        "desirability_score": NEUTRAL_DESIRABILITY_SCORE,
        "weighted_average_hit_desirability_score": None,
        "desirability_source_table": SUMMARY_TABLE,
        "desirability_source_metric": SOURCE_METRIC,
        "desirability_scoring_version": "pokemon_set_hit_desirability_v1",
        "desirability_is_fallback": True,
        "desirability_fallback_reason": reason,
    }


def _build_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    score = _to_optional_float(row.get(SOURCE_METRIC))
    if score is None or not (0.0 <= score <= 100.0):
        return _fallback_payload("missing_or_invalid_set_hit_desirability_summary_score")

    aggregation_version = row.get("aggregation_version") or "pokemon_set_hit_desirability_v1"
    hit_policy_version = row.get("hit_policy_version")
    composite_scoring_version = row.get("composite_scoring_version")
    scoring_parts = [
        str(part)
        for part in (aggregation_version, hit_policy_version, composite_scoring_version)
        if part
    ]

    return {
        "desirability_score": score,
        "weighted_average_hit_desirability_score": score,
        "desirability_source_summary_id": row.get("id"),
        "desirability_source_table": SUMMARY_TABLE,
        "desirability_source_metric": SOURCE_METRIC,
        "desirability_scoring_version": "|".join(scoring_parts) if scoring_parts else str(aggregation_version),
        "desirability_is_fallback": False,
        "desirability_fallback_reason": None,
        "aggregation_version": aggregation_version,
        "hit_policy_version": hit_policy_version,
        "composite_scoring_version": composite_scoring_version,
        "fan_popularity_snapshot_id": row.get("fan_popularity_snapshot_id"),
        "built_at": row.get("built_at"),
    }


def get_latest_set_hit_desirability_score(
    *,
    set_canonical_key: Optional[str] = None,
    set_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the latest set-level hit-card intrinsic desirability score.

    Missing rows return neutral 50 so the canonical 45/25/20/10 RIP formula
    remains stable while desirability coverage is rolling out.
    """

    canonical_key = (set_canonical_key or "").strip()
    resolved_set_id = (set_id or "").strip()
    if not canonical_key and not resolved_set_id:
        logger.warning("[set-desirability] missing set key; using neutral desirability fallback")
        return _fallback_payload("missing_set_identifier")

    try:
        query = public_read_client.table(SUMMARY_TABLE).select(
            "id,set_id,set_name,set_canonical_key,aggregation_version,hit_policy_version,"
            "composite_scoring_version,fan_popularity_snapshot_id,"
            "weighted_average_hit_desirability_score,built_at,updated_at"
        )
        if canonical_key:
            query = query.eq("set_canonical_key", canonical_key)
        else:
            query = query.eq("set_id", resolved_set_id)

        response = query.order("built_at", desc=True).limit(1).execute()
    except Exception as exc:
        logger.warning(
            "[set-desirability] failed to load set hit desirability summary set_canonical_key=%s set_id=%s: %s",
            canonical_key or None,
            resolved_set_id or None,
            exc,
        )
        return _fallback_payload("set_hit_desirability_summary_query_failed")

    row = (response.data or [None])[0] if response is not None else None
    if not isinstance(row, dict):
        logger.warning(
            "[set-desirability] no set hit desirability summary set_canonical_key=%s set_id=%s; using neutral fallback",
            canonical_key or None,
            resolved_set_id or None,
        )
        return _fallback_payload("missing_set_hit_desirability_summary")

    payload = _build_payload(row)
    if payload.get("desirability_is_fallback"):
        logger.warning(
            "[set-desirability] invalid set hit desirability summary set_canonical_key=%s set_id=%s summary_id=%s; using neutral fallback",
            canonical_key or None,
            resolved_set_id or None,
            row.get("id"),
        )
    return payload
