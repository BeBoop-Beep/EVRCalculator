"""Service for aggregating Explore page simulation data."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from backend.db.clients.supabase_client import public_read_client

logger = logging.getLogger(__name__)

DEFAULT_DISTRIBUTION_BINS_LIMIT = 50
MAX_DISTRIBUTION_BINS_LIMIT = 200
DEFAULT_TOP_HITS_LIMIT = 10
MAX_TOP_HITS_LIMIT = 50
MIN_LIMIT = 1


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

    warnings: List[str] = []
    sources: Dict[str, str] = {}

    # Fields from simulation_latest_by_target that are lookup keys, not metrics.
    _CANONICAL_META_KEYS = frozenset({"target_type", "target_id", "calculation_run_id", "run_at"})

    # Prefer canonical latest-by-target source first.
    # The view uses run_at (not created_at) as its timestamp column.
    summary_from_canonical = False
    summary: Dict[str, Any] = {}
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
                    "total_ev,net_value,roi,roi_percent,prob_profit,prob_big_hit,big_hit_threshold"
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
            public_read_client.table("simulation_input_cards")
            .select("card_name,ev_contribution")
            .eq("calculation_run_id", run_id)
            .order("ev_contribution", desc=True)
            .limit(clamped_top_hits_limit)
            .execute()
        )
        top_hits = top_hits_result.data if top_hits_result.data else []
        sources["simulation_input_cards"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_input_cards failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load top hits")
        sources["simulation_input_cards"] = "FAILED"
    top_hits_ms = (time.perf_counter() - top_hits_started) * 1000

    total_ms = (time.perf_counter() - total_started) * 1000

    return {
        "summary": summary,
        "rankings": rankings,
        "rip_statistics": rip_statistics,
        "percentiles": percentiles,
        "distribution_bins": distribution_bins,
        "threshold_bins": threshold_bins,
        "top_hits": top_hits,
        "meta": {
            "request": {
                "target_type": requested_target_type,
                "target_id": requested_target_id,
                "limit_distribution_bins": clamped_distribution_bins_limit,
                "limit_top_hits": clamped_top_hits_limit,
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
                "total_backend_ms": round(total_ms, 2),
            },
        },
    }
