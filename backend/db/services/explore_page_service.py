"""Service for aggregating Explore page simulation data."""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Dict, List, Optional

from backend.db.clients.supabase_client import public_read_client
from backend.interpretation.rips import build_rip_interpretation

logger = logging.getLogger(__name__)

DEFAULT_DISTRIBUTION_BINS_LIMIT = 50
MAX_DISTRIBUTION_BINS_LIMIT = 200
DEFAULT_TOP_HITS_LIMIT = 10
MAX_TOP_HITS_LIMIT = 50
DEFAULT_HISTORY_TREND_LIMIT = 180
MAX_HISTORY_TREND_LIMIT = 180
MIN_LIMIT = 1

_BIGGEST_UPSIDE_P95_CAP = 5.0
_BIGGEST_UPSIDE_P99_CAP = 10.0
_BIGGEST_UPSIDE_P95_WEIGHT = 0.70
_BIGGEST_UPSIDE_P99_WEIGHT = 0.30

_RIP_SUMMARY_META_KEYS = frozenset(
    {
        "set_id",
        "calculation_run_id",
        "run_at",
        "created_at",
        "updated_at",
    }
)

_RIP_SUMMARY_REQUIRED_FIELDS = (
    "pack_score",
    "relative_pack_score",
    "pack_rank",
    "pack_tier",
    "profit_score",
    "safety_score",
    "stability_score",
    "profit_rank",
    "profit_tier",
    "safety_rank",
    "safety_tier",
    "stability_rank",
    "stability_tier",
    "relative_profit_score",
    "relative_safety_score",
    "relative_stability_score",
    "pack_cost",
    "mean_value",
    "median_value",
    "roi_percent",
    "prob_profit",
    "p95_value_to_cost_ratio",
    "p99_value_to_cost_ratio",
    "mean_value_to_cost_ratio",
    "median_value_to_cost_ratio",
    "expected_loss_when_losing_fraction",
    "median_loss_when_losing_fraction",
    "p05_shortfall_to_cost",
    "expected_loss_when_losing",
    "median_loss_when_losing",
    "expected_loss_per_pack",
    "tail_value_p05",
    "coefficient_of_variation",
    "hhi_ev_concentration",
    "effective_chase_count",
    "top1_ev_share",
    "top3_ev_share",
    "top5_ev_share",
)

_RIP_SUMMARY_SUPPLEMENT_FIELDS = (
    "pack_tier",
    "profit_rank",
    "profit_tier",
    "safety_rank",
    "safety_tier",
    "stability_rank",
    "stability_tier",
    "relative_profit_score",
    "relative_safety_score",
    "relative_stability_score",
    "median_value_to_cost_ratio",
    "median_loss_when_losing_fraction",
    "experience_score",
    "chase_potential_score",
    "experience_tier",
    "chase_potential_tier",
    "mean_value_to_cost_rank",
    "mean_value_to_cost_tier",
    "p95_value_to_cost_rank",
    "p95_value_to_cost_tier",
    "derived_metric_version",
)


def _to_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _resolve_top_hit_image_fields(
    variant_row: Optional[Dict[str, Any]],
    card_row: Optional[Dict[str, Any]],
) -> Dict[str, Optional[str]]:
    variant_small = _to_optional_str((variant_row or {}).get("image_small_url"))
    card_small = _to_optional_str((card_row or {}).get("image_small_url"))
    variant_large = _to_optional_str((variant_row or {}).get("image_large_url"))
    card_large = _to_optional_str((card_row or {}).get("image_large_url"))

    return {
        "image_url": variant_small or card_small or variant_large or card_large,
        "image_small_url": variant_small or card_small,
        "image_large_url": variant_large or card_large,
    }


def _enrich_top_hits_with_images(top_hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    variant_ids = sorted(
        {
            str(hit.get("card_variant_id"))
            for hit in top_hits
            if hit.get("card_variant_id") is not None
        }
    )
    card_ids = sorted(
        {
            str(hit.get("card_id"))
            for hit in top_hits
            if hit.get("card_id") is not None
        }
    )

    variant_lookup: Dict[str, Dict[str, Any]] = {}
    card_lookup: Dict[str, Dict[str, Any]] = {}

    if variant_ids:
        variant_result = (
            public_read_client.table("card_variants")
            .select("id,card_id,image_small_url,image_large_url")
            .in_("id", variant_ids)
            .execute()
        )
        variant_lookup = {
            str(row.get("id")): row
            for row in (variant_result.data or [])
            if row.get("id") is not None
        }

    derived_card_ids = {
        str(row.get("card_id"))
        for row in variant_lookup.values()
        if row.get("card_id") is not None
    }
    all_card_ids = sorted(set(card_ids) | derived_card_ids)
    if all_card_ids:
        card_result = (
            public_read_client.table("cards")
            .select("id,image_small_url,image_large_url")
            .in_("id", all_card_ids)
            .execute()
        )
        card_lookup = {
            str(row.get("id")): row
            for row in (card_result.data or [])
            if row.get("id") is not None
        }

    enriched_hits: List[Dict[str, Any]] = []
    for hit in top_hits:
        variant_id = _to_optional_str(hit.get("card_variant_id"))
        card_id = _to_optional_str(hit.get("card_id"))
        variant_row = variant_lookup.get(variant_id) if variant_id else None
        card_row = None
        if card_id:
            card_row = card_lookup.get(card_id)
        elif variant_row and variant_row.get("card_id") is not None:
            card_row = card_lookup.get(str(variant_row.get("card_id")))

        image_fields = _resolve_top_hit_image_fields(variant_row, card_row)
        enriched_hits.append(
            {
                **hit,
                **image_fields,
            }
        )

    return enriched_hits


class ExplorePageError(Exception):
    """Structured error for Explore page service."""

    def __init__(self, status_code: int, message: str, code: str):
        self.status_code = status_code
        self.message = message
        self.code = code
        super().__init__(message)


def _first_row(result) -> Optional[Dict[str, Any]]:
    """Extract first row from Supabase query result."""
    if result and result.data and len(result.data) > 0:
        return result.data[0]
    return None


def _sanitize_limit(value: Any, *, default: int, max_value: int) -> int:
    """Convert untrusted limit input into a safe bounded integer."""
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


def _rank_tier_from_percentile(rank: int, total: int) -> str:
    if rank <= max(1, math.ceil(total * 0.05)):
        return "S"
    if rank <= max(1, math.ceil(total * 0.15)):
        return "A"
    if rank <= max(1, math.ceil(total * 0.30)):
        return "B"
    if rank <= max(1, math.ceil(total * 0.50)):
        return "C"
    if rank <= max(1, math.ceil(total * 0.75)):
        return "D"
    return "F"


def _populate_biggest_upside_metrics_for_set(
    summary: Dict[str, Any],
    requested_target_id: str,
    warnings: List[str],
    sources: Dict[str, str],
) -> None:
    """Attach blended Biggest Upside score + relative/rank/tier for set targets."""

    summary["biggest_upside_score"] = _blend_biggest_upside_score(
        summary.get("p95_value_to_cost_ratio"),
        summary.get("p99_value_to_cost_ratio"),
    )

    if summary.get("biggest_upside_score") is None:
        summary["relative_biggest_upside_score"] = None
        summary["biggest_upside_rank"] = None
        summary["biggest_upside_tier"] = None
        return

    try:
        peers_result = (
            public_read_client.table("explore_rip_statistics_latest")
            .select("set_id,p95_value_to_cost_ratio,p99_value_to_cost_ratio")
            .execute()
        )
        peer_rows = peers_result.data if peers_result and peers_result.data else []
    except Exception as exc:
        logger.warning(
            "[explore-page] biggest_upside peer query failed target_id=%s: %s",
            requested_target_id,
            exc,
        )
        warnings.append("Failed to compute blended Biggest Upside rank context")
        sources["biggest_upside_blend"] = "FAILED"
        summary["relative_biggest_upside_score"] = None
        summary["biggest_upside_rank"] = None
        summary["biggest_upside_tier"] = None
        return

    scored_peers: List[tuple[str, float]] = []
    for row in peer_rows:
        if not isinstance(row, dict):
            continue
        set_id = str(row.get("set_id") or "").strip()
        if not set_id:
            continue
        blended = _blend_biggest_upside_score(
            row.get("p95_value_to_cost_ratio"),
            row.get("p99_value_to_cost_ratio"),
        )
        if blended is None:
            continue
        scored_peers.append((set_id, blended))

    if not scored_peers:
        sources["biggest_upside_blend"] = "NO_PEERS"
        summary["relative_biggest_upside_score"] = None
        summary["biggest_upside_rank"] = None
        summary["biggest_upside_tier"] = None
        return

    scores_only = [score for _, score in scored_peers]
    score_min = min(scores_only)
    score_max = max(scores_only)
    target_score = _to_optional_float(summary.get("biggest_upside_score"))
    if target_score is None:
        summary["relative_biggest_upside_score"] = None
    elif score_max <= score_min:
        summary["relative_biggest_upside_score"] = 50.0
    else:
        summary["relative_biggest_upside_score"] = 100.0 * ((target_score - score_min) / (score_max - score_min))

    ranked = sorted(scored_peers, key=lambda item: item[1], reverse=True)
    rank_lookup = {set_id: index for index, (set_id, _) in enumerate(ranked, start=1)}
    target_rank = rank_lookup.get(requested_target_id)
    summary["biggest_upside_rank"] = target_rank
    summary["biggest_upside_tier"] = (
        _rank_tier_from_percentile(target_rank, len(ranked)) if target_rank is not None else None
    )
    sources["biggest_upside_blend"] = "SERVICE_COMPUTED"


def _populate_relative_average_return_score_for_set(
    summary: Dict[str, Any],
    requested_target_id: str,
    warnings: List[str],
    sources: Dict[str, str],
) -> None:
    mean_ratio = _resolve_mean_value_to_cost_ratio(summary)
    if mean_ratio is None:
        summary["relative_average_return_score"] = None
        return

    try:
        peers_result = (
            public_read_client.table("explore_rip_statistics_latest")
            .select("set_id,mean_value_to_cost_ratio")
            .execute()
        )
        peer_rows = peers_result.data if peers_result and peers_result.data else []
    except Exception as exc:
        logger.warning(
            "[explore-page] average_return peer query failed target_id=%s: %s",
            requested_target_id,
            exc,
        )
        warnings.append("Failed to compute relative Average Return context")
        sources["average_return_relative"] = "FAILED"
        summary["relative_average_return_score"] = None
        return

    peer_ratios: List[float] = []
    for row in peer_rows:
        if not isinstance(row, dict):
            continue
        if not str(row.get("set_id") or "").strip():
            continue
        ratio = _to_optional_float(row.get("mean_value_to_cost_ratio"))
        if ratio is None:
            ratio = _resolve_mean_value_to_cost_ratio(row)
        if ratio is not None:
            peer_ratios.append(ratio)

    if not peer_ratios:
        sources["average_return_relative"] = "NO_PEERS"
        summary["relative_average_return_score"] = None
        return

    score_min = min(peer_ratios)
    score_max = max(peer_ratios)
    if score_max <= score_min:
        summary["relative_average_return_score"] = 50.0
    else:
        summary["relative_average_return_score"] = 100.0 * ((mean_ratio - score_min) / (score_max - score_min))
    sources["average_return_relative"] = "SERVICE_COMPUTED"


def _populate_p99_ratio_from_percentiles(summary: Dict[str, Any], percentiles: List[Dict[str, Any]]) -> None:
    if summary.get("p99_value_to_cost_ratio") is not None:
        return

    pack_cost = _to_optional_float(summary.get("pack_cost"))
    if pack_cost is None or pack_cost <= 0:
        return

    p99_value: Optional[float] = None
    for row in percentiles:
        if not isinstance(row, dict):
            continue
        percentile = _to_optional_float(row.get("percentile"))
        if percentile is None or abs(percentile - 99.0) >= 0.001:
            continue
        p99_value = _to_optional_float(row.get("value"))
        if p99_value is not None:
            break

    if p99_value is None:
        return

    summary["p99_value"] = p99_value
    summary["p99_value_to_cost_ratio"] = p99_value / pack_cost


def _missing_required_fields(row: Dict[str, Any], required_fields: tuple[str, ...]) -> List[str]:
    """Return required field names that are absent from a row."""
    return [field for field in required_fields if field not in row]


def _lookup_latest_run_from_calculation_runs(target_type: str, target_id: str) -> str:
    """Fallback latest run lookup when canonical latest view is unavailable."""
    run_result = (
        public_read_client.table("calculation_runs")
        .select("id,created_at,target_type,target_id")
        .eq("target_type", target_type)
        .eq("target_id", target_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    run_row = _first_row(run_result)
    if not run_row or not run_row.get("id"):
        raise ExplorePageError(
            status_code=404,
            message="No simulation data found for this target",
            code="TARGET_NOT_FOUND",
        )
    return str(run_row.get("id"))


def get_explore_page_payload(
    target_type: str,
    target_id: str,
    limit_distribution_bins: Any = DEFAULT_DISTRIBUTION_BINS_LIMIT,
    limit_top_hits: Any = DEFAULT_TOP_HITS_LIMIT,
) -> Dict[str, Any]:
    """Aggregate simulation data for Explore page."""
    total_started = time.perf_counter()

    requested_target_type = (target_type or "").strip()
    requested_target_id = (target_id or "").strip()

    if not requested_target_type or not requested_target_id:
        raise ExplorePageError(
            status_code=400,
            message="target_type and target_id are required",
            code="INVALID_TARGET",
        )

    clamped_distribution_bins_limit = _sanitize_limit(
        limit_distribution_bins,
        default=DEFAULT_DISTRIBUTION_BINS_LIMIT,
        max_value=MAX_DISTRIBUTION_BINS_LIMIT,
    )
    clamped_top_hits_limit = _sanitize_limit(
        limit_top_hits,
        default=DEFAULT_TOP_HITS_LIMIT,
        max_value=MAX_TOP_HITS_LIMIT,
    )
    history_trend_limit = _sanitize_limit(
        DEFAULT_HISTORY_TREND_LIMIT,
        default=DEFAULT_HISTORY_TREND_LIMIT,
        max_value=MAX_HISTORY_TREND_LIMIT,
    )

    warnings: List[str] = []
    sources: Dict[str, str] = {}

    # Fields from simulation_latest_by_target that are lookup keys, not metrics.
    _CANONICAL_META_KEYS = frozenset({"target_type", "target_id", "calculation_run_id", "run_at"})

    # Prefer RIP-specific summary source for set targets first.
    summary: Dict[str, Any] = {}
    summary_from_canonical = False
    summary_from_rip_latest = False
    if requested_target_type == "set":
        try:
            rip_latest_result = (
                public_read_client.table("explore_rip_statistics_latest")
                .select("*")
                .eq("set_id", requested_target_id)
                .limit(1)
                .execute()
            )
            rip_latest_row = _first_row(rip_latest_result)
            if rip_latest_row:
                rip_run_id = rip_latest_row.get("calculation_run_id")
                if rip_run_id:
                    run_id = str(rip_run_id)
                    summary = {
                        k: v for k, v in rip_latest_row.items() if k not in _RIP_SUMMARY_META_KEYS
                    }

                    # While the view is being updated, enrich with fields already available
                    # in set_pack_score_rankings_latest without computing anything in service.
                    try:
                        ranking_result = (
                            public_read_client.table("set_pack_score_rankings_latest")
                            .select(
                                "target_id,calculation_run_id,"
                                + ",".join(_RIP_SUMMARY_SUPPLEMENT_FIELDS)
                            )
                            .eq("target_id", requested_target_id)
                            .eq("calculation_run_id", run_id)
                            .limit(1)
                            .execute()
                        )
                        ranking_row = _first_row(ranking_result)
                        if ranking_row:
                            for field in _RIP_SUMMARY_SUPPLEMENT_FIELDS:
                                if field in ranking_row and (
                                    field not in summary or summary.get(field) is None
                                ):
                                    summary[field] = ranking_row.get(field)
                            sources["set_pack_score_rankings_latest"] = "OK"
                        else:
                            sources["set_pack_score_rankings_latest"] = "NO_ROW"
                    except Exception as ranking_exc:
                        logger.warning(
                            "[explore-page] set_pack_score_rankings_latest supplement failed "
                            "target_id=%s run_id=%s: %s",
                            requested_target_id,
                            run_id,
                            ranking_exc,
                        )
                        warnings.append(
                            "Failed to load supplemental RIP ranking fields from "
                            "set_pack_score_rankings_latest"
                        )
                        sources["set_pack_score_rankings_latest"] = "FAILED"

                    summary_from_rip_latest = True
                    summary_from_canonical = True
                    sources["explore_rip_statistics_latest"] = "OK"
                    sources["summary_source"] = "explore_rip_statistics_latest"
                    sources["latest_target_source"] = "explore_rip_statistics_latest"
                    sources["simulation_latest_by_target"] = "SKIPPED_RIP_SUMMARY"
                    sources["simulation_run_summary"] = "SKIPPED_RIP_SUMMARY"
                    sources["simulation_derived_metrics"] = "SKIPPED_RIP_SUMMARY"

                    missing_fields = _missing_required_fields(summary, _RIP_SUMMARY_REQUIRED_FIELDS)
                    if missing_fields:
                        warnings.append(
                            "explore_rip_statistics_latest is missing required summary fields: "
                            + ", ".join(missing_fields)
                            + ". Update view public.explore_rip_statistics_latest."
                        )
                        sources["explore_rip_statistics_latest"] = "MISSING_REQUIRED_FIELDS"
                else:
                    warnings.append(
                        "explore_rip_statistics_latest did not expose calculation_run_id; "
                        "fell back to simulation_latest_by_target"
                    )
                    sources["explore_rip_statistics_latest"] = "MISSING_CALCULATION_RUN_ID_FALLBACK"
            else:
                sources["explore_rip_statistics_latest"] = "NO_ROW_FALLBACK"
        except Exception as exc:
            logger.warning(
                "[explore-page] explore_rip_statistics_latest unavailable target_id=%s; "
                "falling back to simulation_latest_by_target: %s",
                requested_target_id,
                exc,
            )
            warnings.append(
                "explore_rip_statistics_latest unavailable; fell back to simulation_latest_by_target"
            )
            sources["explore_rip_statistics_latest"] = "UNAVAILABLE_FALLBACK"

    # Prefer canonical latest-by-target source when RIP summary wasn't used.
    # The view uses run_at (not created_at) as its timestamp column.
    if not summary_from_rip_latest:
        try:
            latest_target_result = (
                public_read_client.table("simulation_latest_by_target")
                .select("*")
                .eq("target_type", requested_target_type)
                .eq("target_id", requested_target_id)
                .order("run_at", desc=True)
                .limit(1)
                .execute()
            )
            latest_target_row = _first_row(latest_target_result)
            if not latest_target_row:
                raise ExplorePageError(
                    status_code=404,
                    message="No simulation data found for this target",
                    code="TARGET_NOT_FOUND",
                )

            latest_run_id = latest_target_row.get("calculation_run_id")
            if not latest_run_id:
                warnings.append(
                    "simulation_latest_by_target did not expose calculation_run_id; "
                    "fell back to calculation_runs latest lookup"
                )
                sources["simulation_latest_by_target"] = "MISSING_CALCULATION_RUN_ID_FALLBACK"
                run_id = _lookup_latest_run_from_calculation_runs(
                    requested_target_type,
                    requested_target_id,
                )
                sources["latest_target_source"] = "calculation_runs_fallback"
            else:
                run_id = str(latest_run_id)
                # Build summary directly from the canonical row — no separate summary/derived queries needed.
                summary = {k: v for k, v in latest_target_row.items() if k not in _CANONICAL_META_KEYS}
                summary_from_canonical = True
                sources["simulation_latest_by_target"] = "OK"
                sources["summary_source"] = "simulation_latest_by_target"
                sources["latest_target_source"] = "simulation_latest_by_target"
                sources["simulation_run_summary"] = "SKIPPED_CANONICAL"
                sources["simulation_derived_metrics"] = "SKIPPED_CANONICAL"
        except ExplorePageError:
            raise
        except Exception as exc:
            logger.warning(
                "[explore-page] simulation_latest_by_target unavailable target_type=%s target_id=%s; "
                "falling back to calculation_runs: %s",
                requested_target_type,
                requested_target_id,
                exc,
            )
            warnings.append(
                "simulation_latest_by_target unavailable or missing required columns; "
                "fell back to calculation_runs latest lookup"
            )
            sources["simulation_latest_by_target"] = "UNAVAILABLE_FALLBACK"
            try:
                run_id = _lookup_latest_run_from_calculation_runs(
                    requested_target_type,
                    requested_target_id,
                )
                sources["latest_target_source"] = "calculation_runs_fallback"
            except ExplorePageError:
                raise
            except Exception as fallback_exc:
                logger.exception(
                    "[explore-page] calculation_runs query failed target_type=%s target_id=%s",
                    requested_target_type,
                    requested_target_id,
                )
                raise ExplorePageError(
                    status_code=500,
                    message="Failed to fetch simulation data",
                    code="RUN_QUERY_FAILED",
                ) from fallback_exc

    # Summary + derived metrics (required only when canonical view was not used).
    summary_started = time.perf_counter()
    if not summary_from_canonical:
        try:
            summary_result = (
                public_read_client.table("simulation_run_summary")
                .select(
                    "pack_cost,mean_value,median_value,min_value,max_value,std_dev,"
                    "total_ev,net_value,roi,roi_percent,prob_profit,prob_big_hit,big_hit_threshold,"
                    "expected_loss_when_losing,median_loss_when_losing,tail_value_p05,coefficient_of_variation"
                )
                .eq("calculation_run_id", run_id)
                .single()
                .execute()
            )
            summary = summary_result.data if summary_result and summary_result.data else {}
            if not summary:
                raise ExplorePageError(
                    status_code=500,
                    message="Failed to load required summary statistics",
                    code="SUMMARY_QUERY_FAILED",
                )
            sources["simulation_run_summary"] = "OK"
            sources["summary_source"] = "simulation_run_summary+simulation_derived_metrics"
        except ExplorePageError:
            raise
        except Exception as exc:
            logger.exception("[explore-page] simulation_run_summary required query failed run_id=%s", run_id)
            raise ExplorePageError(
                status_code=500,
                message="Failed to load required summary statistics",
                code="SUMMARY_QUERY_FAILED",
            ) from exc

        try:
            derived_result = (
                public_read_client.table("simulation_derived_metrics")
                .select("*")
                .eq("calculation_run_id", run_id)
                .single()
                .execute()
            )
            derived_metrics = derived_result.data if derived_result and derived_result.data else {}
            if not derived_metrics:
                raise ExplorePageError(
                    status_code=500,
                    message="Failed to load required derived metrics",
                    code="DERIVED_QUERY_FAILED",
                )
            summary.update(derived_metrics)
            sources["simulation_derived_metrics"] = "OK"
        except ExplorePageError:
            raise
        except Exception as exc:
            logger.exception("[explore-page] simulation_derived_metrics required query failed run_id=%s", run_id)
            raise ExplorePageError(
                status_code=500,
                message="Failed to load required derived metrics",
                code="DERIVED_QUERY_FAILED",
            ) from exc

    summary_ms = (time.perf_counter() - summary_started) * 1000

    # Rankings (optional)
    rankings_started = time.perf_counter()
    rankings: List[Dict[str, Any]] = []
    try:
        rankings_result = (
            public_read_client.table("simulation_pull_summary")
            .select("rarity_bucket,pulled_count,avg_sampled_value,total_sampled_value")
            .eq("calculation_run_id", run_id)
            .order("rarity_bucket", desc=False)
            .execute()
        )
        rankings = rankings_result.data if rankings_result.data else []
        sources["simulation_pull_summary"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_pull_summary failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load rarity rankings")
        sources["simulation_pull_summary"] = "FAILED"
    rankings_ms = (time.perf_counter() - rankings_started) * 1000

    # RIP statistics (optional)
    rip_started = time.perf_counter()
    rip_statistics: Dict[str, Any] = {"pack_paths": {}, "normal_pack_states": {}}
    try:
        rip_result = (
            public_read_client.table("simulation_state_counts")
            .select("state_group,state_name,occurrence_count")
            .eq("calculation_run_id", run_id)
            .execute()
        )
        for row in (rip_result.data or []):
            group = row.get("state_group", "")
            name = row.get("state_name", "")
            count = row.get("occurrence_count", 0)
            if group == "pack_path":
                rip_statistics["pack_paths"][name] = count
            elif group == "normal_pack_state":
                rip_statistics["normal_pack_states"][name] = count
        sources["simulation_state_counts"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_state_counts failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load RIP statistics")
        sources["simulation_state_counts"] = "FAILED"
    rip_ms = (time.perf_counter() - rip_started) * 1000

    # Percentiles (optional)
    percentiles_started = time.perf_counter()
    percentiles: List[Dict[str, Any]] = []
    try:
        percentiles_result = (
            public_read_client.table("simulation_percentiles")
            .select("percentile,value")
            .eq("calculation_run_id", run_id)
            .order("percentile", desc=False)
            .execute()
        )
        percentiles = percentiles_result.data if percentiles_result.data else []
        sources["simulation_percentiles"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_percentiles failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load percentiles")
        sources["simulation_percentiles"] = "FAILED"
    percentiles_ms = (time.perf_counter() - percentiles_started) * 1000

    _populate_p99_ratio_from_percentiles(summary, percentiles)
    if requested_target_type == "set":
        _populate_biggest_upside_metrics_for_set(summary, requested_target_id, warnings, sources)
        _populate_relative_average_return_score_for_set(summary, requested_target_id, warnings, sources)

    # Distribution bins (optional, separate query)
    distribution_started = time.perf_counter()
    distribution_bins: List[Dict[str, Any]] = []
    try:
        distribution_result = (
            public_read_client.table("simulation_value_distribution_bins")
            .select(
                "bin_floor,bin_ceiling,occurrence_count,probability,"
                "cumulative_probability,survival_probability"
            )
            .eq("calculation_run_id", run_id)
            .order("bin_floor", desc=False)
            .limit(clamped_distribution_bins_limit)
            .execute()
        )
        distribution_bins = distribution_result.data if distribution_result.data else []
        sources["simulation_value_distribution_bins"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_value_distribution_bins failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load distribution bins")
        sources["simulation_value_distribution_bins"] = "FAILED"
    distribution_ms = (time.perf_counter() - distribution_started) * 1000

    # Threshold bins (optional, separate query)
    threshold_started = time.perf_counter()
    threshold_bins: List[Dict[str, Any]] = []
    try:
        threshold_result = (
            public_read_client.table("simulation_value_threshold_bins")
            .select(
                "threshold_floor,threshold_ceiling,occurrence_count,probability,"
                "cumulative_probability,survival_probability,bucket_label,bucket_order"
            )
            .eq("calculation_run_id", run_id)
            .order("bucket_order", desc=False)
            .execute()
        )
        threshold_bins = threshold_result.data if threshold_result.data else []
        sources["simulation_value_threshold_bins"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_value_threshold_bins failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load threshold bins")
        sources["simulation_value_threshold_bins"] = "FAILED"
    threshold_ms = (time.perf_counter() - threshold_started) * 1000

    # Top hits (optional)
    top_hits_started = time.perf_counter()
    top_hits: List[Dict[str, Any]] = []
    try:
        top_hits_result = (
            public_read_client.table("simulation_input_cards_with_near_mint_price")
            .select("card_id,card_variant_id,card_name,rarity_bucket,ev_contribution,current_near_mint_price")
            .eq("calculation_run_id", run_id)
            .order("ev_contribution", desc=True)
            .limit(clamped_top_hits_limit)
            .execute()
        )
        raw_hits = top_hits_result.data if top_hits_result.data else []
        top_hits = _enrich_top_hits_with_images(raw_hits)
        sources["simulation_input_cards"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_input_cards failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load top hits")
        sources["simulation_input_cards"] = "FAILED"
    top_hits_ms = (time.perf_counter() - top_hits_started) * 1000

    # Historical trend (optional)
    history_started = time.perf_counter()
    history_trend: List[Dict[str, Any]] = []
    try:
        history_result = (
            public_read_client.table("calculation_history_trend")
            .select(
                "snapshot_date,simulated_mean_pack_value_vs_pack_cost,"
                "simulated_median_pack_value_vs_pack_cost,run_created_at,calculation_run_id,"
                "p95_value_to_cost_ratio"
            )
            .eq("target_type", requested_target_type)
            .eq("target_id", requested_target_id)
            .order("snapshot_date", desc=True)
            .limit(history_trend_limit)
            .execute()
        )
        history_rows = history_result.data if history_result and history_result.data else []
        history_rows.sort(key=lambda row: (str(row.get("snapshot_date") or ""), str(row.get("run_created_at") or "")))
        history_trend = history_rows
        sources["calculation_history_trend"] = "OK"
    except Exception as exc:
        logger.warning(
            "[explore-page] calculation_history_trend failed (with p95) target_type=%s target_id=%s: %s – retrying without p95",
            requested_target_type,
            requested_target_id,
            exc,
        )
        # Fallback: retry without p95_value_to_cost_ratio in case the view does not expose that column yet.
        try:
            history_result_fallback = (
                public_read_client.table("calculation_history_trend")
                .select(
                    "snapshot_date,simulated_mean_pack_value_vs_pack_cost,"
                    "simulated_median_pack_value_vs_pack_cost,run_created_at,calculation_run_id"
                )
                .eq("target_type", requested_target_type)
                .eq("target_id", requested_target_id)
                .order("snapshot_date", desc=True)
                .limit(history_trend_limit)
                .execute()
            )
            history_rows_fb = history_result_fallback.data if history_result_fallback and history_result_fallback.data else []
            history_rows_fb.sort(key=lambda row: (str(row.get("snapshot_date") or ""), str(row.get("run_created_at") or "")))
            history_trend = history_rows_fb
            sources["calculation_history_trend"] = "OK_NO_P95"
        except Exception as exc2:
            logger.warning(
                "[explore-page] calculation_history_trend fallback also failed target_type=%s target_id=%s: %s",
                requested_target_type,
                requested_target_id,
                exc2,
            )
            warnings.append("Failed to load historical trend")
            sources["calculation_history_trend"] = "FAILED"
    history_ms = (time.perf_counter() - history_started) * 1000

    total_ms = (time.perf_counter() - total_started) * 1000

    interpretation = build_rip_interpretation(
        {
            "summary": summary,
            "rankings": rankings,
            "rip_statistics": rip_statistics,
            "percentiles": percentiles,
            "distribution_bins": distribution_bins,
            "threshold_bins": threshold_bins,
            "top_hits": top_hits,
            "history_trend": history_trend,
        }
    )

    return {
        "summary": summary,
        "rankings": rankings,
        "rip_statistics": rip_statistics,
        "percentiles": percentiles,
        "distribution_bins": distribution_bins,
        "threshold_bins": threshold_bins,
        "top_hits": top_hits,
        "history_trend": history_trend,
        "interpretation": interpretation,
        "meta": {
            "request": {
                "target_type": requested_target_type,
                "target_id": requested_target_id,
                "limit_distribution_bins": clamped_distribution_bins_limit,
                "limit_top_hits": clamped_top_hits_limit,
                "limit_history_trend": history_trend_limit,
            },
            "sources": sources,
            "warnings": warnings,
            "timings": {
                "summary_ms": round(summary_ms, 2),
                "rankings_ms": round(rankings_ms, 2),
                "rip_statistics_ms": round(rip_ms, 2),
                "percentiles_ms": round(percentiles_ms, 2),
                "distribution_bins_ms": round(distribution_ms, 2),
                "threshold_bins_ms": round(threshold_ms, 2),
                "top_hits_ms": round(top_hits_ms, 2),
                "history_trend_ms": round(history_ms, 2),
                "total_backend_ms": round(total_ms, 2),
            },
        },
    }
