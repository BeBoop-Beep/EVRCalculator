"""Persistence for Stage 1 sealed-product simulation results.

One row per ``(calculation_run_id, sealed_product_id)``. Writes are upserts on
that key so re-running a set is idempotent rather than accumulating duplicates.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from ..clients.supabase_client import supabase

TABLE = "simulation_sealed_product_results"
UNIQUE_KEY = "calculation_run_id,sealed_product_id"

_SELECT_FIELDS = (
    "id,calculation_run_id,sealed_product_id,set_id,product_family,product_name,pack_count,"
    "composition_version,distribution_model_version,pack_independence_assumption,"
    "product_market_cost,price_as_of,price_source,simulation_count,"
    "expected_value,median_value,p05_value,p95_value,p99_value,min_value,max_value,"
    "standard_deviation,chance_to_recover_cost,expected_loss_when_losing,"
    "median_loss_when_losing,total_value_to_cost_ratio,"
    "financial_rip_v3_score,financial_rip_v3_status,financial_rip_v3_rankable,"
    "financial_rip_v3_version,financial_rip_v3_payload,"
    "collector_appeal_score,collector_appeal_version,"
    "overall_rip_score,overall_rip_version,overall_rip_rankable,overall_rip_payload,"
    "created_at,updated_at"
)


def upsert_sealed_product_results(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Upsert Stage 1 product rows. Returns the persisted rows."""
    payload = [dict(row) for row in rows]
    if not payload:
        return []
    response = supabase.table(TABLE).upsert(payload, on_conflict=UNIQUE_KEY).execute()
    return list(response.data or [])


# ---------------------------------------------------------------------------
# Enrichment (batch finalization)
# ---------------------------------------------------------------------------
# Finalization is ENRICHMENT, not recomputation. The columns below are the ONLY
# ones it may write. Everything else on the row - the distribution statistics,
# the product market cost and its provenance, the whole Financial RIP V3 block,
# `calculation_run_id`, `sealed_product_id`, `pack_count` and the composition
# metadata - is the output of the simulation that produced the row and is
# re-derivable only by re-running it. An update is used rather than an upsert
# precisely so a partially-populated payload can never blank those columns.

ENRICHMENT_FIELDS = (
    "collector_appeal_score",
    "collector_appeal_version",
    "overall_rip_score",
    "overall_rip_version",
    "overall_rip_rankable",
    "overall_rip_payload",
)


def update_sealed_product_enrichment(row_id: Any, values: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Write ONLY the enrichment columns of one product row, by primary key.

    Unknown keys are refused rather than silently dropped: a typo'd column name
    that quietly does nothing would look exactly like a successful finalization.
    ``updated_at`` is left to the table's existing trigger.
    """
    unknown = sorted(set(values) - set(ENRICHMENT_FIELDS))
    if unknown:
        raise ValueError(
            f"{TABLE} enrichment may only write {ENRICHMENT_FIELDS}; refused: {unknown}"
        )
    if not values:
        return []
    response = supabase.table(TABLE).update(dict(values)).eq("id", str(row_id)).execute()
    return list(response.data or [])


def get_sealed_product_results_for_runs(calculation_run_ids: Sequence[Any]) -> List[Dict[str, Any]]:
    """Every product row belonging to an EXPLICIT list of calculation runs.

    The run list is the cohort boundary. There is deliberately no "all rows
    missing Collector Appeal" query here: that predicate has no date or run
    boundary and would sweep historical rows into a current-day enrichment.
    """
    ids = [str(value) for value in calculation_run_ids if value is not None]
    if not ids:
        return []
    response = (
        supabase.table(TABLE)
        .select(_SELECT_FIELDS)
        .in_("calculation_run_id", ids)
        .order("pack_count")
        .execute()
    )
    return list(response.data or [])


def get_sealed_product_results_for_run(calculation_run_id: Any) -> List[Dict[str, Any]]:
    response = (
        supabase.table(TABLE)
        .select(_SELECT_FIELDS)
        .eq("calculation_run_id", str(calculation_run_id))
        .order("pack_count")
        .execute()
    )
    return list(response.data or [])


def get_latest_sealed_product_results_for_set(set_id: Any) -> List[Dict[str, Any]]:
    """Every Stage 1 product row from the set's most recent scored run.

    "Latest" is resolved by run, not by row: taking the newest row per product
    could mix SKUs from different runs (and therefore different pack models) into
    one comparison table, which is exactly the thing a ranking must not do.
    """
    newest = (
        supabase.table(TABLE)
        .select("calculation_run_id,created_at")
        .eq("set_id", str(set_id))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = list(newest.data or [])
    if not rows:
        return []
    return get_sealed_product_results_for_run(rows[0]["calculation_run_id"])


def get_latest_sealed_product_result_for_family(set_id: Any, product_family: str) -> Optional[Dict[str, Any]]:
    """The best (highest Overall RIP, then Financial RIP) row for one family."""
    candidates = [
        row
        for row in get_latest_sealed_product_results_for_set(set_id)
        if str(row.get("product_family")) == str(product_family)
    ]
    if not candidates:
        return None

    def _rank_key(row: Dict[str, Any]) -> tuple:
        def _num(value: Any) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return float("-inf")

        return (_num(row.get("overall_rip_score")), _num(row.get("financial_rip_v3_score")))

    return max(candidates, key=_rank_key)
