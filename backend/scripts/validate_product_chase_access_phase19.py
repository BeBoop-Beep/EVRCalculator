"""Phase 19 - READ-ONLY production validation for Chase Access at Budget (O_budget).

Runs Product Chase Intelligence at representative budgets against the
current live pinned budget cohort and reports, honestly:

* the leader at each budget and whether the leader changes across budgets;
* family distribution of the top rows;
* Spearman correlation of O_budget against: overall_rip_v12_score (single
  unit, the closest live column - a true V12_budget series does not exist as
  a persisted column, so this is the best live proxy available), ECE,
  product price, effective pack cost, effective_packs, and set A_raw;
* the critical Stage XII follow-up: Spearman(O_budget, effective_packs), to
  check whether O_budget is genuinely quantity-dominated in production data.

NO WRITES. NO MIGRATIONS. Read-only against `simulation_sealed_product_results`
via the existing `load_pinned_cohort` authority and the new
`resolve_product_chase_access` orchestration.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Sequence

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.budget_product_ranking_authority import load_pinned_cohort
from backend.db.services.product_chase_access_authority import resolve_product_chase_access

BUDGETS = (25, 50, 100, 150, 250, 500)


def spearman(xs: Sequence[Optional[float]], ys: Sequence[Optional[float]]) -> Optional[float]:
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    xs2, ys2 = zip(*pairs)
    n = len(xs2)

    def ranks(values):
        order = sorted(range(n), key=lambda i: values[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg_rank
            i = j + 1
        return r

    rx, ry = ranks(list(xs2)), ranks(list(ys2))
    mean_x, mean_y = sum(rx) / n, sum(ry) / n
    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry))
    var_x = sum((a - mean_x) ** 2 for a in rx)
    var_y = sum((b - mean_y) ** 2 for b in ry)
    if var_x <= 0 or var_y <= 0:
        return None
    return cov / (var_x * var_y) ** 0.5


def main() -> int:
    client = create_service_role_client()
    t0 = time.time()
    cohort, authority = load_pinned_cohort(client, price_as_of="2026-08-26")
    load_elapsed = time.time() - t0
    print("== Phase 19: Chase Access at Budget - read-only production validation ==")
    print(json.dumps({
        "cohortProductCount": len(cohort),
        "distinctSetCount": len({r["set_id"] for r in cohort}),
        "pinnedPriceAsOf": authority["pinnedPriceAsOf"],
        "cohortLoadSeconds": round(load_elapsed, 3),
    }, indent=2))

    v12_by_product: Dict[str, Any] = {}
    for row in cohort:
        v12_by_product[str(row.get("sealed_product_id"))] = {
            "overallRipV12Score": row.get("overall_rip_v12_score"),
            "overallRipV12Status": row.get("overall_rip_v12_status"),
        }
    # load_pinned_cohort's own select list doesn't carry v12 columns; re-fetch them.
    v12_raw = client.table("simulation_sealed_product_results").select(
        "sealed_product_id,overall_rip_v12_score,overall_rip_v12_status"
    ).execute().data or []
    for row in v12_raw:
        pid = str(row.get("sealed_product_id"))
        v12_by_product[pid] = {
            "overallRipV12Score": row.get("overall_rip_v12_score"),
            "overallRipV12Status": row.get("overall_rip_v12_status"),
        }

    per_budget_reports: List[Dict[str, Any]] = []
    leaders: Dict[int, Any] = {}
    families_at_top: Dict[int, List[str]] = {}

    query_counts = []
    compute_times = []
    payload_sizes = []

    for budget in BUDGETS:
        t1 = time.time()
        result = resolve_product_chase_access(client, cohort, budget=float(budget))
        elapsed = time.time() - t1
        compute_times.append(elapsed)
        query_counts.append(result["queryCount"])
        payload_sizes.append(len(json.dumps(result)))

        ranked = sorted(
            (p for p in result["products"] if p.get("oBudget") is not None),
            key=lambda p: -p["oBudget"],
        )
        top = ranked[:5]
        leaders[budget] = {
            "sealedProductId": top[0]["sealedProductId"] if top else None,
            "productName": top[0].get("productName") if top else None,
            "productFamily": top[0].get("productFamily") if top else None,
            "oBudget": top[0]["oBudget"] if top else None,
        }
        families_at_top[budget] = [p.get("productFamily") for p in top]

        o_budget = [p.get("oBudget") for p in result["products"]]
        effective_packs = [p.get("effectivePacks") for p in result["products"]]
        ece = [p.get("ece") for p in result["products"]]
        price = [p.get("productMarketCost") for p in result["products"]]
        pack_cost = [p.get("effectivePackCost") for p in result["products"]]
        a_raw = [p.get("aRaw") for p in result["products"]]
        v12_scores = [
            (v12_by_product.get(p["sealedProductId"]) or {}).get("overallRipV12Score")
            for p in result["products"]
        ]

        per_budget_reports.append({
            "budget": budget,
            "rankedProductCount": len(ranked),
            "leader": leaders[budget],
            "topFamilies": families_at_top[budget],
            "spearman": {
                "oBudget_vs_effectivePacks": spearman(o_budget, effective_packs),
                "oBudget_vs_overallRipV12": spearman(o_budget, v12_scores),
                "oBudget_vs_ece": spearman(o_budget, ece),
                "oBudget_vs_price": spearman(o_budget, price),
                "oBudget_vs_effectivePackCost": spearman(o_budget, pack_cost),
                "oBudget_vs_setARaw": spearman(o_budget, a_raw),
            },
            "computeSeconds": round(elapsed, 4),
            "queryCount": result["queryCount"],
            "payloadBytes": len(json.dumps(result)),
        })
        print(f"\n--- budget=${budget} ---")
        print(json.dumps(per_budget_reports[-1], indent=2))

    distinct_leaders = {v["sealedProductId"] for v in leaders.values() if v["sealedProductId"]}
    print("\n== SUMMARY ==")
    print(json.dumps({
        "leaderChangesAcrossBudgets": len(distinct_leaders) > 1,
        "distinctLeaderCount": len(distinct_leaders),
        "leadersByBudget": leaders,
        "avgComputeSeconds": round(sum(compute_times) / len(compute_times), 4),
        "maxPayloadBytes": max(payload_sizes),
        "queryCountsPerBudgetCall": query_counts,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
