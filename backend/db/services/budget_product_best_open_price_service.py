"""Service-role PRIVATE persistence/read service for Best-Open Price results.

SERVICE-ROLE ONLY. No public projection exists in this module by design --
Bucket 3A is persistence + atomic publication only, with no frontend/API
exposure. Scoring logic lives exclusively in
``backend.calculations.evr.best_open_price``; this module never computes a
threshold, it only builds a deterministic publish payload from already-
validated engine results, calls the publication RPC, and reads back the
latest snapshot with the stale-read rule enforced.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.calculations.evr.best_open_price import BEST_OPEN_PRICE_METHOD_VERSION

RPC_NAME = "publish_budget_product_best_open_price_snapshot"


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list((response.data if response else []) or [])


def content_fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
    """Deterministic fingerprint of the row payload, order-independent on
    identity but sensitive to every persisted field -- mirrors what the RPC
    computes server-side over the JSON text it receives, so a caller can
    detect drift before even attempting a publish."""
    encoded = json.dumps(
        sorted(rows, key=lambda row: str(row.get("sealed_product_id"))),
        sort_keys=True, default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_snapshot_payload(
    *,
    built_at: str,
    source_budget_snapshot_id: str,
    source_budget_published_at: str,
    source_market_date: str,
    source_cohort_fingerprint: str,
    source_full_market_row_fingerprint: str,
    source_full_market_budget: float,
    source_eligible_cohort_count: int,
    ranking_method_version: str,
    allocation_method_version: str,
    comparison_scope_version: str,
    financial_rip_version: str,
    overall_rip_v12_version: str,
    collector_appeal_version: str,
    chase_accessibility_version: str,
    chase_accessibility_transform_version: str,
    resolved_count: int,
    unresolved_count: int,
    runtime_seconds: float,
    best_open_price_method_version: str = BEST_OPEN_PRICE_METHOD_VERSION,
    diagnostics_json: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the snapshot half of the publish payload. Pure function -- no
    I/O, no scoring. Every field named here is re-verified by the RPC
    against the LIVE budget ranking authority; this function only shapes
    already-computed values into the wire format."""
    return {
        "built_at": built_at,
        "source_budget_snapshot_id": source_budget_snapshot_id,
        "source_budget_published_at": source_budget_published_at,
        "source_market_date": source_market_date,
        "source_cohort_fingerprint": source_cohort_fingerprint,
        "source_full_market_row_fingerprint": source_full_market_row_fingerprint,
        "source_full_market_budget": source_full_market_budget,
        "source_eligible_cohort_count": source_eligible_cohort_count,
        "ranking_method_version": ranking_method_version,
        "allocation_method_version": allocation_method_version,
        "comparison_scope_version": comparison_scope_version,
        "financial_rip_version": financial_rip_version,
        "overall_rip_v12_version": overall_rip_v12_version,
        "collector_appeal_version": collector_appeal_version,
        "chase_accessibility_version": chase_accessibility_version,
        "chase_accessibility_transform_version": chase_accessibility_transform_version,
        "best_open_price_method_version": best_open_price_method_version,
        "resolved_count": resolved_count,
        "unresolved_count": unresolved_count,
        "runtime_seconds": runtime_seconds,
        "diagnostics_json": dict(diagnostics_json or {}),
    }


def build_row_payload(engine_row: Mapping[str, Any]) -> Dict[str, Any]:
    """Project one validated Bucket-2.x-shaped engine result row (as produced
    by ``backend/scripts/research_best_open_price_bucket2.py``) into the
    wire format the RPC expects. Only fields already computed by the engine
    are consumed -- no re-derivation, no re-scoring."""
    return {
        "sealed_product_id": engine_row["sealedProductId"],
        "set_id": engine_row["setId"],
        "product_family": engine_row.get("productFamily"),
        "source_calculation_run_id": engine_row.get("sourceCalculationRunId"),
        "current_market_price": engine_row["currentMarketPrice"],
        "current_quantity": engine_row["currentQuantity"],
        "current_budget_rank": engine_row["currentBudgetRank"],
        "current_overall_rip_v12_score": engine_row.get("currentOverallRipV12Score"),
        "status": engine_row["status"],
        "best_open_price": engine_row["bestOpenPrice"],
        "threshold_quantity": engine_row["thresholdQuantity"],
        "price_gap_dollars": engine_row["priceGapDollars"],
        "price_gap_percent": engine_row.get("priceGapPercent"),
        "benchmark_sealed_product_id": engine_row["benchmarkSealedProductId"],
        "benchmark_overall_rip_v12_score": engine_row["benchmarkOverallRipV12Score"],
        "candidate_price_evaluations": engine_row.get("candidatePriceEvaluations", 0),
        "bracket_expansions": engine_row.get("bracketExpansions", 0),
        "bracket_refinements": engine_row.get("bracketRefinements", 0),
        "monotonicity_fallback_count": engine_row.get("fallbackCount", 0),
        "search_wall_seconds": engine_row.get("searchWallSeconds", 0.0),
    }


def publish_snapshot(client: Any, snapshot: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> str:
    """Call the atomic publication RPC. Raises on any failure; the RPC
    itself guarantees the transaction rolls back completely on error, so
    there is nothing partial to clean up here."""
    response = client.rpc(RPC_NAME, {"p_snapshot": dict(snapshot), "p_rows": list(rows)}).execute()
    return str(response.data)


def load_latest_snapshot(
    client: Any, *, best_open_price_method_version: str = BEST_OPEN_PRICE_METHOD_VERSION,
) -> Optional[Dict[str, Any]]:
    latest = _rows(
        client.table("budget_product_best_open_price_latest").select("*")
        .eq("best_open_price_method_version", best_open_price_method_version)
        .limit(1).execute()
    )
    if not latest:
        return None
    snapshots = _rows(
        client.table("budget_product_best_open_price_snapshots").select("*")
        .eq("id", str(latest[0]["snapshot_id"])).limit(1).execute()
    )
    return snapshots[0] if snapshots else None


def _live_budget_source_identity(client: Any, ranking_method_version: str, allocation_method_version: str) -> Optional[Dict[str, Any]]:
    latest = _rows(
        client.table("budget_product_ranking_latest").select("*")
        .eq("ranking_method_version", ranking_method_version)
        .eq("allocation_method_version", allocation_method_version)
        .limit(1).execute()
    )
    if not latest:
        return None
    snapshots = _rows(
        client.table("budget_product_ranking_snapshots").select("*")
        .eq("id", str(latest[0]["snapshot_id"])).limit(1).execute()
    )
    return snapshots[0] if snapshots else None


def load_best_open_price_ranking(
    client: Any, *, best_open_price_method_version: str = BEST_OPEN_PRICE_METHOD_VERSION,
) -> Dict[str, Any]:
    """Load the latest published Best-Open Price snapshot+rows, enforcing
    the stale-read rule: whenever the CURRENT live budget-ranking source no
    longer exactly matches the persisted snapshot's source binding, this
    returns ``available=false, reason="stale_source_publication"`` rather
    than silently serving a stale/previous snapshot."""
    snapshot = load_latest_snapshot(client, best_open_price_method_version=best_open_price_method_version)
    if snapshot is None:
        return {"available": False, "reason": "no_published_snapshot", "rows": []}

    live_source = _live_budget_source_identity(
        client, snapshot["ranking_method_version"], snapshot["allocation_method_version"],
    )
    if live_source is None:
        return {"available": False, "reason": "no_live_budget_ranking_source", "rows": []}

    if (
        str(live_source["id"]) != str(snapshot["source_budget_snapshot_id"])
        or str(live_source["published_at"]) != str(snapshot["source_budget_published_at"])
        or str(live_source["market_date"]) != str(snapshot["source_market_date"])
        or str(live_source["cohort_fingerprint"]) != str(snapshot["source_cohort_fingerprint"])
    ):
        return {"available": False, "reason": "stale_source_publication", "rows": []}

    rows = _rows(
        client.table("budget_product_best_open_price_rows").select("*")
        .eq("snapshot_id", str(snapshot["id"]))
        .execute()
    )
    if len(rows) != snapshot["resolved_count"]:
        return {"available": False, "reason": "incomplete_snapshot_rows", "rows": []}

    return {
        "available": True,
        "reason": None,
        "snapshotId": str(snapshot["id"]),
        "builtAt": snapshot["built_at"],
        "publishedAt": snapshot["published_at"],
        "sourceBudgetSnapshotId": str(snapshot["source_budget_snapshot_id"]),
        "resolvedCount": snapshot["resolved_count"],
        "unresolvedCount": snapshot["unresolved_count"],
        "rows": rows,
    }
