"""Service for RIP Statistics target discovery and default target selection."""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Dict, Iterable, List, Optional

from backend.db.clients.supabase_client import public_read_client
from backend.db.services.rip_desirability_comparison import build_rip_desirability_comparison_payload
from backend.interpretation.rips import build_rip_interpretation

logger = logging.getLogger(__name__)

DEFAULT_TARGETS_LIMIT = 100
MAX_TARGETS_LIMIT = 200
MIN_LIMIT = 1

_BIGGEST_UPSIDE_P95_CAP = 5.0
_BIGGEST_UPSIDE_P99_CAP = 10.0
_BIGGEST_UPSIDE_P95_WEIGHT = 0.70
_BIGGEST_UPSIDE_P99_WEIGHT = 0.30
_SET_VALUE_HISTORY_SCOPE = "standard"
_SET_VALUE_HISTORY_CHUNK_SIZE = 50
_SET_VALUE_HISTORY_DAYS_PER_SET_LIMIT = 45


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


def _to_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _chunks(values: List[str], size: int) -> Iterable[List[str]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _load_current_checklist_set_value_lookup(
    set_ids: List[str],
    *,
    sources: Dict[str, str],
    warnings: List[str],
) -> Dict[str, Dict[str, Any]]:
    """Load latest canonical checklist set value rows for Explore validation targets."""

    unique_set_ids = sorted({_to_optional_str(set_id) for set_id in set_ids if _to_optional_str(set_id)})
    if not unique_set_ids:
        sources["pokemon_set_value_daily_history"] = "SKIPPED"
        return {}

    started = time.perf_counter()
    latest_by_set_id: Dict[str, Dict[str, Any]] = {}
    try:
        for chunk in _chunks(unique_set_ids, _SET_VALUE_HISTORY_CHUNK_SIZE):
            result = (
                public_read_client.table("pokemon_set_value_daily_history")
                .select("set_id,snapshot_date,set_value,priced_card_count,total_card_count,source")
                .in_("set_id", chunk)
                .eq("value_scope", _SET_VALUE_HISTORY_SCOPE)
                .order("snapshot_date", desc=True)
                .limit(max(len(chunk) * _SET_VALUE_HISTORY_DAYS_PER_SET_LIMIT, len(chunk)))
                .execute()
            )
            for row in result.data or []:
                set_id = _to_optional_str(row.get("set_id"))
                if not set_id or set_id in latest_by_set_id:
                    continue
                value = _to_optional_float(row.get("set_value"))
                if value is None or value <= 0:
                    continue
                latest_by_set_id[set_id] = row

        sources["pokemon_set_value_daily_history"] = "OK"
        logger.info(
            "[rip-statistics-targets] loaded checklist set values matched=%s/%s in %.1fms",
            len(latest_by_set_id),
            len(unique_set_ids),
            (time.perf_counter() - started) * 1000,
        )
    except Exception as exc:
        logger.warning("[rip-statistics-targets] checklist set value enrichment failed: %s", exc)
        warnings.append("Failed to load checklist set value data for one or more RIP targets")
        sources["pokemon_set_value_daily_history"] = "FAILED"
        return {}

    return latest_by_set_id


def _resolve_mean_value_to_cost_ratio(row: Dict[str, Any]) -> Optional[float]:
    ratio = _to_optional_float(row.get("mean_value_to_cost_ratio"))
    if ratio is not None:
        return ratio

    mean_value = _to_optional_float(row.get("mean_value"))
    pack_cost = _to_optional_float(row.get("pack_cost"))
    if mean_value is None or pack_cost is None or pack_cost <= 0:
        return None
    return mean_value / pack_cost


def _blend_biggest_upside_score(
    p95_value_to_cost_ratio: Optional[float],
    p99_value_to_cost_ratio: Optional[float],
) -> Optional[float]:
    """Blend Big Hit Upside (P95) and God Pull Upside (P99) into a 0-100 score."""

    p95 = _to_optional_float(p95_value_to_cost_ratio)
    p99 = _to_optional_float(p99_value_to_cost_ratio)
    if p95 is None and p99 is None:
        return None

    def _normalize(raw: Optional[float], cap: float) -> float:
        if raw is None:
            return 0.0
        bounded = min(max(raw, 0.0), cap)
        return (bounded / cap) * 100.0

    norm_p95 = _normalize(p95, _BIGGEST_UPSIDE_P95_CAP)
    norm_p99 = _normalize(p99, _BIGGEST_UPSIDE_P99_CAP)
    return (_BIGGEST_UPSIDE_P95_WEIGHT * norm_p95) + (_BIGGEST_UPSIDE_P99_WEIGHT * norm_p99)


def _compute_relative_scores(rows: List[Dict[str, Any]], score_key: str) -> Dict[str, Optional[float]]:
    """Compute 0-100 relative scores for a score field across current rows."""

    scored_rows = [
        (str(row.get("target_id")), _to_optional_float(row.get(score_key)))
        for row in rows
        if row.get("target_id")
    ]
    valid_scores = [score for _, score in scored_rows if score is not None]
    if not valid_scores:
        return {target_id: None for target_id, _ in scored_rows}

    score_min = min(valid_scores)
    score_max = max(valid_scores)
    if score_max <= score_min:
        return {
            target_id: (50.0 if score is not None else None)
            for target_id, score in scored_rows
        }

    return {
        target_id: (100.0 * ((score - score_min) / (score_max - score_min)) if score is not None else None)
        for target_id, score in scored_rows
    }


def _shorten_canonical_label(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    for separator in (",", " - ", " — "):
        if separator in text:
            head = text.split(separator, 1)[0].strip()
            return head or text
    return text


def _build_recommendation_labels(summary_row: Dict[str, Any]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    try:
        interpretation = build_rip_interpretation(summary_row)
    except Exception:
        logger.warning("[rip-statistics-targets] failed to build interpretation for target row")
        return None, None, None

    pack_score_meta = ((interpretation or {}).get("meta") or {}).get("packScore") or {}
    canonical_header = _to_optional_str(pack_score_meta.get("label"))
    quick_label = _shorten_canonical_label(canonical_header)
    severity = _to_optional_str(pack_score_meta.get("severity"))
    return canonical_header, quick_label, severity


def _build_rank_sort_key(row: Dict[str, Any]) -> tuple[int, float, str]:
    placeholder = bool(row.get("pack_score_is_placeholder"))
    pack_score = _to_optional_float(row.get("pack_score"))
    run_at = str(row.get("run_at") or "")
    return (
        1 if placeholder else 0,
        -(pack_score if pack_score is not None else float("-inf")),
        run_at,
    )


def _build_set_order_key(target_id: str, set_row: Dict[str, Any]) -> tuple[int, str, int, str, str, str]:
    release_date = _to_optional_str(set_row.get("release_date"))
    pokemon_api_set_id = _to_optional_str(set_row.get("pokemon_api_set_id"))
    set_name = _to_optional_str(set_row.get("name")) or target_id
    return (
        1 if release_date is None else 0,
        release_date or "",
        1 if pokemon_api_set_id is None else 0,
        pokemon_api_set_id or "",
        set_name.casefold(),
        target_id,
    )


def _calculate_score_ranks_and_tiers(
    rows: List[Dict[str, Any]], score_key: str
) -> Dict[str, Dict[str, Any]]:
    """Calculate rank and tier for each row based on a score field.
    
    Args:
        rows: List of target rows with score data
        score_key: The score field name (e.g., 'pack_score', 'profit_score')
    
    Returns:
        Dict mapping target_id to {rank, tier} for that score
    """
    result: Dict[str, Dict[str, Any]] = {}
    
    # Sort rows by score descending (highest score = rank 1)
    scored_rows = [
        (str(row.get("target_id")), _to_optional_float(row.get(score_key)))
        for row in rows
        if row.get("target_id")
    ]
    scored_rows_with_valid_scores = [
        (target_id, score) for target_id, score in scored_rows if score is not None
    ]
    
    if not scored_rows_with_valid_scores:
        # All rows have null scores for this score_key
        for target_id, _ in scored_rows:
            result[target_id] = {"rank": None, "tier": None}
        return result
    
    # Sort by score descending
    scored_rows_with_valid_scores.sort(key=lambda x: x[1], reverse=True)
    total = len(scored_rows_with_valid_scores)
    
    # Assign ranks and calculate rank-bucket tiers (mirrors DB view semantics)
    for rank, (target_id, score) in enumerate(scored_rows_with_valid_scores, start=1):
        if rank <= max(1, math.ceil(total * 0.05)):
            tier = "S"
        elif rank <= max(1, math.ceil(total * 0.15)):
            tier = "A"
        elif rank <= max(1, math.ceil(total * 0.30)):
            tier = "B"
        elif rank <= max(1, math.ceil(total * 0.50)):
            tier = "C"
        elif rank <= max(1, math.ceil(total * 0.75)):
            tier = "D"
        else:
            tier = "F"
        
        result[target_id] = {"rank": rank, "tier": tier}
    
    # Rows without scores get None
    for target_id, _ in scored_rows:
        if target_id not in result:
            result[target_id] = {"rank": None, "tier": None}
    
    return result


def get_rip_statistics_targets_payload(limit: Any = DEFAULT_TARGETS_LIMIT) -> Dict[str, Any]:
    """Return available RIP targets and the best default target from persisted data."""
    total_started = time.perf_counter()
    clamped_limit = _sanitize_limit(limit, default=DEFAULT_TARGETS_LIMIT, max_value=MAX_TARGETS_LIMIT)

    warnings: List[str] = []
    sources: Dict[str, str] = {}

    query_started = time.perf_counter()
    try:
        targets_result = (
            public_read_client.table("explore_rip_statistics_latest")
            .select("*")
            .order("pack_score", desc=True)
            .order("run_at", desc=True)
            .limit(clamped_limit)
            .execute()
        )
        raw_rows = [row for row in (targets_result.data or []) if row.get("set_id")]
        sources["explore_rip_statistics_latest"] = "OK"
        sources["simulation_latest_by_target"] = "SKIPPED_RIP_SUMMARY"
    except Exception as exc:
        logger.exception("[rip-statistics-targets] explore_rip_statistics_latest query failed")
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

    ranked_rows = sorted(raw_rows, key=_build_rank_sort_key)

    set_lookup_by_target_id: Dict[str, Dict[str, Any]] = {}
    era_lookup: Dict[str, Dict[str, Any]] = {}

    set_ids = sorted({str(row.get("set_id")) for row in ranked_rows if row.get("set_id")})
    if set_ids:
        set_started = time.perf_counter()
        try:
            set_result = (
                public_read_client.table("sets")
                .select(
                    "id,name,canonical_key,release_date,pokemon_api_set_id,era_id,logo_image_url,symbol_image_url,hero_image_url"
                )
                .in_("id", set_ids)
                .execute()
            )
            for row in (set_result.data or []):
                set_id = _to_optional_str(row.get("id"))
                if set_id:
                    set_lookup_by_target_id[set_id] = row

            unresolved_target_ids = [
                target_id for target_id in set_ids if target_id not in set_lookup_by_target_id
            ]
            if unresolved_target_ids:
                canonical_result = (
                    public_read_client.table("sets")
                    .select(
                        "id,name,canonical_key,release_date,pokemon_api_set_id,era_id,logo_image_url,symbol_image_url,hero_image_url"
                    )
                    .in_("canonical_key", unresolved_target_ids)
                    .execute()
                )
                for row in (canonical_result.data or []):
                    canonical_key = _to_optional_str(row.get("canonical_key"))
                    if canonical_key and canonical_key in unresolved_target_ids:
                        set_lookup_by_target_id[canonical_key] = row

            sources["sets"] = "OK"
        except Exception as exc:
            logger.warning("[rip-statistics-targets] set enrichment failed: %s", exc)
            warnings.append("Failed to load set metadata for one or more RIP targets")
            sources["sets"] = "FAILED"
        set_ms = (time.perf_counter() - set_started) * 1000
    else:
        set_ms = 0.0
        sources["sets"] = "SKIPPED"

    set_value_started = time.perf_counter()
    set_value_lookup_ids = sorted(
        {
            resolved_id
            for resolved_id in [
                *set_ids,
                *[
                    _to_optional_str(set_row.get("id"))
                    for set_row in set_lookup_by_target_id.values()
                ],
            ]
            if resolved_id
        }
    )
    current_checklist_set_value_lookup = _load_current_checklist_set_value_lookup(
        set_value_lookup_ids,
        sources=sources,
        warnings=warnings,
    )
    set_value_ms = (time.perf_counter() - set_value_started) * 1000

    era_ids = sorted(
        {
            str(row.get("era_id"))
            for row in set_lookup_by_target_id.values()
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

    # Fetch ratio rank/tier fields not exposed by explore_rip_statistics_latest
    ratio_rank_tier_lookup: Dict[str, Dict[str, Any]] = {}
    if set_ids:
        ratio_started = time.perf_counter()
        try:
            ratio_result = (
                public_read_client.table("set_pack_score_rankings_latest")
                .select(
                    "target_id,mean_value_to_cost_rank,mean_value_to_cost_tier,"
                    "p95_value_to_cost_rank,p95_value_to_cost_tier"
                )
                .in_("target_id", set_ids)
                .execute()
            )
            for ratio_row in (ratio_result.data or []):
                tid = _to_optional_str(ratio_row.get("target_id"))
                if tid:
                    ratio_rank_tier_lookup[tid] = ratio_row
            sources["ratio_rank_tiers"] = "OK"
        except Exception as exc:
            logger.warning("[rip-statistics-targets] ratio rank/tier enrichment failed: %s", exc)
            warnings.append("Failed to load ratio rank/tier data for one or more RIP targets")
            sources["ratio_rank_tiers"] = "FAILED"

    ordered_rows = sorted(
        ranked_rows,
        key=lambda row: _build_set_order_key(
            str(row.get("set_id")),
            set_lookup_by_target_id.get(str(row.get("set_id"))) or {},
        ),
    )

    default_target_id: Optional[str] = None
    for row in ranked_rows:
        target_id = _to_optional_str(row.get("set_id"))
        if target_id and _to_optional_float(row.get("pack_score")) is not None:
            default_target_id = target_id
            break
    if default_target_id is None and ranked_rows:
        default_target_id = _to_optional_str(ranked_rows[0].get("target_id"))

    targets: List[Dict[str, Any]] = []
    for row in ordered_rows:
        target_id = str(row.get("set_id"))
        set_row = set_lookup_by_target_id.get(target_id) or {}
        era_row = era_lookup.get(str(set_row.get("era_id"))) if set_row.get("era_id") is not None else None
        summary_row = {
            key: value
            for key, value in row.items()
            if key not in {"set_id", "calculation_run_id", "run_at", "created_at", "updated_at"}
        }
        canonical_recommendation_header, leaderboard_label, recommendation_severity = _build_recommendation_labels(
            summary_row
        )
        pack_rank = row.get("pack_rank")
        pack_tier = _to_optional_str(row.get("pack_tier"))
        resolved_set_id = _to_optional_str(set_row.get("id")) or target_id
        checklist_set_value_row = (
            current_checklist_set_value_lookup.get(resolved_set_id)
            or current_checklist_set_value_lookup.get(target_id)
            or {}
        )
        checklist_set_value = _to_optional_float(checklist_set_value_row.get("set_value"))
        
        targets.append(
            {
                "target_type": "set",
                "target_id": target_id,
                "id": resolved_set_id,
                "set_id": resolved_set_id,
                "canonical_key": set_row.get("canonical_key"),
                "slug": set_row.get("canonical_key"),
                "pokemon_api_set_id": set_row.get("pokemon_api_set_id"),
                "name": str(set_row.get("name") or target_id),
                "era": era_row.get("name") if era_row else None,
                "logo_image_url": set_row.get("logo_image_url"),
                "symbol_image_url": set_row.get("symbol_image_url"),
                "hero_image_url": set_row.get("hero_image_url"),
                "leaderboard_label": leaderboard_label,
                "canonical_recommendation_header": canonical_recommendation_header,
                "recommendation_severity": recommendation_severity,
                "relative_pack_score": row.get("relative_pack_score"),
                "pack_score": row.get("pack_score"),
                "pack_rank": pack_rank,
                "pack_tier": pack_tier,
                "relative_profit_score": row.get("relative_profit_score"),
                "profit_score": row.get("profit_score"),
                "profit_rank": row.get("profit_rank"),
                "profit_tier": row.get("profit_tier"),
                "relative_safety_score": row.get("relative_safety_score"),
                "safety_score": row.get("safety_score"),
                "safety_rank": row.get("safety_rank"),
                "safety_tier": row.get("safety_tier"),
                "relative_stability_score": row.get("relative_stability_score"),
                "stability_score": row.get("stability_score"),
                "stability_rank": row.get("stability_rank"),
                "stability_tier": row.get("stability_tier"),
                "relative_desirability_score": row.get("relative_desirability_score"),
                "desirability_score": row.get("desirability_score"),
                "desirability_rank": row.get("desirability_rank"),
                "desirability_tier": row.get("desirability_tier"),
                "desirability_scoring_version": row.get("desirability_scoring_version"),
                "desirability_source_summary_id": row.get("desirability_source_summary_id"),
                "desirability_source_table": row.get("desirability_source_table"),
                "desirability_source_metric": row.get("desirability_source_metric"),
                "desirability_is_fallback": row.get("desirability_is_fallback"),
                "desirability_fallback_reason": row.get("desirability_fallback_reason"),
                "relative_experience_score": row.get("relative_experience_score"),
                "experience_score": row.get("experience_score"),
                "experience_rank": row.get("experience_rank"),
                "experience_tier": row.get("experience_tier"),
                "relative_chase_potential_score": row.get("relative_chase_potential_score"),
                "chase_potential_score": row.get("chase_potential_score"),
                "chase_potential_rank": row.get("chase_potential_rank"),
                "chase_potential_tier": row.get("chase_potential_tier"),
                "mean_value_to_cost_ratio": row.get("mean_value_to_cost_ratio"),
                "mean_value_to_cost_rank": ratio_rank_tier_lookup.get(target_id, {}).get("mean_value_to_cost_rank"),
                "mean_value_to_cost_tier": ratio_rank_tier_lookup.get(target_id, {}).get("mean_value_to_cost_tier"),
                "p95_value_to_cost_ratio": row.get("p95_value_to_cost_ratio"),
                "p99_value_to_cost_ratio": row.get("p99_value_to_cost_ratio"),
                "p95_value_to_cost_rank": ratio_rank_tier_lookup.get(target_id, {}).get("p95_value_to_cost_rank"),
                "p95_value_to_cost_tier": ratio_rank_tier_lookup.get(target_id, {}).get("p95_value_to_cost_tier"),
                "pack_cost": row.get("pack_cost"),
                "mean_value": row.get("mean_value"),
                "median_value": row.get("median_value"),
                "simulated_set_value": row.get("simulated_set_value"),
                "simulated_set_value_card_count": row.get("simulated_set_value_card_count"),
                "set_value_for_validation": checklist_set_value,
                "setValueForValidation": checklist_set_value,
                "current_checklist_set_value": checklist_set_value,
                "currentChecklistSetValue": checklist_set_value,
                "checklist_set_value": checklist_set_value,
                "checklistSetValue": checklist_set_value,
                "current_checklist_set_value_date": checklist_set_value_row.get("snapshot_date"),
                "currentChecklistSetValueDate": checklist_set_value_row.get("snapshot_date"),
                "checklist_set_value_source": checklist_set_value_row.get("source"),
                "checklistSetValueSource": checklist_set_value_row.get("source"),
                "checklist_set_value_priced_card_count": checklist_set_value_row.get("priced_card_count"),
                "checklistSetValuePricedCardCount": checklist_set_value_row.get("priced_card_count"),
                "checklist_set_value_total_card_count": checklist_set_value_row.get("total_card_count"),
                "checklistSetValueTotalCardCount": checklist_set_value_row.get("total_card_count"),
                "roi_percent": row.get("roi_percent"),
                "prob_profit": row.get("prob_profit"),
                "prob_big_hit": row.get("prob_big_hit"),
                "run_at": row.get("run_at"),
            }
        )

    desirability_rows = [
        {
            "target_id": target.get("target_id"),
            "desirability_score": _to_optional_float(target.get("desirability_score")),
        }
        for target in targets
    ]
    desirability_ranks = _calculate_score_ranks_and_tiers(desirability_rows, "desirability_score")
    desirability_relatives = _compute_relative_scores(desirability_rows, "desirability_score")
    for target in targets:
        target_id = str(target.get("target_id"))
        rank_payload = desirability_ranks.get(target_id, {})
        if target.get("relative_desirability_score") is None:
            relative_desirability = desirability_relatives.get(target_id)
            target["relative_desirability_score"] = (
                round(relative_desirability, 2)
                if relative_desirability is not None
                else None
            )
        if target.get("desirability_rank") is None:
            target["desirability_rank"] = rank_payload.get("rank")
        if target.get("desirability_tier") is None:
            target["desirability_tier"] = rank_payload.get("tier")

    # Blend Biggest Upside lens from P95 (Big Hit Upside) + P99 (God Pull Upside).
    blended_rows = [
        {
            "target_id": target.get("target_id"),
            "biggest_upside_score": _blend_biggest_upside_score(
                target.get("p95_value_to_cost_ratio"),
                target.get("p99_value_to_cost_ratio"),
            ),
        }
        for target in targets
    ]
    blended_score_lookup = {
        str(row.get("target_id")): _to_optional_float(row.get("biggest_upside_score"))
        for row in blended_rows
        if row.get("target_id")
    }
    blended_ranks = _calculate_score_ranks_and_tiers(blended_rows, "biggest_upside_score")
    blended_relatives = _compute_relative_scores(blended_rows, "biggest_upside_score")

    for target in targets:
        target_id = str(target.get("target_id"))
        rank_payload = blended_ranks.get(target_id, {})
        blended_score = blended_score_lookup.get(target_id)
        target["biggest_upside_score"] = (
            round(blended_score, 2)
            if blended_score is not None
            else None
        )
        target["relative_biggest_upside_score"] = (
            round(blended_relatives[target_id], 2)
            if blended_relatives.get(target_id) is not None
            else None
        )
        target["biggest_upside_rank"] = rank_payload.get("rank")
        target["biggest_upside_tier"] = rank_payload.get("tier")

    average_return_rows = [
        {
            "target_id": target.get("target_id"),
            "average_return_score": _resolve_mean_value_to_cost_ratio(target),
        }
        for target in targets
    ]
    average_return_relatives = _compute_relative_scores(average_return_rows, "average_return_score")
    for target in targets:
        target_id = str(target.get("target_id"))
        relative_average = average_return_relatives.get(target_id)
        target["relative_average_return_score"] = (
            round(relative_average, 2)
            if relative_average is not None
            else None
        )

    p99_rows = [
        {
            "target_id": target.get("target_id"),
            "p99_value_to_cost_score": _to_optional_float(target.get("p99_value_to_cost_ratio")),
        }
        for target in targets
    ]
    p99_ranks = _calculate_score_ranks_and_tiers(p99_rows, "p99_value_to_cost_score")
    p99_relatives = _compute_relative_scores(p99_rows, "p99_value_to_cost_score")
    for target in targets:
        target_id = str(target.get("target_id"))
        p99_rank_payload = p99_ranks.get(target_id, {})
        relative_p99 = p99_relatives.get(target_id)
        target["relative_p99_value_to_cost_score"] = (
            round(relative_p99, 2)
            if relative_p99 is not None
            else None
        )
        target["p99_value_to_cost_rank"] = p99_rank_payload.get("rank")
        target["p99_value_to_cost_tier"] = p99_rank_payload.get("tier")

    comparison_payload = build_rip_desirability_comparison_payload(targets)
    targets = comparison_payload["rows"]
    comparison_diagnostics = comparison_payload["diagnostics"]
    logger.info(
        "[rip-statistics-targets] RIP desirability comparison valid=%s/%s missing_desirability=%s "
        "raises_rank=%s lowers_rank=%s minimal=%s",
        comparison_diagnostics["valid_comparison_count"],
        comparison_diagnostics["total_sets"],
        comparison_diagnostics["missing_desirability_count"],
        comparison_diagnostics["raises_rank_count"],
        comparison_diagnostics["lowers_rank_count"],
        comparison_diagnostics["minimal_impact_count"],
    )

    default_target_row = next(
        (target for target in targets if target.get("target_id") == default_target_id),
        targets[0],
    )

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
            "ripDesirabilityComparison": comparison_diagnostics,
            "rip_desirability_comparison": comparison_diagnostics,
            "timings": {
                "targets_query_ms": round(query_ms, 2),
                "set_enrichment_ms": round(set_ms, 2),
                "set_value_enrichment_ms": round(set_value_ms, 2),
                "era_enrichment_ms": round(era_ms, 2),
                "total_backend_ms": round(total_ms, 2),
            },
            "request": {
                "limit": clamped_limit,
            },
        },
    }
