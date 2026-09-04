"""Service-role reader for Budget-Constrained Whole-Unit Product Rankings.

SERVICE-ROLE ONLY. Only the explicit allowlisted projection built at the end
of this module may enter the existing public Rankings snapshot. The tables grant no
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
    CANONICAL_BUDGET_BANDS,
)
from backend.domain.pokemon.sealed_product_classifier import FAMILY_LABELS
from backend.rankings.public_relative import (
    compute_leader_normalized_scores, compute_public_relative_scores, public_leader_rip_tier,
)

PUBLIC_ROW_FIELDS = (
    "sealed_product_id,set_id,product_family,target_budget,budget_type,quantity,"
    "actual_committed_capital,unused_capital,capital_utilization,budget_rank,"
    "budget_cohort_size,budget_tier,financial_rip_v4_score,overall_rip_v10_score,"
    "collector_appeal_score,chance_to_recover_capital,product_market_price,"
    "expected_value,source_calculation_run_id,"
    "overall_rip_v12_score,budget_rank_v12,budget_cohort_size_v12"
)


def snapshot_ranked_under_v12_authority(snapshot: Dict[str, Any]) -> bool:
    """No-mixed-authority invariant (Gate F closure, Phase 10): the ONE place
    that decides whether a published snapshot's GENERIC current read (as
    opposed to the always-available, always-V10 diagnostic fields) resolves
    to Overall RIP V12 or V10. Never inferred from anything but the
    snapshot's own explicit ``ranked_under_v12_authority`` flag, exactly the
    field the publication RPC persists under explicit V12 opt-in.
    """
    return bool(snapshot.get("ranked_under_v12_authority"))


def resolve_generic_overall_score(row: Dict[str, Any], snapshot: Dict[str, Any]) -> Optional[float]:
    """The generic/current Overall RIP score for one row: V12 when the
    snapshot was ranked under V12 authority, V10 otherwise. Never a mix -
    when the snapshot is V12-authority, the V10 score is never substituted
    even if the V12 score happens to be missing (that indicates a data
    defect, not a fallback opportunity)."""
    if snapshot_ranked_under_v12_authority(snapshot):
        return row.get("overall_rip_v12_score")
    return row.get("overall_rip_v10_score")


def resolve_generic_budget_rank(row: Dict[str, Any], snapshot: Dict[str, Any]) -> Optional[int]:
    if snapshot_ranked_under_v12_authority(snapshot):
        return row.get("budget_rank_v12")
    return row.get("budget_rank")


def resolve_generic_budget_cohort_size(row: Dict[str, Any], snapshot: Dict[str, Any]) -> Optional[int]:
    if snapshot_ranked_under_v12_authority(snapshot):
        return row.get("budget_cohort_size_v12")
    return row.get("budget_cohort_size")


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list((response.data if response else []) or [])


def public_budget_cohort_presentation(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Presentation-only relative fields for exactly one selected budget cohort."""
    overall = compute_public_relative_scores(
        rows, id_getter=lambda row: row.get("sealed_product_id"),
        score_getter=lambda row: row.get("overall_rip_v10_score"),
    )
    financial = compute_public_relative_scores(
        rows, id_getter=lambda row: row.get("sealed_product_id"),
        score_getter=lambda row: row.get("financial_rip_v4_score"),
    )
    overall_leader = compute_leader_normalized_scores(
        rows, id_getter=lambda row: row.get("sealed_product_id"),
        score_getter=lambda row: row.get("overall_rip_v10_score"),
    )
    financial_leader = compute_leader_normalized_scores(
        rows, id_getter=lambda row: row.get("sealed_product_id"),
        score_getter=lambda row: row.get("financial_rip_v4_score"),
    )
    return {
        str(row.get("sealed_product_id")): {
            "overallRipAbsoluteScore": row.get("overall_rip_v10_score"),
            "overallRipRelativeScore": overall.get(str(row.get("sealed_product_id"))),
            "overallRipLeaderScore": overall_leader.get(str(row.get("sealed_product_id"))),
            "financialRipAbsoluteScore": row.get("financial_rip_v4_score"),
            "financialRipRelativeScore": financial.get(str(row.get("sealed_product_id"))),
            "financialRipLeaderScore": financial_leader.get(str(row.get("sealed_product_id"))),
            "budgetModelTier": row.get("budget_tier"),
            "publicTier": public_leader_rip_tier(overall_leader.get(str(row.get("sealed_product_id")))),
        }
        for row in rows
    }


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
        "rankedUnderV12Authority": snapshot_ranked_under_v12_authority(snapshot),
    }


def build_public_overall_projection(
    client: Any,
    *,
    product_family_rankings: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the narrow public snapshot projection; never return raw table rows."""
    snapshot = load_latest_snapshot(client)
    if snapshot is None:
        return {"available": False, "reason": "no_published_snapshot", "cohorts": {}}

    rows = _rows(
        client.table("budget_product_ranking_rows")
        .select(PUBLIC_ROW_FIELDS)
        .eq("snapshot_id", str(snapshot["id"]))
        .order("target_budget")
        .order("budget_rank")
        .execute()
    )
    if not rows or any(row.get("expected_value") is None for row in rows):
        return {"available": False, "reason": "strategy_expected_value_not_published", "cohorts": {}}

    product_identity: Dict[str, Dict[str, Any]] = {}
    for family in (product_family_rankings.get("families") or {}).values():
        for product in family.get("products") or []:
            product_identity[str(product.get("sealedProductId"))] = product

    def project(row: Dict[str, Any]) -> Dict[str, Any]:
        identity = product_identity.get(str(row.get("sealed_product_id")), {})
        family = str(row.get("product_family") or "")
        return {
            "sealedProductId": row.get("sealed_product_id"),
            "setId": row.get("set_id"),
            "productName": identity.get("productName"),
            "setName": identity.get("setName"),
            "setCanonicalKey": identity.get("setCanonicalKey"),
            "setImage": identity.get("setImage"),
            "productFamily": family,
            "productFamilyLabel": identity.get("productFamilyLabel") or FAMILY_LABELS.get(family, family.replace("_", " ").title()),
            # Generic/current authority: resolves to V12 rank/score when this
            # snapshot was ranked under explicit V12 authority, V10
            # otherwise - never a mix (see `resolve_generic_*` above).
            "budgetRank": resolve_generic_budget_rank(row, snapshot),
            "budgetCohortSize": resolve_generic_budget_cohort_size(row, snapshot),
            "budgetTier": row.get("budget_tier"),
            "quantity": row.get("quantity"),
            "actualCommittedCapital": row.get("actual_committed_capital"),
            "unusedCapital": row.get("unused_capital"),
            "capitalUtilization": row.get("capital_utilization"),
            "overallRipScore": resolve_generic_overall_score(row, snapshot),
            # Historical V10 diagnostic field - always the V10 value,
            # unaffected by which authority is generically current.
            "overallRipV10Score": row.get("overall_rip_v10_score"),
            "financialRipScore": row.get("financial_rip_v4_score"),
            "collectorAppealScore": row.get("collector_appeal_score"),
            "unitPrice": row.get("product_market_price"),
            "expectedValue": row.get("expected_value"),
            "chanceToRecoverCapital": row.get("chance_to_recover_capital"),
            "familyRank": identity.get("familyRank"),
            "familySize": identity.get("familySize"),
            "familyTier": identity.get("familyTier"),
            "sourceCalculationRunId": row.get("source_calculation_run_id"),
        }

    cohorts: Dict[str, Any] = {}
    for row in rows:
        key = f"{row['budget_type']}:{float(row['target_budget']):g}"
        block = cohorts.setdefault(key, {
            "targetBudget": row["target_budget"],
            "budgetType": row["budget_type"],
            "rankedCount": row["budget_cohort_size"],
            "rows": [],
        })
        block["rows"].append(project(row))

    full_market_budget = snapshot["full_market_budget"]
    available_budgets = [
        {"key": f"standard_band:{budget:g}", "targetBudget": budget, "budgetType": "standard_band"}
        for budget in CANONICAL_BUDGET_BANDS
    ]
    available_budgets.append({
        "key": f"full_market:{float(full_market_budget):g}",
        "targetBudget": full_market_budget,
        "budgetType": BUDGET_TYPE_FULL_MARKET,
    })
    authority = _authority_block(snapshot)
    authority.pop("cohortFingerprint", None)
    return {
        "available": True,
        "defaultBudgetKey": f"full_market:{float(full_market_budget):g}",
        "fullMarketBudget": full_market_budget,
        "availableBudgets": available_budgets,
        "authority": authority,
        "cohorts": cohorts,
    }
