"""Narrow public projection for one budget cohort; raw stores stay private."""
from __future__ import annotations

from typing import Any, Dict, Mapping, Tuple

from backend.calculations.evr.best_open_price import (
    BEST_OPEN_PRICE_METHOD_VERSION, BEST_OPEN_PRICE_V2_METHOD_VERSION,
)
from backend.calculations.evr.budget_normalized_product_ranking import (
    BUDGET_TYPE_FULL_MARKET, CANONICAL_BUDGET_BANDS,
)
from backend.db.clients.supabase_client import service_read_client
from backend.db.services.budget_product_best_open_price_service import load_best_open_price_ranking
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


def _best_open_price_projection(
    client: Any, snapshot: Mapping[str, Any], raw_rows: list[Mapping[str, Any]], budget: str,
) -> Tuple[Dict[str, Any], Dict[str, Mapping[str, Any]]]:
    """Load the prepared Best-Open layer without making Product Rankings depend on it.

    Best-Open Price is defined only for the published Full Market cohort. Any
    missing/stale/incomplete/mismatched prepared authority therefore hides only
    this optional layer; the underlying Product Rankings response remains live.
    """
    if budget != "full_market":
        return {"available": False, "reason": "full_market_only"}, {}

    # CURRENT-authority selection: a current, complete, source-matched V2
    # publication is always attempted first. V1 is only used when it
    # independently passes the exact same currentness/completeness rule
    # (`load_best_open_price_ranking` enforces this identically for either
    # method version) -- a stale V1 publication must never mask a valid
    # current V2 one, and an incomplete/stale V1 must not be served either.
    try:
        prepared = load_best_open_price_ranking(
            client, best_open_price_method_version=BEST_OPEN_PRICE_V2_METHOD_VERSION,
        )
        if not prepared.get("available"):
            prepared = load_best_open_price_ranking(
                client, best_open_price_method_version=BEST_OPEN_PRICE_METHOD_VERSION,
            )
    except Exception:
        return {"available": False, "reason": "prepared_read_failed"}, {}
    if not prepared.get("available"):
        return {"available": False, "reason": prepared.get("reason") or "prepared_unavailable"}, {}

    expected_identity = (
        str(snapshot.get("id")),
        str(snapshot.get("published_at")),
        str(snapshot.get("market_date")),
        str(snapshot.get("cohort_fingerprint")),
    )
    prepared_identity = (
        str(prepared.get("sourceBudgetSnapshotId")),
        str(prepared.get("sourceBudgetPublishedAt")),
        str(prepared.get("sourceMarketDate")),
        str(prepared.get("sourceCohortFingerprint")),
    )
    if any(value in {"None", ""} for value in expected_identity) or prepared_identity != expected_identity:
        return {"available": False, "reason": "source_mismatch"}, {}

    prepared_rows = [row for row in (prepared.get("rows") or []) if isinstance(row, Mapping)]
    expected_ids = {str(row.get("sealed_product_id")) for row in raw_rows if row.get("sealed_product_id")}
    prepared_ids = {str(row.get("sealed_product_id")) for row in prepared_rows if row.get("sealed_product_id")}
    if (
        int(prepared.get("unresolvedCount") or 0) != 0
        or int(prepared.get("resolvedCount") or 0) != len(raw_rows)
        or prepared_ids != expected_ids
    ):
        return {"available": False, "reason": "incomplete_snapshot_rows"}, {}

    return {
        "available": True,
        "reason": None,
        "snapshotId": prepared.get("snapshotId"),
        "methodVersion": prepared.get("methodVersion"),
        "sourceMarketDate": prepared.get("sourceMarketDate"),
        "sourceBudgetSnapshotId": prepared.get("sourceBudgetSnapshotId"),
    }, {str(row.get("sealed_product_id")): row for row in prepared_rows}


def read_public_overall_product_rankings(
    budget: str = "full_market", *, product_family_rankings: Mapping[str, Any], client: Any = None
) -> Dict[str, Any]:
    client = client or service_read_client
    snapshot = load_latest_snapshot(client)
    if snapshot is None:
        return {"available": False, "reason": "no_published_authority", "rows": []}
    if budget == "full_market":
        result = load_full_market_ranking(client, source_snapshot=snapshot)
    else:
        try:
            value = float(budget)
        except (TypeError, ValueError):
            return {"available": False, "reason": "invalid_budget", "rows": []}
        if value not in CANONICAL_BUDGET_BANDS:
            return {"available": False, "reason": "invalid_budget", "rows": []}
        result = load_budget_ranking(client, value, source_snapshot=snapshot)

    if result.get("available") is False:
        return {"available": False, "reason": result.get("reason") or "no_rows_for_budget", "rows": []}

    identities = _identity_index(product_family_rankings)
    raw_rows = result.get("rows") or []
    presentation = public_budget_cohort_presentation(raw_rows, snapshot)
    best_open_price, best_open_by_id = _best_open_price_projection(client, snapshot, raw_rows, budget)
    best_open_is_v2 = best_open_price.get("methodVersion") == BEST_OPEN_PRICE_V2_METHOD_VERSION
    rows = []
    for raw in raw_rows:
        identity = identities.get(str(raw.get("sealed_product_id")), {})
        product_id = str(raw.get("sealed_product_id"))
        public = presentation.get(product_id, {})
        best_open = best_open_by_id.get(product_id) if best_open_price.get("available") else None
        projected = {
            "sealedProductId": raw.get("sealed_product_id"), "setId": raw.get("set_id"),
            "productName": identity.get("productName"), "setName": identity.get("setName"),
            "productFamily": raw.get("product_family"), "productFamilyLabel": identity.get("productFamilyLabel"),
            "productImageUrl": identity.get("productImageUrl"), "setCanonicalKey": identity.get("setCanonicalKey"),
            "budgetRank": public.get("budgetRank"), "budgetCohortSize": public.get("budgetCohortSize"),
            "budgetTier": raw.get("budget_tier"), "budgetModelTier": public.get("budgetModelTier"),
            "publicTier": public.get("publicTier"),
            "quantity": raw.get("quantity"),
            "actualCommittedCapital": raw.get("actual_committed_capital"), "unusedCapital": raw.get("unused_capital"),
            "overallRipScore": public.get("overallRipScore"), "financialRipScore": raw.get("financial_rip_v4_score"),
            "overallRipAbsoluteScore": public.get("overallRipAbsoluteScore"),
            "overallRipRelativeScore": public.get("overallRipRelativeScore"),
            "overallRipLeaderScore": public.get("overallRipLeaderScore"),
            "financialRipAbsoluteScore": public.get("financialRipAbsoluteScore"),
            "financialRipRelativeScore": public.get("financialRipRelativeScore"),
            "financialRipLeaderScore": public.get("financialRipLeaderScore"),
            "collectorAppealScore": raw.get("collector_appeal_score"), "unitPrice": raw.get("product_market_price"),
            "expectedValue": raw.get("expected_value"), "chanceToRecoverCost": raw.get("chance_to_recover_capital"),
            # Exact q-unit strategy distribution values, persisted verbatim by
            # the builder (never recomputed here). A legacy/historical
            # snapshot row published before this contract has NULL
            # `median_value`/`top1_outcome_value_share` — those rows must
            # keep rendering with these three fields unavailable rather than
            # crash or silently show a computed-looking zero. Average Return
            # is simple presentation arithmetic over already-persisted
            # authority values (expected_value / actual_committed_capital) —
            # NOT request-time strategy scoring — and is likewise unavailable
            # whenever either operand is missing/non-positive.
            "medianValue": raw.get("median_value"),
            "topOneOutcomeValueShare": raw.get("top1_outcome_value_share"),
            "averageReturn": (
                float(raw["expected_value"]) / float(raw["actual_committed_capital"])
                if raw.get("expected_value") is not None
                and raw.get("actual_committed_capital") not in (None, 0)
                else None
            ),
            "familyRank": identity.get("familyRank"), "familySize": identity.get("familySize"), "familyTier": identity.get("familyTier"),
            # SET-level authority, carried verbatim off the same in-memory
            # `product_family_rankings` identity index this function already
            # builds — no extra query. See
            # backend/db/services/chase_accessibility_set_ranking.py.
            "chaseAccessibility": identity.get("chaseAccessibility"),
        }
        if best_open is not None:
            projected.update({
                "bestOpenPrice": best_open.get("best_open_price"),
                "bestOpenPriceStatus": best_open.get("status"),
                "bestOpenPriceGapDollars": best_open.get("price_gap_dollars"),
                "bestOpenPriceGapPercent": best_open.get("price_gap_percent"),
            })
            # `ripBestOpenPrice*`/`financialBestOpenPrice*` are V2-only
            # response-shape additions (Finding 2). They must never appear
            # for a row served from a V1 publication -- gated on the
            # publication-level `methodVersion` selected above, not merely on
            # field presence, so a V1 row's shape stays byte-identical to the
            # historical contract.
            if best_open_is_v2:
                projected.update({
                    "ripBestOpenPrice": best_open.get("best_open_price"),
                    "ripBestOpenPriceStatus": best_open.get("status"),
                    "ripBestOpenPriceGapDollars": best_open.get("price_gap_dollars"),
                    "ripBestOpenPriceGapPercent": best_open.get("price_gap_percent"),
                })
                if best_open.get("financial_best_open_price") is not None:
                    projected.update({
                        "financialBestOpenPrice": best_open.get("financial_best_open_price"),
                        "financialBestOpenPriceStatus": best_open.get("financial_status"),
                        "financialBestOpenPriceGapDollars": best_open.get("financial_price_gap_dollars"),
                        "financialBestOpenPriceGapPercent": best_open.get("financial_price_gap_percent"),
                    })
        rows.append(projected)
    required_generic_fields = ("overallRipScore", "budgetRank", "budgetCohortSize")
    if rows and any(
        row.get("expectedValue") is None
        or not row.get("productName")
        or any(row.get(field) is None for field in required_generic_fields)
        for row in rows
    ):
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
    return {
        "available": bool(rows),
        "reason": None if rows else "no_rows_for_budget",
        "authority": authority,
        "bestOpenPrice": best_open_price,
        "selectedBudget": {
            "value": target,
            "type": budget_type,
            "label": available[-1]["label"] if budget_type == BUDGET_TYPE_FULL_MARKET else f"${target:g}",
        },
        "availableBudgets": available,
        "cohortSize": len(rows),
        "rows": rows,
    }
