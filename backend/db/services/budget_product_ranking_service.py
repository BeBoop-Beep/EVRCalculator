"""INTERNAL reader for Budget-Constrained Whole-Unit Product Rankings.

SERVICE-ROLE ONLY. Nothing in this module may be wired into a public payload,
API route, page prop, or entitlement surface. The underlying tables grant no
access to `anon`/`authenticated`, so a public caller cannot read them even if
this module were imported by mistake — this is the second lock, not the only
one.

WHAT A RANK MEANS HERE
----------------------
"Ranked #N of M among sealed products whose whole units fit within a $X
spending ceiling." The budget is part of the rank's identity: there is no
context-free "best product" row in this store, by design.

`budget_tier` is a SCORE tier derived from the Overall RIP V10 score, not a
rank percentile — rank #1 in a weak cohort is still whatever tier its own
score earns.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.calculations.evr.budget_normalized_product_ranking import (
    ALLOCATION_METHOD_VERSION,
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
    BUDGET_TYPE_FULL_MARKET,
)


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list((response.data if response else []) or [])


def load_latest_snapshot(
    client: Any,
    *,
    ranking_method_version: str = BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
    allocation_method_version: str = ALLOCATION_METHOD_VERSION,
) -> Optional[Dict[str, Any]]:
    """The current authoritative snapshot for one method pair, or None."""
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


def load_budget_ranking(
    client: Any,
    target_budget: float,
    *,
    budget_type: str = "standard_band",
    limit: Optional[int] = None,
    ranking_method_version: str = BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
    allocation_method_version: str = ALLOCATION_METHOD_VERSION,
) -> Dict[str, Any]:
    """One budget cohort, ordered by `budget_rank`.

    Returns the snapshot's authority alongside the rows so a caller can never
    render a rank without knowing which market state and budget produced it.
    """
    snapshot = load_latest_snapshot(
        client,
        ranking_method_version=ranking_method_version,
        allocation_method_version=allocation_method_version,
    )
    if snapshot is None:
        return {"available": False, "reason": "no_published_snapshot", "rows": []}

    query = (
        client.table("budget_product_ranking_rows").select("*")
        .eq("snapshot_id", str(snapshot["id"]))
        .eq("target_budget", target_budget)
        .eq("budget_type", budget_type)
        .order("budget_rank")
    )
    if limit is not None:
        query = query.limit(limit)
    rows = _rows(query.execute())

    return {
        "available": bool(rows),
        "reason": None if rows else "no_rows_for_budget",
        "targetBudget": target_budget,
        "budgetType": budget_type,
        "authority": _authority_block(snapshot),
        "cohortSize": rows[0]["budget_cohort_size"] if rows else 0,
        "rows": rows,
    }


def load_full_market_ranking(client: Any, **kwargs: Any) -> Dict[str, Any]:
    """The complete-cohort reference ranking.

    The Full Market anchor is DYNAMIC (next $50 above the max eligible SKU
    price), so its dollar value is read from the snapshot rather than assumed
    — never hard-code $1,350.
    """
    snapshot = load_latest_snapshot(client, **kwargs)
    if snapshot is None:
        return {"available": False, "reason": "no_published_snapshot", "rows": []}
    return load_budget_ranking(
        client,
        float(snapshot["full_market_budget"]),
        budget_type=BUDGET_TYPE_FULL_MARKET,
        **kwargs,
    )


def load_product_budget_ranks(client: Any, sealed_product_id: str, **kwargs: Any) -> Dict[str, Any]:
    """Every budget at which one SKU is ranked, cheapest budget first."""
    snapshot = load_latest_snapshot(client, **kwargs)
    if snapshot is None:
        return {"available": False, "reason": "no_published_snapshot", "rows": []}
    rows = _rows(
        client.table("budget_product_ranking_rows").select("*")
        .eq("snapshot_id", str(snapshot["id"]))
        .eq("sealed_product_id", str(sealed_product_id))
        .order("target_budget").execute()
    )
    return {
        "available": bool(rows),
        "reason": None if rows else "product_not_ranked_at_any_budget",
        "sealedProductId": str(sealed_product_id),
        "authority": _authority_block(snapshot),
        "rows": rows,
    }


def _authority_block(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "snapshotId": str(snapshot["id"]),
        "marketDate": snapshot["market_date"],
        "pinnedPriceAsOf": snapshot["pinned_price_as_of"],
        "rankingMethodVersion": snapshot["ranking_method_version"],
        "allocationMethodVersion": snapshot["allocation_method_version"],
        "comparisonScopeVersion": snapshot["comparison_scope_version"],
        "financialRipVersion": snapshot["financial_rip_version"],
        "overallRipVersion": snapshot["overall_rip_version"],
        "collectorAppealVersion": snapshot["collector_appeal_version"],
        "eligibleCohortCount": snapshot["eligible_cohort_count"],
        "cohortFingerprint": snapshot["cohort_fingerprint"],
        "fullMarketBudget": snapshot["full_market_budget"],
        "maxEligibleSkuPrice": snapshot["max_eligible_sku_price"],
        "fullMarketRoundingIncrement": snapshot["full_market_rounding_increment"],
        "fullMarketRoundingRuleVersion": snapshot["full_market_rounding_rule_version"],
    }
