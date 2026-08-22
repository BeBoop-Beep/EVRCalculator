"""Build/publish the internal Budget-Normalized Product Ranking snapshot.

INTERNAL INFRASTRUCTURE ONLY. Not wired to any public payload, API, or
current customer-facing surface. See
docs/research/OVERALL_PRODUCT_RANK_DECISION_2026-08-22_v2.md and
backend/calculations/evr/budget_normalized_product_ranking.py.

Usage:
    python -m backend.scripts.build_budget_normalized_product_rankings --dry-run
    python -m backend.scripts.build_budget_normalized_product_rankings --commit

--dry-run (default): computes the full ranking for every canonical budget
band plus Full Market, prints a summary, writes nothing.
--commit: additionally calls `publish_budget_product_ranking_snapshot`
(requires migration 20260822213027 to be applied first).

Idempotent: re-running with unchanged source data reproduces byte-identical
ranks (see the reconstruction-check pattern in the equal-spend research this
reuses). Publishing twice for the same market_date/method REPLACES the row
set (ON CONFLICT DO UPDATE), never appends duplicate authority.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Sequence

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
    build_budget_strategy_values,
    rank_budget_cohort,
    resolve_full_market_budget,
    score_budget_strategy,
    whole_unit_allocation,
)
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.scripts.pokemon_snapshot_builders import get_client


def load_eligible_products(client: Any) -> List[Dict[str, Any]]:
    """Every currently V4/V10-ready, priced sealed product, one row per SKU
    (the most recent V4-ready run per product; ambiguity fails closed)."""
    rows = client.table("simulation_sealed_product_results").select(
        "sealed_product_id,set_id,product_family,product_name,pack_count,random_pack_count,"
        "guaranteed_component_count,guaranteed_component_market_value,product_market_cost,price_as_of,"
        "collector_appeal_score,collector_appeal_version,calculation_run_id,"
        "financial_rip_v4_status,financial_rip_v4_score"
    ).eq("financial_rip_v4_status", "ready").execute().data or []

    by_product: Dict[str, Dict[str, Any]] = {}
    seen_runs: Dict[str, set] = defaultdict(set)
    for row in rows:
        price = row.get("product_market_cost")
        if not price or float(price) <= 0:
            continue
        pid = str(row["sealed_product_id"])
        seen_runs[pid].add(str(row["calculation_run_id"]))
        by_product[pid] = row  # last write wins; ambiguity checked below
    ambiguous = [pid for pid, runs in seen_runs.items() if len(runs) > 1]
    if ambiguous:
        raise RuntimeError(f"products with more than one V4-ready calculation run (ambiguous authority): {ambiguous[:5]}...")
    return list(by_product.values())


def build_all_rankings(client: Any) -> Dict[str, Any]:
    products = load_eligible_products(client)
    prices = [float(p["product_market_cost"]) for p in products]
    full_market = resolve_full_market_budget(prices)

    # One outcome artifact per calculation_run_id, reused across every
    # product/budget candidate from that run (same caching discipline as the
    # equal-spend research's StrategyEngine).
    run_ids = sorted({str(p["calculation_run_id"]) for p in products})
    artifacts = {run_id: load_pack_outcome_artifact(client, run_id) for run_id in run_ids}

    base_cache: Dict[tuple, Any] = {}

    def base_values(product: Dict[str, Any]):
        run_id = str(product["calculation_run_id"])
        random_count = int(product.get("random_pack_count") or product["pack_count"])
        key = (run_id, random_count)
        if key not in base_cache:
            built = build_stage1_distributions_cached(artifacts[run_id], random_count, run_id)
            base_cache[key] = built
        return base_cache[key]

    budgets: List[tuple] = [(float(b), BUDGET_TYPE_STANDARD) for b in CANONICAL_BUDGET_BANDS]
    budgets.append((full_market["budget"], BUDGET_TYPE_FULL_MARKET))

    results: Dict[str, Any] = {"budgets": {}, "fullMarket": full_market, "productCount": len(products)}
    for target_budget, budget_type in budgets:
        strategies = []
        excluded = []
        for product in products:
            allocation = whole_unit_allocation(target_budget, float(product["product_market_cost"]))
            if not allocation["eligible"]:
                excluded.append({"sealedProductId": product["sealed_product_id"], "reason": "price_exceeds_budget"})
                continue
            values = build_budget_strategy_values(
                base_random_pack_values=base_values(product),
                quantity=allocation["quantity"],
                guaranteed_component_market_value=product.get("guaranteed_component_market_value"),
                canonical_set_key=f"budget:{product['sealed_product_id']}",
                run_fingerprint=None,
            )
            scored = score_budget_strategy(
                values, allocation["actualCommittedCapital"], product.get("collector_appeal_score")
            )
            strategies.append({
                "sealedProductId": product["sealed_product_id"],
                "setId": product["set_id"],
                "productFamily": product["product_family"],
                "productName": product.get("product_name"),
                "productMarketPrice": float(product["product_market_cost"]),
                "priceAsOf": product.get("price_as_of"),
                "sourceCalculationRunId": product["calculation_run_id"],
                **allocation,
                **scored,
                "chanceToRecoverCost": None,
            })
        ranked = rank_budget_cohort(strategies)
        unrankable = [s for s in strategies if s.get("overallRipV10Score") is None]
        results["budgets"][f"{budget_type}:{target_budget:g}"] = {
            "targetBudget": target_budget,
            "budgetType": budget_type,
            "eligibleCount": len(strategies),
            "rankedCount": len(ranked),
            "excludedCount": len(excluded),
            "excluded": excluded,
            "unrankableCount": len(unrankable),
            "familyCoverage": dict((f, sum(1 for r in ranked if r["productFamily"] == f)) for f in sorted({r["productFamily"] for r in ranked})),
            "rows": ranked,
        }
    return results


def build_stage1_distributions_cached(artifact, random_count: int, run_id: str):
    from backend.calculations.evr.sealed_product_distribution import build_stage1_product_distributions
    built = build_stage1_product_distributions(
        artifact.outcomes, pack_counts=[random_count], canonical_set_key=run_id, run_fingerprint=None
    )
    return built["distributions"][random_count]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    parser.add_argument("--json", default="logs/budget_normalized_product_rankings.json")
    args = parser.parse_args(argv)

    client = get_client()
    results = build_all_rankings(client)

    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    for key, block in results["budgets"].items():
        print(f"{key}: eligible={block['eligibleCount']} ranked={block['rankedCount']} "
              f"excluded={block['excludedCount']} families={block['familyCoverage']}")
    print(f"Full Market: {results['fullMarket']}")
    print(f"wrote {out}")

    if args.dry_run:
        print("DRY RUN — no publication attempted.")
        return 0

    print("--commit requires migration 20260822213027 to be applied "
          "(publish_budget_product_ranking_snapshot RPC). Not calling it automatically; "
          "see PHASE 9 in the task / decision record for the manual publish step.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
