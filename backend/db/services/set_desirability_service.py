"""Read set-level Opening Desirability inputs for RIP scoring."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.db.clients.supabase_client import public_read_client

logger = logging.getLogger(__name__)

SUMMARY_TABLE = "pokemon_set_hit_desirability_summaries"
OPENING_DESIRABILITY_VIEW = "pokemon_set_opening_desirability_latest"
OPENING_DESIRABILITY_SOURCE_METRIC = "opening_desirability_score"
COLLECTOR_FALLBACK_SOURCE_METRIC = "collector_appeal_score"
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
        "opening_desirability_score": None,
        "collector_appeal_score": None,
        "weighted_average_hit_desirability_score": None,
        "desirability_source_table": OPENING_DESIRABILITY_VIEW,
        "desirability_source_metric": OPENING_DESIRABILITY_SOURCE_METRIC,
        "desirability_scoring_version": "opening_desirability_v1",
        "desirability_is_fallback": True,
        "desirability_fallback_reason": reason,
        "rip_desirability_source": "missing",
    }


def _build_legacy_payload(row: Dict[str, Any]) -> Dict[str, Any]:
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
        "rip_desirability_source": "legacy_set_hit_desirability",
        "aggregation_version": aggregation_version,
        "hit_policy_version": hit_policy_version,
        "composite_scoring_version": composite_scoring_version,
        "fan_popularity_snapshot_id": row.get("fan_popularity_snapshot_id"),
        "built_at": row.get("built_at"),
    }


def _build_opening_desirability_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    opening_score = _to_optional_float(row.get("opening_desirability_score"))
    collector_score = _to_optional_float(row.get("collector_appeal_score"))

    if opening_score is not None and 0.0 <= opening_score <= 100.0:
        desirability_score = opening_score
        source_metric = OPENING_DESIRABILITY_SOURCE_METRIC
        rip_source = "opening_desirability"
        is_fallback = False
        fallback_reason = None
    elif collector_score is not None and 0.0 <= collector_score <= 100.0:
        desirability_score = collector_score
        source_metric = COLLECTOR_FALLBACK_SOURCE_METRIC
        rip_source = "collector_appeal_fallback"
        is_fallback = True
        fallback_reason = "collector_appeal_fallback_missing_opening_desirability"
    else:
        return _fallback_payload("missing_opening_desirability_and_collector_appeal")

    return {
        "desirability_score": desirability_score,
        "opening_desirability_score": opening_score,
        "opening_desirability_rank": row.get("opening_desirability_rank"),
        "collector_appeal_score": collector_score,
        "collector_appeal_rank": row.get("collector_appeal_rank"),
        "chase_appeal_score": _to_optional_float(row.get("chase_appeal_score")),
        "chase_appeal_rank": row.get("chase_appeal_rank"),
        "chase_appeal_data_quality": row.get("chase_appeal_data_quality"),
        "opening_desirability_display_status": row.get("opening_desirability_display_status"),
        "opening_desirability_summary": row.get("opening_desirability_summary"),
        "public_tooltip_copy_json": row.get("public_tooltip_copy_json") or {},
        "desirability_source_summary_id": row.get("set_id"),
        "desirability_source_table": OPENING_DESIRABILITY_VIEW,
        "desirability_source_metric": source_metric,
        "desirability_scoring_version": row.get("scoring_version") or "opening_desirability_v1",
        "desirability_is_fallback": is_fallback,
        "desirability_fallback_reason": fallback_reason,
        "rip_desirability_source": rip_source,
        "built_at": row.get("built_at"),
    }


def get_latest_opening_desirability_for_rip_score(
    *,
    set_canonical_key: Optional[str] = None,
    set_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the latest Opening Desirability payload for RIP scoring.

    Missing rows return neutral 50 with ``rip_desirability_source='missing'``.
    Collector-only rows use Collector Appeal as a temporary fallback rather than
    treating missing Chase Appeal as zero.
    """

    canonical_key = (set_canonical_key or "").strip()
    resolved_set_id = (set_id or "").strip()
    if not canonical_key and not resolved_set_id:
        logger.warning("[opening-desirability] missing set key; using neutral desirability fallback")
        return _fallback_payload("missing_set_identifier")

    try:
        query = public_read_client.table(OPENING_DESIRABILITY_VIEW).select(
            "set_id,set_name,set_canonical_key,opening_desirability_score,"
            "opening_desirability_rank,collector_appeal_score,collector_appeal_rank,"
            "chase_appeal_score,chase_appeal_rank,chase_appeal_data_quality,"
            "opening_desirability_display_status,opening_desirability_summary,"
            "public_tooltip_copy_json,scoring_version,built_at"
        )
        if canonical_key:
            query = query.eq("set_canonical_key", canonical_key)
        else:
            query = query.eq("set_id", resolved_set_id)

        response = query.order("built_at", desc=True).limit(1).execute()
    except Exception as exc:
        logger.warning(
            "[opening-desirability] failed to load set Opening Desirability set_canonical_key=%s set_id=%s: %s",
            canonical_key or None,
            resolved_set_id or None,
            exc,
        )
        return _fallback_payload("opening_desirability_query_failed")

    row = (response.data or [None])[0] if response is not None else None
    if not isinstance(row, dict):
        logger.warning(
            "[opening-desirability] no Opening Desirability row set_canonical_key=%s set_id=%s; using neutral fallback",
            canonical_key or None,
            resolved_set_id or None,
        )
        return _fallback_payload("missing_opening_desirability_row")

    return _build_opening_desirability_payload(row)


def get_latest_set_hit_desirability_score(
    *,
    set_canonical_key: Optional[str] = None,
    set_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the latest Opening Desirability score for RIP scoring.

    The historical function name is kept for call-site compatibility.
    """
    opening_payload = get_latest_opening_desirability_for_rip_score(
        set_canonical_key=set_canonical_key,
        set_id=set_id,
    )
    if opening_payload.get("rip_desirability_source") != "missing":
        return opening_payload

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
        return opening_payload

    row = (response.data or [None])[0] if response is not None else None
    if not isinstance(row, dict):
        return opening_payload

    payload = _build_legacy_payload(row)
    if payload.get("desirability_is_fallback"):
        logger.warning(
            "[set-desirability] invalid set hit desirability summary set_canonical_key=%s set_id=%s summary_id=%s; using neutral fallback",
            canonical_key or None,
            resolved_set_id or None,
            row.get("id"),
        )
    return payload
