"""EXPLICIT (non-default, non-scheduled) Budget Product Ranking V2 orchestration.

Ranking V2 scores each whole-unit budget strategy with Financial RIP V5 and Overall RIP V14 and publishes
through the versioned RPC branch validated on real PostgreSQL. It is selected only by calling this module;
nothing imports it from a default or scheduled path, and the V1/V12 builders are untouched.

Preconditions (fail closed, never fall back to V4/V12):
  * the request must name ``budget_product_ranking_v2`` explicitly - a V1 request is never relabelled;
  * every source sealed-product row of the cohort must carry a READY Financial RIP V5 (the persisted
    result of the exact-artifact finalizer). Until the V5 schema/data has landed, a commit-capable run
    therefore reports "not ready" truthfully rather than computing V5 ad hoc from an unverified source;
  * Chase Accessibility must be same-run and Collector Appeal must be V5 (resolved by the shared helpers).

Allocation (floor quantity, Full Market anchor, $50 rounding) is unchanged from V1.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from backend.calculations.evr.budget_normalized_product_ranking import (
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2,
    BUDGET_TYPE_FULL_MARKET,
    BUDGET_TYPE_STANDARD,
    CANONICAL_BUDGET_BANDS,
    build_budget_strategy_values,
    rank_budget_cohort_v2,
    resolve_full_market_budget,
    score_budget_strategy_v2,
    whole_unit_allocation,
)
from backend.calculations.evr.financial_rip_v5_config import FINANCIAL_RIP_V5_VERSION
from backend.db.services.budget_v2_v3_publication_payloads import (
    build_ranking_v2_rows,
    build_ranking_v2_snapshot,
)


class RankingV2NotReady(RuntimeError):
    """The V2 source authority is not ready; carries a stable reason and detail list."""

    def __init__(self, reason: str, details: Sequence[Any] = ()):
        super().__init__(f"{reason}: {list(details)[:5]}" if details else reason)
        self.reason, self.details = reason, list(details)


def require_explicit_v2_request(method_version: Optional[str]) -> None:
    """A V1 (or defaulted/None) request can never be turned into a V2 publication."""
    if method_version != BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2:
        raise RankingV2NotReady(
            "ranking_v2_must_be_requested_explicitly",
            [f"got {method_version!r}; V1 is {BUDGET_NORMALIZED_RANKING_METHOD_VERSION!r} and is never relabelled"])


def require_v5_source_rows(products: Sequence[Mapping[str, Any]]) -> None:
    """Every source row needs a ready exact Financial V5. No V4 fallback, no ad hoc computation."""
    bad = [str(p.get("sealed_product_id")) for p in products
           if not (p.get("financial_rip_v5_version") == FINANCIAL_RIP_V5_VERSION
                   and p.get("financial_rip_v5_status") == "ready" and p.get("financial_rip_v5_score") is not None
                   and p.get("financial_rip_v5_rankable") is True)]
    if bad:
        raise RankingV2NotReady("financial_v5_source_rows_not_ready", bad)


def read_v5_source_rows(products: Sequence[Mapping[str, Any]], *, client: Any = None,
                        reader_fn: Optional[Callable[..., Sequence[Mapping[str, Any]]]] = None) -> List[Dict[str, Any]]:
    """Attach the persisted V5 columns to the product rows, or report the schema as not landed."""
    if reader_fn is None:
        from backend.db.repositories.sealed_product_results_repository import (
            get_sealed_product_financial_v5_for_runs as reader_fn,  # type: ignore[misc]
        )
    runs = sorted({str(p["calculation_run_id"]) for p in products})
    try:
        v5_rows = list(reader_fn(runs, client=client) if client is not None else reader_fn(runs))
    except Exception as exc:  # PostgREST 42703 (undefined column) until the V5 migration has landed
        text = str(exc)
        if "42703" in text or "financial_rip_v5" in text:
            raise RankingV2NotReady("financial_v5_schema_not_landed", [text[:200]]) from exc
        raise
    by_key = {(str(r["calculation_run_id"]), str(r["sealed_product_id"])): r for r in v5_rows}
    merged: List[Dict[str, Any]] = []
    for p in products:
        v5 = by_key.get((str(p["calculation_run_id"]), str(p["sealed_product_id"]))) or {}
        merged.append({**p, **{k: v for k, v in v5.items() if k.startswith("financial_rip_v5_")}})
    return merged


def rank_one_budget_v2(*, engine_products: Sequence[Mapping[str, Any]], base_values_for: Callable[[Mapping[str, Any]], Any],
                       target_budget: float, budget_type: str, accessibility_raw_for: Callable[[Any], Any],
                       full_market: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Rank one budget ceiling under Financial V5 / Overall V14. No Accessibility I/O in here."""
    strategies: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    for product in engine_products:
        price = float(product["product_market_cost"])
        allocation = whole_unit_allocation(target_budget, price)
        if not allocation["eligible"]:
            excluded.append({"sealedProductId": str(product["sealed_product_id"]), "unitPrice": price,
                             "reason": "price_exceeds_budget"})
            continue
        a_raw = accessibility_raw_for(product["set_id"])
        values = build_budget_strategy_values(
            base_random_pack_values=base_values_for(product), quantity=allocation["quantity"],
            guaranteed_component_market_value=product.get("guaranteed_component_market_value"),
            canonical_set_key="budget:%s" % product["sealed_product_id"], run_fingerprint=None)
        scored = score_budget_strategy_v2(
            values, allocation["actualCommittedCapital"], product.get("collector_appeal_score"),
            chase_accessibility_raw=a_raw)
        strategies.append({
            "sealedProductId": str(product["sealed_product_id"]), "setId": str(product["set_id"]),
            "productFamily": product["product_family"], "productName": product.get("product_name"),
            "productMarketPrice": price, "priceAsOf": product.get("price_as_of"),
            "collectorAppealScore": product.get("collector_appeal_score"),
            "sourceCalculationRunId": str(product["calculation_run_id"]), "budgetType": budget_type,
            "chaseAccessibilityRaw": a_raw, **allocation, **scored})
    ranked = rank_budget_cohort_v2(strategies)
    unrankable = [s for s in strategies if not (s.get("overallRipV14Rankable") is True
                                               and s.get("overallRipV14Score") is not None)]
    if budget_type == BUDGET_TYPE_FULL_MARKET and full_market is not None:
        for row in ranked:
            row.update(fullMarketAnchor=full_market["budget"], maxEligibleSkuPrice=full_market["maxEligibleSkuPrice"],
                       fullMarketRoundingIncrement=full_market["roundingIncrement"],
                       fullMarketRoundingRule=full_market["roundingRule"],
                       fullMarketRoundingRuleVersion=full_market["roundingRuleVersion"])
    return {"targetBudget": target_budget, "budgetType": budget_type, "eligibleCount": len(strategies),
            "rankedCount": len(ranked), "excludedCount": len(excluded), "excluded": excluded,
            "unrankableCount": len(unrankable),
            "unrankable": [{"sealedProductId": s["sealedProductId"],
                            "reason": (s.get("overallRipV14Payload") or {}).get("statusReason") or s.get("overallRipV14Status")}
                           for s in unrankable],
            "familyCoverage": dict(sorted(Counter(r["productFamily"] for r in ranked).items())), "rows": ranked}


def build_ranking_v2_for_cohort(
    client: Any, products: Sequence[Mapping[str, Any]], *, method_version: Optional[str],
    accessibility_resolver_fn: Optional[Callable[[Any, Mapping[str, str]], Dict[str, Any]]] = None,
    artifact_loader_fn: Optional[Callable[[Any, Any], Any]] = None,
    base_builder_fn: Optional[Callable[[Any, int, str], Any]] = None,
    require_v5: bool = True,
) -> Dict[str, Any]:
    """Explicit V2 build over the cohort. Fails closed before any scoring if V5 authority is missing."""
    require_explicit_v2_request(method_version)
    if require_v5:
        require_v5_source_rows(products)
    if accessibility_resolver_fn is None:
        from backend.db.services.budget_chase_accessibility_authority import resolve_budget_cohort_accessibility as accessibility_resolver_fn  # type: ignore[misc]
    if artifact_loader_fn is None:
        from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact as artifact_loader_fn  # type: ignore[misc]
    if base_builder_fn is None:
        from backend.scripts.build_budget_normalized_product_rankings import build_stage1_distributions_cached as base_builder_fn  # type: ignore[misc]
    from backend.db.services.budget_chase_accessibility_authority import accessibility_raw_for_product

    run_id_by_set_id = {str(p["set_id"]): str(p["calculation_run_id"]) for p in products}
    resolution = accessibility_resolver_fn(client, run_id_by_set_id)  # ONE batch read for the whole cohort
    full_market = resolve_full_market_budget([float(p["product_market_cost"]) for p in products])
    run_ids = sorted({str(p["calculation_run_id"]) for p in products})
    artifacts = {run_id: artifact_loader_fn(client, run_id) for run_id in run_ids}  # once per run
    base_cache: Dict[tuple, Any] = {}

    def base_values_for(product: Mapping[str, Any]):
        run_id = str(product["calculation_run_id"])
        count = int(product.get("random_pack_count") or product["pack_count"])
        if (run_id, count) not in base_cache:
            base_cache[(run_id, count)] = base_builder_fn(artifacts[run_id], count, run_id)
        return base_cache[(run_id, count)]

    budgets = [(float(b), BUDGET_TYPE_STANDARD) for b in CANONICAL_BUDGET_BANDS]
    budgets.append((float(full_market["budget"]), BUDGET_TYPE_FULL_MARKET))
    results = {"%s:%g" % (bt, tb): rank_one_budget_v2(
        engine_products=products, base_values_for=base_values_for, target_budget=tb, budget_type=bt,
        accessibility_raw_for=lambda set_id: accessibility_raw_for_product(resolution, set_id),
        full_market=full_market if bt == BUDGET_TYPE_FULL_MARKET else None) for tb, bt in budgets}
    return {"rankingMethodVersion": BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2, "fullMarket": full_market,
            "productCount": len(products), "budgets": results,
            "batchAccessibilityReadCount": resolution.get("batchReadCount"),
            "artifactLoads": len(artifacts), "builtAt": datetime.now(timezone.utc).isoformat()}


def assemble_ranking_v2_publication(
    result: Mapping[str, Any], products: Sequence[Mapping[str, Any]], *, market_date: str, pinned_price_as_of: str,
    cohort_fingerprint: str, diagnostics: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Snapshot + rows for the versioned RPC, via the payload builders proven against real Postgres."""
    fm = result["fullMarket"]
    by_id = {str(p["sealed_product_id"]): p for p in products}
    rows: List[Dict[str, Any]] = []
    for key, block in result["budgets"].items():
        ctx = {}
        for entry in block["rows"]:
            p = by_id[entry["sealedProductId"]]
            is_fm = block["budgetType"] == BUDGET_TYPE_FULL_MARKET
            ctx[entry["sealedProductId"]] = {
                "set_id": str(p["set_id"]), "product_family": p["product_family"],
                "product_market_price": float(p["product_market_cost"]), "price_as_of": pinned_price_as_of,
                "collector_appeal_score": p.get("collector_appeal_score"),
                "chase_accessibility_raw": entry["chaseAccessibilityRaw"],
                "source_calculation_run_id": str(p["calculation_run_id"]),
                "full_market_anchor": fm["budget"] if is_fm else None,
                "max_eligible_sku_price": fm["maxEligibleSkuPrice"] if is_fm else None,
                "full_market_rounding_rule": fm["roundingRule"] if is_fm else None,
                "full_market_rounding_increment": fm["roundingIncrement"] if is_fm else None,
                "full_market_rounding_rule_version": fm["roundingRuleVersion"] if is_fm else None}
        rows += build_ranking_v2_rows(block["rows"], ctx, budget_type=block["budgetType"])
    fm_count = result["budgets"]["%s:%g" % (BUDGET_TYPE_FULL_MARKET, fm["budget"])]["rankedCount"]
    snapshot = build_ranking_v2_snapshot(
        market_date=market_date, built_at=result["builtAt"], pinned_price_as_of=pinned_price_as_of,
        eligible_cohort_count=fm_count, cohort_fingerprint=cohort_fingerprint, full_market_budget=fm["budget"],
        max_eligible_sku_price=fm["maxEligibleSkuPrice"], full_market_rounding_increment=fm["roundingIncrement"],
        full_market_rounding_rule_version=fm["roundingRuleVersion"], diagnostics_json=diagnostics)
    return {"snapshot": snapshot, "rows": rows}


def publish_ranking_v2(client: Any, publication: Mapping[str, Any]) -> Any:
    """Commit through the versioned RPC. The dispatcher routes on ``ranking_method_version``; there is no
    other write path and this function never touches the V1 pointer or any canonical selector."""
    if publication["snapshot"].get("ranking_method_version") != BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2:
        raise RankingV2NotReady("snapshot_is_not_ranking_v2")
    return client.rpc("publish_budget_product_ranking_snapshot",
                      {"p_snapshot": publication["snapshot"], "p_rows": publication["rows"]}).execute()
