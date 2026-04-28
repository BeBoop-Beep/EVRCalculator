"""Service for RIP Statistics target discovery and default target selection."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from backend.db.clients.supabase_client import public_read_client

logger = logging.getLogger(__name__)

DEFAULT_TARGETS_LIMIT = 100
MAX_TARGETS_LIMIT = 200
MIN_LIMIT = 1


class ExploreRipStatisticsTargetsError(Exception):
    """Structured error for RIP Statistics target discovery."""

    def __init__(self, status_code: int, message: str, code: str):
        self.status_code = status_code
        self.message = message
        self.code = code
        super().__init__(message)


def _sanitize_limit(value: Any, *, default: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < MIN_LIMIT:
        return MIN_LIMIT
    if parsed > max_value:
        return max_value
    return parsed


def _to_optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _build_sort_key(row: Dict[str, Any]) -> tuple[int, float, str]:
    placeholder = bool(row.get("pack_score_is_placeholder"))
    pack_score = _to_optional_float(row.get("pack_score"))
    run_at = str(row.get("run_at") or "")
    return (
        1 if placeholder else 0,
        -(pack_score if pack_score is not None else float("-inf")),
        run_at,
    )


def get_rip_statistics_targets_payload(limit: Any = DEFAULT_TARGETS_LIMIT) -> Dict[str, Any]:
    """Return available RIP targets and the best default target from persisted data."""
    total_started = time.perf_counter()
    clamped_limit = _sanitize_limit(limit, default=DEFAULT_TARGETS_LIMIT, max_value=MAX_TARGETS_LIMIT)

    warnings: List[str] = []
    sources: Dict[str, str] = {}

    query_started = time.perf_counter()
    try:
        targets_result = (
            public_read_client.table("simulation_latest_by_target")
            .select(
                "target_type,target_id,run_at,pack_score,profit_score,safety_score,stability_score,"
                "pack_score_is_placeholder,pack_cost,mean_value,median_value,roi_percent,prob_profit,prob_big_hit"
            )
            .eq("target_type", "set")
            .order("pack_score", desc=True)
            .order("run_at", desc=True)
            .limit(clamped_limit)
            .execute()
        )
        raw_rows = [row for row in (targets_result.data or []) if row.get("target_id")]
        sources["simulation_latest_by_target"] = "OK"
    except Exception as exc:
        logger.exception("[rip-statistics-targets] simulation_latest_by_target query failed")
        raise ExploreRipStatisticsTargetsError(
            status_code=500,
            message="Failed to load RIP Statistics targets",
            code="TARGETS_QUERY_FAILED",
        ) from exc
    query_ms = (time.perf_counter() - query_started) * 1000

    if not raw_rows:
        raise ExploreRipStatisticsTargetsError(
            status_code=404,
            message="No RIP Statistics targets found",
            code="TARGETS_NOT_FOUND",
        )

    sorted_rows = sorted(raw_rows, key=_build_sort_key)

    set_lookup: Dict[str, Dict[str, Any]] = {}
    era_lookup: Dict[str, Dict[str, Any]] = {}

    set_ids = sorted({str(row.get("target_id")) for row in sorted_rows if row.get("target_id")})
    if set_ids:
        set_started = time.perf_counter()
        try:
            set_result = (
                public_read_client.table("sets")
                .select("id,name,release_date,era_id")
                .in_("id", set_ids)
                .execute()
            )
            set_lookup = {
                str(row.get("id")): row
                for row in (set_result.data or [])
                if row.get("id") is not None
            }
            sources["sets"] = "OK"
        except Exception as exc:
            logger.warning("[rip-statistics-targets] set enrichment failed: %s", exc)
            warnings.append("Failed to load set metadata for one or more RIP targets")
            sources["sets"] = "FAILED"
        set_ms = (time.perf_counter() - set_started) * 1000
    else:
        set_ms = 0.0
        sources["sets"] = "SKIPPED"

    era_ids = sorted(
        {
            str(row.get("era_id"))
            for row in set_lookup.values()
            if row.get("era_id") is not None
        }
    )
    if era_ids:
        era_started = time.perf_counter()
        try:
            era_result = (
                public_read_client.table("eras")
                .select("id,name")
                .in_("id", era_ids)
                .execute()
            )
            era_lookup = {
                str(row.get("id")): row
                for row in (era_result.data or [])
                if row.get("id") is not None
            }
            sources["eras"] = "OK"
        except Exception as exc:
            logger.warning("[rip-statistics-targets] era enrichment failed: %s", exc)
            warnings.append("Failed to load era metadata for one or more RIP targets")
            sources["eras"] = "FAILED"
        era_ms = (time.perf_counter() - era_started) * 1000
    else:
        era_ms = 0.0
        sources["eras"] = "SKIPPED"

    targets: List[Dict[str, Any]] = []
    for row in sorted_rows:
        target_id = str(row.get("target_id"))
        set_row = set_lookup.get(target_id) or {}
        era_row = era_lookup.get(str(set_row.get("era_id"))) if set_row.get("era_id") is not None else None
        targets.append(
            {
                "target_type": str(row.get("target_type") or "set"),
                "target_id": target_id,
                "name": str(set_row.get("name") or target_id),
                "era": era_row.get("name") if era_row else None,
                "pack_score": row.get("pack_score"),
                "profit_score": row.get("profit_score"),
                "safety_score": row.get("safety_score"),
                "stability_score": row.get("stability_score"),
                "pack_cost": row.get("pack_cost"),
                "mean_value": row.get("mean_value"),
                "median_value": row.get("median_value"),
                "roi_percent": row.get("roi_percent"),
                "prob_profit": row.get("prob_profit"),
                "prob_big_hit": row.get("prob_big_hit"),
                "run_at": row.get("run_at"),
            }
        )

    default_target_row = None
    for target in targets:
        if _to_optional_float(target.get("pack_score")) is not None:
            default_target_row = target
            break
    if default_target_row is None:
        default_target_row = targets[0]

    total_ms = (time.perf_counter() - total_started) * 1000
    return {
        "targets": targets,
        "default_target": {
            "target_type": default_target_row["target_type"],
            "target_id": default_target_row["target_id"],
        },
        "meta": {
            "sources": sources,
            "warnings": warnings,
            "timings": {
                "targets_query_ms": round(query_ms, 2),
                "set_enrichment_ms": round(set_ms, 2),
                "era_enrichment_ms": round(era_ms, 2),
                "total_backend_ms": round(total_ms, 2),
            },
            "request": {
                "limit": clamped_limit,
            },
        },
    }