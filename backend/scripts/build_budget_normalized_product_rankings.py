"""Build/publish the internal Budget-Constrained Whole-Unit Product Ranking.

INTERNAL INFRASTRUCTURE ONLY. Not wired to any public payload, API, or
current customer-facing surface. See
`docs/research/BUDGET_NORMALIZED_PRODUCT_RANKING_v1.md` and
`backend/calculations/evr/budget_normalized_product_ranking.py`.

METHOD (frozen V1): for a budget ceiling B and unit price P, the strategy is
`floor(B / P)` WHOLE units of one SKU. Leftover cash is recorded and never
scored. This is NOT equal committed capital.

Usage:
    python -m backend.scripts.build_budget_normalized_product_rankings \
        --dry-run --price-as-of 2026-08-21
    python -m backend.scripts.build_budget_normalized_product_rankings \
        --commit --price-as-of 2026-08-21

--dry-run (default-safe): computes every canonical band plus Full Market,
prints a structured summary, writes only a local JSON.
--commit: additionally calls `publish_budget_product_ranking_snapshot`
(requires migration 20260822213027 to be applied first).

Idempotent: re-running with unchanged source data reproduces byte-identical
ranks. Publishing twice for the same market_date/method REPLACES the row set
(ON CONFLICT DO UPDATE), never appends duplicate authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.calculations.evr.budget_normalized_product_ranking import (
    ALLOCATION_METHOD_VERSION,
    BUDGET_COMPARISON_SCOPE_VERSION,
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
    BUDGET_TYPE_FULL_MARKET,
    BUDGET_TYPE_STANDARD,
    CANONICAL_BUDGET_BANDS,
    FULL_MARKET_ROUNDING_RULE_VERSION,
    build_budget_strategy_values,
    rank_budget_cohort,
    resolve_full_market_budget,
    score_budget_strategy,
    whole_unit_allocation,
)
from backend.db.services.budget_product_ranking_authority import (
    assert_expected_model_versions,
    load_pinned_cohort,
)
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.scripts.pokemon_snapshot_builders import get_client

#: Validated financial-only dominance inversion rate at the V1 freeze was
#: 0.044% ($1,350) with a worst observed 0.108% ($1,600) across two cohorts.
#: This is an AUDIT WARNING threshold, not a publish blocker: a handful of
#: inversions is expected because the 4-metric dominance test is not a
#: monotone function of V4's 6 scored components.
FINANCIAL_DOMINANCE_WARN_RATE = 0.01

#: Utilization/rank correlation stayed inside +/-0.10 on both validated
#: cohorts. A materially larger magnitude means budget divisibility has
#: started to drive rank and the method needs re-validation.
UTILIZATION_CORRELATION_WARN = 0.25

#: Families the V1 validation actually covered. A new family appearing is not
#: an error, but it has never been checked for ranking coverage.
VALIDATED_PRODUCT_FAMILIES = frozenset({
    "booster_box", "booster_bundle", "elite_trainer_box", "enhanced_booster_box",
    "half_booster_box", "loose_booster_pack", "pokemon_center_elite_trainer_box",
    "sleeved_booster_pack",
})


def build_stage1_distributions_cached(artifact, random_count: int, run_id: str):
    from backend.calculations.evr.sealed_product_distribution import build_stage1_product_distributions
    built = build_stage1_product_distributions(
        artifact.outcomes, pack_counts=[random_count], canonical_set_key=run_id, run_fingerprint=None
    )
    return built["distributions"][random_count]


def _spearman(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    import numpy as np
    if len(x) < 3:
        return None

    def ranks(values):
        a = np.asarray(values, float)
        order = np.argsort(a, kind="mergesort")
        out = np.empty(len(a), float)
        i = 0
        while i < len(a):
            j = i
            while j + 1 < len(a) and a[order[j + 1]] == a[order[i]]:
                j += 1
            out[order[i:j + 1]] = 0.5 * (i + j) + 1.0
            i = j + 1
        return out

    rx, ry = ranks(x), ranks(y)
    if np.std(rx) == 0 or np.std(ry) == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def cohort_fingerprint(products: Sequence[Dict[str, Any]], pinned_price_as_of: str) -> str:
    """Stable identity of the exact input cohort, so a publication can be
    proven to have come from one specific market state."""
    parts = sorted(
        "%s:%s:%s" % (p["sealed_product_id"], p["calculation_run_id"], p["product_market_cost"])
        for p in products
    )
    digest = hashlib.sha256(("|".join([str(pinned_price_as_of)] + parts)).encode("utf-8"))
    return digest.hexdigest()


def rank_one_budget(
    *,
    engine_products: Sequence[Dict[str, Any]],
    base_values_for,
    target_budget: float,
    budget_type: str,
    full_market: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Rank one budget ceiling over the whole cohort.

    Accepts ANY positive budget — the canonical bands are just the values the
    builder happens to precompute. A future "user enters $X" flow calls this
    directly with no new scoring architecture.
    """
    if target_budget <= 0:
        raise ValueError("target_budget must be positive")

    strategies: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []

    for product in engine_products:
        price = float(product["product_market_cost"])
        allocation = whole_unit_allocation(target_budget, price)
        if not allocation["eligible"]:
            excluded.append({
                "sealedProductId": str(product["sealed_product_id"]),
                "productName": product.get("product_name"),
                "productFamily": product.get("product_family"),
                "unitPrice": price,
                "reason": "price_exceeds_budget",
            })
            continue

        values = build_budget_strategy_values(
            base_random_pack_values=base_values_for(product),
            quantity=allocation["quantity"],
            guaranteed_component_market_value=product.get("guaranteed_component_market_value"),
            canonical_set_key="budget:%s" % product["sealed_product_id"],
            run_fingerprint=None,
        )
        scored = score_budget_strategy(
            values, allocation["actualCommittedCapital"], product.get("collector_appeal_score")
        )
        strategies.append({
            "sealedProductId": str(product["sealed_product_id"]),
            "setId": str(product["set_id"]),
            "productFamily": product["product_family"],
            "productName": product.get("product_name"),
            "productMarketPrice": price,
            "priceAsOf": product.get("price_as_of"),
            "collectorAppealScore": product.get("collector_appeal_score"),
            "sourceCalculationRunId": str(product["calculation_run_id"]),
            "budgetType": budget_type,
            **allocation,
            **scored,
        })

    ranked = rank_budget_cohort(strategies)
    unrankable = [s for s in strategies if s.get("overallRipV10Score") is None]

    if budget_type == BUDGET_TYPE_FULL_MARKET and full_market is not None:
        for row in ranked:
            row["fullMarketAnchor"] = full_market["budget"]
            row["maxEligibleSkuPrice"] = full_market["maxEligibleSkuPrice"]
            row["fullMarketRoundingIncrement"] = full_market["roundingIncrement"]
            row["fullMarketRoundingRule"] = full_market["roundingRule"]
            row["fullMarketRoundingRuleVersion"] = full_market["roundingRuleVersion"]

    utilizations = [r["capitalUtilization"] for r in ranked]
    return {
        "targetBudget": target_budget,
        "budgetType": budget_type,
        "eligibleCount": len(strategies),
        "rankedCount": len(ranked),
        "excludedCount": len(excluded),
        "excluded": excluded,
        "unrankableCount": len(unrankable),
        "familyCoverage": dict(sorted(Counter(r["productFamily"] for r in ranked).items())),
        "medianUtilization": (sorted(utilizations)[len(utilizations) // 2] if utilizations else None),
        "minimumUtilization": (min(utilizations) if utilizations else None),
        "meanUtilization": (sum(utilizations) / len(utilizations) if utilizations else None),
        "utilizationRankSpearman": _spearman(utilizations, [r["budgetRank"] for r in ranked]),
        "rows": ranked,
    }


def build_all_rankings(client: Any, price_as_of: Optional[str] = None) -> Dict[str, Any]:
    timings: Dict[str, Any] = {}
    t0 = time.time()

    products, authority = load_pinned_cohort(client, price_as_of)
    timings["cohortLoadSeconds"] = round(time.time() - t0, 3)

    drift = assert_expected_model_versions(authority)

    prices = [float(p["product_market_cost"]) for p in products]
    full_market = resolve_full_market_budget(prices)

    t_art = time.time()
    run_ids = sorted({str(p["calculation_run_id"]) for p in products})
    artifacts = {run_id: load_pack_outcome_artifact(client, run_id) for run_id in run_ids}
    timings["artifactLoadSeconds"] = round(time.time() - t_art, 3)

    base_cache: Dict[tuple, Any] = {}

    def base_values_for(product: Dict[str, Any]):
        run_id = str(product["calculation_run_id"])
        random_count = int(product.get("random_pack_count") or product["pack_count"])
        key = (run_id, random_count)
        if key not in base_cache:
            base_cache[key] = build_stage1_distributions_cached(artifacts[run_id], random_count, run_id)
        return base_cache[key]

    budgets: List[tuple] = [(float(b), BUDGET_TYPE_STANDARD) for b in CANONICAL_BUDGET_BANDS]
    budgets.append((float(full_market["budget"]), BUDGET_TYPE_FULL_MARKET))

    results: Dict[str, Dict[str, Any]] = {}
    per_budget_seconds: Dict[str, float] = {}
    for target_budget, budget_type in budgets:
        t_b = time.time()
        block = rank_one_budget(
            engine_products=products,
            base_values_for=base_values_for,
            target_budget=target_budget,
            budget_type=budget_type,
            full_market=full_market if budget_type == BUDGET_TYPE_FULL_MARKET else None,
        )
        key = "%s:%g" % (budget_type, target_budget)
        results[key] = block
        per_budget_seconds[key] = round(time.time() - t_b, 3)

    timings["perBudgetSeconds"] = per_budget_seconds
    timings["totalBuildSeconds"] = round(time.time() - t0, 3)

    health = _health_checks(results, products, full_market, authority, drift)

    market_date = max(str(p.get("price_as_of")) for p in products)
    return {
        "authority": authority,
        "modelDriftWarnings": drift,
        "fullMarket": full_market,
        "productCount": len(products),
        "marketDate": market_date,
        "cohortFingerprint": cohort_fingerprint(products, authority["pinnedPriceAsOf"]),
        "rankingMethodVersion": BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
        "allocationMethodVersion": ALLOCATION_METHOD_VERSION,
        "comparisonScopeVersion": BUDGET_COMPARISON_SCOPE_VERSION,
        "fullMarketRoundingRuleVersion": FULL_MARKET_ROUNDING_RULE_VERSION,
        "budgets": results,
        "timings": timings,
        "health": health,
        "builtAt": datetime.now(timezone.utc).isoformat(),
    }


def _health_checks(
    results: Dict[str, Dict[str, Any]],
    products: Sequence[Dict[str, Any]],
    full_market: Dict[str, Any],
    authority: Dict[str, Any],
    drift: Sequence[str],
) -> Dict[str, Any]:
    """Turn the V1 validation findings into repeatable guards."""
    warnings: List[str] = list(drift)

    fm_key = "%s:%g" % (BUDGET_TYPE_FULL_MARKET, full_market["budget"])
    fm = results.get(fm_key)
    full_market_complete = bool(fm and fm["rankedCount"] == len(products))
    if not full_market_complete:
        warnings.append(
            "COVERAGE: Full Market ranked %s of %d eligible SKUs; the anchor must admit the whole cohort"
            % ((fm or {}).get("rankedCount"), len(products))
        )

    observed_families = set(Counter(p["product_family"] for p in products))
    unsupported = sorted(observed_families - VALIDATED_PRODUCT_FAMILIES)
    if unsupported:
        warnings.append(
            "UNSUPPORTED FAMILY: %s appeared in the cohort but was never covered by V1 validation"
            % unsupported
        )

    utilization_flags = []
    for key, block in results.items():
        rho = block.get("utilizationRankSpearman")
        if rho is not None and abs(rho) > UTILIZATION_CORRELATION_WARN:
            utilization_flags.append({"budget": key, "spearman": rho})
            warnings.append(
                "CAPITAL-UTILIZATION ANOMALY: Spearman(utilization, rank) = %.4f at %s exceeds +/-%.2f"
                % (rho, key, UTILIZATION_CORRELATION_WARN)
            )

    return {
        "fullMarketCoverageComplete": full_market_complete,
        "unsupportedFamilies": unsupported,
        "utilizationCorrelationFlags": utilization_flags,
        "utilizationCorrelationWarnThreshold": UTILIZATION_CORRELATION_WARN,
        "financialDominanceWarnRate": FINANCIAL_DOMINANCE_WARN_RATE,
        "modelVersionsExpected": not drift,
        "authorityCoherent": True,
        "pinnedPriceAsOf": authority["pinnedPriceAsOf"],
        "warnings": warnings,
        "healthy": not warnings,
    }


def to_publication_payload(results: Dict[str, Any]) -> tuple:
    """Flatten into the (snapshot, rows) shape the publish RPC expects."""
    authority = results["authority"]
    snapshot = {
        "market_date": results["marketDate"],
        "built_at": results["builtAt"],
        "ranking_method_version": results["rankingMethodVersion"],
        "allocation_method_version": results["allocationMethodVersion"],
        "comparison_scope_version": results["comparisonScopeVersion"],
        "financial_rip_version": authority["financialRipVersion"],
        "overall_rip_version": authority["overallRipVersion"],
        "collector_appeal_version": authority["collectorAppealVersion"],
        "pinned_price_as_of": authority["pinnedPriceAsOf"],
        "eligible_cohort_count": results["productCount"],
        "cohort_fingerprint": results["cohortFingerprint"],
        "full_market_budget": results["fullMarket"]["budget"],
        "max_eligible_sku_price": results["fullMarket"]["maxEligibleSkuPrice"],
        "full_market_rounding_increment": results["fullMarket"]["roundingIncrement"],
        "full_market_rounding_rule_version": results["fullMarketRoundingRuleVersion"],
        "diagnostics_json": {
            "timings": results["timings"],
            "health": results["health"],
            "authority": {k: v for k, v in authority.items() if k != "excludedRows"},
        },
    }

    rows: List[Dict[str, Any]] = []
    for block in results["budgets"].values():
        for row in block["rows"]:
            rows.append({
                "sealed_product_id": row["sealedProductId"],
                "set_id": row["setId"],
                "product_family": row["productFamily"],
                "target_budget": row["targetBudget"],
                "budget_type": row["budgetType"],
                "quantity": row["quantity"],
                "actual_committed_capital": row["actualCommittedCapital"],
                "unused_capital": row["unusedCapital"],
                "unused_capital_percent": row["unusedCapitalPercent"],
                "capital_utilization": row["capitalUtilization"],
                "budget_rank": row["budgetRank"],
                "budget_cohort_size": row["budgetCohortSize"],
                "budget_tier": row["budgetTier"],
                "financial_only_rank": row["financialOnlyRank"],
                "financial_rip_v4_score": row["financialRipV4Score"],
                "overall_rip_v10_score": row["overallRipV10Score"],
                "collector_appeal_score": row["collectorAppealScore"],
                "chance_to_recover_capital": row.get("chanceToRecoverCapital"),
                "product_market_price": row["productMarketPrice"],
                "price_as_of": row.get("priceAsOf"),
                "full_market_anchor": row.get("fullMarketAnchor"),
                "max_eligible_sku_price": row.get("maxEligibleSkuPrice"),
                "full_market_rounding_rule": row.get("fullMarketRoundingRule"),
                "full_market_rounding_increment": row.get("fullMarketRoundingIncrement"),
                "full_market_rounding_rule_version": row.get("fullMarketRoundingRuleVersion"),
                "source_calculation_run_id": row["sourceCalculationRunId"],
            })
    return snapshot, rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    parser.add_argument("--price-as-of", default=None,
                        help="Pin the cohort to one coherent price_as_of. Required whenever "
                             "several complete cohorts exist (the resolver fails closed).")
    parser.add_argument("--json", default="logs/budget_normalized_product_rankings.json")
    args = parser.parse_args(argv)

    client = get_client()
    results = build_all_rankings(client, args.price_as_of)

    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    authority = results["authority"]
    print("=" * 86)
    print("BUDGET-CONSTRAINED WHOLE-UNIT PRODUCT RANKING — %s" % ("COMMIT" if args.commit else "DRY RUN"))
    print("=" * 86)
    print("authority         : price_as_of=%s (%s), %d SKUs, %d runs"
          % (authority["pinnedPriceAsOf"], authority["pinMode"],
             authority["productCount"], len(authority["calculationRunIds"])))
    print("models            : %s" % authority["financialRipVersion"])
    print("                  : %s" % authority["overallRipVersion"])
    print("                  : %s" % authority["collectorAppealVersion"])
    print("method            : %s" % results["rankingMethodVersion"])
    print("allocation        : %s" % results["allocationMethodVersion"])
    print("comparison scope  : %s" % results["comparisonScopeVersion"])
    print("full market       : $%.2f  (max SKU $%.2f, %s)"
          % (results["fullMarket"]["budget"], results["fullMarket"]["maxEligibleSkuPrice"],
             results["fullMarket"]["roundingRule"]))
    print("cohort fingerprint: %s" % results["cohortFingerprint"][:16])
    print("excluded cohorts  : %d rows / %d runs"
          % (authority["excludedRowCount"], authority["excludedRunCount"]))
    print("-" * 86)
    print("%-24s %8s %7s %8s %9s %9s %6s" % ("BUDGET", "ELIGIBLE", "RANKED", "EXCLUDED", "MED-UTIL", "MIN-UTIL", "FAMS"))
    for key, block in results["budgets"].items():
        print("%-24s %8d %7d %8d %9s %9s %6d"
              % (key, block["eligibleCount"], block["rankedCount"], block["excludedCount"],
                 ("%.4f" % block["medianUtilization"]) if block["medianUtilization"] is not None else "-",
                 ("%.4f" % block["minimumUtilization"]) if block["minimumUtilization"] is not None else "-",
                 len(block["familyCoverage"])))
    print("-" * 86)
    total_rows = sum(b["rankedCount"] for b in results["budgets"].values())
    print("ranking rows      : %d" % total_rows)
    print("timings           : cohort %.2fs | artifacts %.2fs | total %.2fs"
          % (results["timings"]["cohortLoadSeconds"], results["timings"]["artifactLoadSeconds"],
             results["timings"]["totalBuildSeconds"]))
    health = results["health"]
    print("health            : %s" % ("HEALTHY" if health["healthy"] else "%d WARNING(S)" % len(health["warnings"])))
    for warning in health["warnings"]:
        print("   ! %s" % warning)
    print("wrote %s" % out)

    if args.dry_run:
        print("DRY RUN — no publication attempted.")
        return 0

    snapshot, rows = to_publication_payload(results)
    print("publishing %d rows under snapshot market_date=%s ..." % (len(rows), snapshot["market_date"]))
    response = client.rpc(
        "publish_budget_product_ranking_snapshot",
        {"p_snapshot": snapshot, "p_rows": rows},
    ).execute()
    print("published snapshot id: %s" % response.data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
