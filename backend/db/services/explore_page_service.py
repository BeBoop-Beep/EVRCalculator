"""Service for aggregating Explore page simulation data."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from backend.db.clients.supabase_client import public_read_client

logger = logging.getLogger(__name__)


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


def get_explore_page_payload(
    target_type: str,
    target_id: str,
    limit_distribution_bins: int = 50,
    limit_top_hits: int = 10,
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

    # Find latest calculation run
    try:
        run_result = (
            public_read_client.table("calculation_runs")
            .select("id,created_at,target_type,target_id")
            .eq("target_type", requested_target_type)
            .eq("target_id", requested_target_id)
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
        run_id = run_row.get("id")
    except ExplorePageError:
        raise
    except Exception as exc:
        logger.exception(
            "[explore-page] calculation_runs query failed target_type=%s target_id=%s",
            requested_target_type,
            requested_target_id,
        )
        raise ExplorePageError(
            status_code=500,
            message="Failed to fetch simulation data",
            code="RUN_QUERY_FAILED",
        ) from exc

    warnings: List[str] = []
    sources: Dict[str, str] = {}

    # Summary
    summary_started = time.perf_counter()
    summary: Dict[str, Any] = {}
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
        summary.update(summary_result.data if summary_result.data else {})
        sources["simulation_run_summary"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_run_summary failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load summary statistics")
        sources["simulation_run_summary"] = "FAILED"

    try:
        derived_result = (
            public_read_client.table("simulation_derived_metrics")
            .select("*")
            .eq("calculation_run_id", run_id)
            .single()
            .execute()
        )
        summary.update(derived_result.data if derived_result.data else {})
        sources["simulation_derived_metrics"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_derived_metrics failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load derived metrics")
        sources["simulation_derived_metrics"] = "FAILED"

    summary_ms = (time.perf_counter() - summary_started) * 1000

    # Rankings
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

    # RIP Statistics
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

    # Percentiles
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

    # Distribution Bins (SEPARATE query)
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
            .limit(limit_distribution_bins)
            .execute()
        )
        distribution_bins = distribution_result.data if distribution_result.data else []
        sources["simulation_value_distribution_bins"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_value_distribution_bins failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load distribution bins")
        sources["simulation_value_distribution_bins"] = "FAILED"
    distribution_ms = (time.perf_counter() - distribution_started) * 1000

    # Top Hits
    top_hits_started = time.perf_counter()
    top_hits: List[Dict[str, Any]] = []
    try:
        top_hits_result = (
            public_read_client.table("simulation_input_cards")
            .select("card_name,ev_contribution")
            .eq("calculation_run_id", run_id)
            .order("ev_contribution", desc=True)
            .limit(limit_top_hits)
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
        "top_hits": top_hits,
        "meta": {
            "sources": sources,
            "warnings": warnings,
            "timings": {
                "summary_ms": round(summary_ms, 2),
                "rankings_ms": round(rankings_ms, 2),
                "rip_statistics_ms": round(rip_ms, 2),
                "percentiles_ms": round(percentiles_ms, 2),
                "distribution_bins_ms": round(distribution_ms, 2),
                "top_hits_ms": round(top_hits_ms, 2),
                "total_backend_ms": round(total_ms, 2),
            },
        },
    }
