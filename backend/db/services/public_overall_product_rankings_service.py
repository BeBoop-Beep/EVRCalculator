"""Narrow public projection for one budget cohort; raw stores stay private."""
from __future__ import annotations

from typing import Any, Dict, Mapping

from backend.calculations.evr.budget_normalized_product_ranking import (
    BUDGET_TYPE_FULL_MARKET, CANONICAL_BUDGET_BANDS,
)
from backend.db.clients.supabase_client import service_read_client
from backend.db.services.budget_product_ranking_service import (
    load_budget_ranking, load_full_market_ranking, load_latest_snapshot,
    public_budget_cohort_presentation,
)


def _identity_index(product_family_rankings: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        str(product.get("sealedProductId")): product
        for family in (product_family_rankings.get("families") or {}).values()
        for product in (family.get("products") or [])
    }


def read_public_overall_product_rankings(
    budget: str = "full_market", *, product_family_rankings: Mapping[str, Any], client: Any = None
) -> Dict[str, Any]:
    client = client or service_read_client
    snapshot = load_latest_snapshot(client)
    if snapshot is None:
        return {"available": False, "reason": "no_published_authority", "rows": []}
    if budget == "full_market":
        result = load_full_market_ranking(client)
    else:
        try:
            value = float(budget)
        except (TypeError, ValueError):
            return {"available": False, "reason": "invalid_budget", "rows": []}
        if value not in CANONICAL_BUDGET_BANDS:
            return {"available": False, "reason": "invalid_budget", "rows": []}
        result = load_budget_ranking(client, value)

    identities = _identity_index(product_family_rankings)
    raw_rows = result.get("rows") or []
    presentation = public_budget_cohort_presentation(raw_rows)
    rows = []
    for raw in raw_rows:
        identity = identities.get(str(raw.get("sealed_product_id")), {})
        product_id = str(raw.get("sealed_product_id"))
        public = presentation.get(product_id, {})
        rows.append({
            "sealedProductId": raw.get("sealed_product_id"), "setId": raw.get("set_id"),
            "productName": identity.get("productName"), "setName": identity.get("setName"),
            "productFamily": raw.get("product_family"), "productFamilyLabel": identity.get("productFamilyLabel"),
            "productImageUrl": identity.get("productImageUrl"),
            "budgetRank": raw.get("budget_rank"), "budgetCohortSize": raw.get("budget_cohort_size"),
            "budgetTier": raw.get("budget_tier"), "budgetModelTier": public.get("budgetModelTier"),
            "publicTier": public.get("publicTier"),
            "quantity": raw.get("quantity"),
            "actualCommittedCapital": raw.get("actual_committed_capital"), "unusedCapital": raw.get("unused_capital"),
            "overallRipScore": raw.get("overall_rip_v10_score"), "financialRipScore": raw.get("financial_rip_v4_score"),
            "overallRipAbsoluteScore": public.get("overallRipAbsoluteScore"),
            "overallRipRelativeScore": public.get("overallRipRelativeScore"),
            "overallRipLeaderScore": public.get("overallRipLeaderScore"),
            "financialRipAbsoluteScore": public.get("financialRipAbsoluteScore"),
            "financialRipRelativeScore": public.get("financialRipRelativeScore"),
            "financialRipLeaderScore": public.get("financialRipLeaderScore"),
            "collectorAppealScore": raw.get("collector_appeal_score"), "unitPrice": raw.get("product_market_price"),
            "expectedValue": raw.get("expected_value"), "chanceToRecoverCost": raw.get("chance_to_recover_capital"),
            "familyRank": identity.get("familyRank"), "familySize": identity.get("familySize"), "familyTier": identity.get("familyTier"),
        })
    if rows and any(row.get("expectedValue") is None or not row.get("productName") for row in rows):
        return {"available": False, "reason": "public_projection_incomplete", "rows": []}

    target = float(snapshot["full_market_budget"]) if budget == "full_market" else float(budget)
    budget_type = BUDGET_TYPE_FULL_MARKET if budget == "full_market" else "standard_band"
    full_market_value = float(snapshot["full_market_budget"])
    available = [{"value": float(value), "type": "standard_band", "label": f"${value:,.0f}"}
                 for value in CANONICAL_BUDGET_BANDS if float(value) != full_market_value]
    available.append({"value": full_market_value, "type": BUDGET_TYPE_FULL_MARKET, "label": f"${full_market_value:,.0f}"})
    authority = result.get("authority") or {}
    authority = {key: authority.get(key) for key in (
        "snapshotId", "marketDate", "fullMarketBudget", "rankingMethodVersion", "allocationMethodVersion",
        "comparisonScopeVersion", "financialRipVersion", "overallRipVersion", "collectorAppealVersion",
    )}
    return {"available": bool(rows), "reason": None if rows else "no_rows_for_budget", "authority": authority,
            "selectedBudget": {"value": target, "type": budget_type, "label": available[-1]["label"] if budget_type == BUDGET_TYPE_FULL_MARKET else f"${target:g}"},
            "availableBudgets": available, "cohortSize": len(rows), "rows": rows}
