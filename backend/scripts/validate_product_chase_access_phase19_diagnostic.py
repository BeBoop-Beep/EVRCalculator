"""Phase 19 DIAGNOSTIC (NON-AUTHORITATIVE) - O_budget quantity-dominance check.

Phase 19's primary run (``validate_product_chase_access_phase19.py``) found
that the FULLY authority-coherent path returns 0/22 sets ready in current
production: ``simulation_card_variant_pull_rates`` has zero rows for the
sealed-product financial pipeline's CURRENT pinned calculation_run_id, for
every set. This is confirmed to be a pre-existing condition, not something
this session introduced - the exact same ``resolve_budget_cohort_accessibility``
call the ALREADY-CANONICAL V12 budget ranking uses reports 0/22 ready against
the same live cohort.

This script exists ONLY to still answer Stage XII's quantity-dominance
research question honestly, since the fully-coherent path cannot. It
DELIBERATELY RELAXES the run-coherence requirement - for each set it reads
the MOST RECENT pull-rate run (``order by created_at desc limit 1``, exactly
`build_product_chase_opportunity_stage12.py`'s own research pattern) instead
of requiring it to equal the current financial cohort's run - and pairs that
Accessibility/HC universe with the CURRENT product price and quantity
allocation. This is NOT the production authority contract and MUST NOT be
read as "O_budget in production" - it mixes two runs precisely the way
Phase 11 forbids for a real answer. It is read-only, non-authoritative,
diagnostic-only output.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence

from backend.calculations.evr.budget_normalized_product_ranking import whole_unit_allocation
from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.budget_product_ranking_authority import load_pinned_cohort
from backend.db.services.chase_accessibility_service import load_drawable_variants
from backend.desirability.chase_accessibility import compute_chase_accessibility
from backend.desirability.product_chase_access import (
    compute_ece,
    compute_o_budget,
    effective_pack_cost,
    effective_random_packs,
)
from backend.scripts.validate_product_chase_access_phase19 import BUDGETS, spearman


def latest_run_for_set(client: Any, set_id: str) -> Optional[str]:
    rows = (client.table("simulation_card_variant_pull_rates")
            .select("calculation_run_id,created_at")
            .eq("set_id", set_id).order("created_at", desc=True).limit(1).execute().data or [])
    return rows[0]["calculation_run_id"] if rows else None


def main() -> int:
    client = create_service_role_client()
    cohort, authority = load_pinned_cohort(client, price_as_of="2026-08-26")
    print("== Phase 19 DIAGNOSTIC (non-authoritative, relaxed run-coherence) ==")
    print("cohort products:", len(cohort), "sets:", len({r["set_id"] for r in cohort}))

    set_ids = sorted({r["set_id"] for r in cohort})
    latest_run_by_set: Dict[str, Optional[str]] = {sid: latest_run_for_set(client, sid) for sid in set_ids}
    variants_by_set: Dict[str, List[Dict[str, Any]]] = {}
    a_raw_by_set: Dict[str, Optional[float]] = {}
    for sid, run_id in latest_run_by_set.items():
        if not run_id:
            variants_by_set[sid] = []
            a_raw_by_set[sid] = None
            continue
        variants = load_drawable_variants(client, calculation_run_id=run_id)
        variants_by_set[sid] = variants
        result = compute_chase_accessibility(variants=variants, has_pull_model=bool(variants),
                                             set_id=sid, calculation_run_id=run_id)
        a_raw_by_set[sid] = result.get("accessibility")

    ready_sets = sum(1 for v in a_raw_by_set.values() if v is not None)
    print(f"sets with a usable (relaxed, non-authoritative) A_raw: {ready_sets}/{len(set_ids)}")

    v12_raw = client.table("simulation_sealed_product_results").select(
        "sealed_product_id,overall_rip_v12_score").execute().data or []
    v12_by_product = {str(r["sealed_product_id"]): r.get("overall_rip_v12_score") for r in v12_raw}

    summary_rows = []
    for budget in BUDGETS:
        rows = []
        for row in cohort:
            sid = row["set_id"]
            price = row.get("product_market_cost")
            pack_count = row.get("random_pack_count") or row.get("pack_count")
            a_raw = a_raw_by_set.get(sid)
            variants = variants_by_set.get(sid) or []
            if not price or float(price) <= 0 or not variants:
                continue
            allocation = whole_unit_allocation(target_budget=budget, product_market_price=float(price))
            if not allocation["eligible"]:
                continue
            n = effective_random_packs(quantity=allocation["quantity"], random_pack_count=pack_count)
            o_result = compute_o_budget(variants=variants, effective_packs=n,
                                        set_id=sid, calculation_run_id=latest_run_by_set.get(sid))
            if o_result.get("oBudget") is None:
                continue
            pack_cost = effective_pack_cost(product_market_cost=price, random_pack_count=pack_count)
            ece = compute_ece(a_raw=a_raw, effective_pack_cost_value=pack_cost)
            rows.append({
                "sealedProductId": row["sealed_product_id"], "productName": row.get("product_name"),
                "productFamily": row.get("product_family"), "oBudget": o_result["oBudget"],
                "effectivePacks": n, "ece": ece, "price": float(price), "packCost": pack_cost,
                "aRaw": a_raw, "v12": v12_by_product.get(str(row["sealed_product_id"])),
            })
        rows.sort(key=lambda r: -r["oBudget"])
        leader = rows[0] if rows else None
        report = {
            "budget": budget,
            "rankedCount": len(rows),
            "leader": {k: leader[k] for k in ("sealedProductId", "productName", "productFamily", "oBudget")} if leader else None,
            "topFamilies": [r["productFamily"] for r in rows[:5]],
            "spearman": {
                "oBudget_vs_effectivePacks": spearman([r["oBudget"] for r in rows], [r["effectivePacks"] for r in rows]),
                "oBudget_vs_overallRipV12": spearman([r["oBudget"] for r in rows], [r["v12"] for r in rows]),
                "oBudget_vs_ece": spearman([r["oBudget"] for r in rows], [r["ece"] for r in rows]),
                "oBudget_vs_price": spearman([r["oBudget"] for r in rows], [r["price"] for r in rows]),
                "oBudget_vs_effectivePackCost": spearman([r["oBudget"] for r in rows], [r["packCost"] for r in rows]),
                "oBudget_vs_setARaw": spearman([r["oBudget"] for r in rows], [r["aRaw"] for r in rows]),
            },
        }
        summary_rows.append(report)
        print(f"\n--- (DIAGNOSTIC) budget=${budget} ---")
        print(json.dumps(report, indent=2))

    leaders = {r["budget"]: (r["leader"] or {}).get("sealedProductId") for r in summary_rows}
    distinct_leaders = {v for v in leaders.values() if v}
    print("\n== DIAGNOSTIC SUMMARY (non-authoritative) ==")
    print(json.dumps({
        "distinctLeaderCount": len(distinct_leaders),
        "leaderChangesAcrossBudgets": len(distinct_leaders) > 1,
        "leadersByBudget": leaders,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
