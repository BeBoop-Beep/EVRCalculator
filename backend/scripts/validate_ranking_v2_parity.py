"""Read-only Ranking V2 parity against the frozen Sep-14 research oracle.

Replays snapshot 0e65fb6d (Full Market, 138 products) from the exact outcome
artifacts, scores every strategy through the PRODUCTION Ranking V2 path
(``score_budget_strategy_v2``: ``build_financial_rip_v5`` + ``compute_overall_rip_v14``)
and requires per-product equality with the frozen research evidence:

  * docs/research/financial_rip_v5_real_artifact_validation.json (V5 score/rank,
    quantity, cost, P(win))
  * docs/research/financial_rip_v5_best_open_live_validation.json (V5 / Overall
    shadow rank order)

Overall V14 is compared to the research shadow formula applied to the frozen V5
score. No database writes.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from backend.calculations.evr.budget_normalized_product_ranking import (
    build_budget_strategy_values,
    rank_budget_cohort_v2,
    score_budget_strategy_v2,
)
from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.scripts.build_budget_normalized_product_rankings import (
    build_stage1_distributions_cached,
    cohort_fingerprint,
)
from backend.scripts.pokemon_snapshot_builders import get_client
from backend.scripts.research_best_open_price_bucket0 import _fetch_source_rows, _load_exact_source_products
from backend.scripts.research_financial_rip_v5_best_open import overall_shadow

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_ID = "0e65fb6d-ff33-4331-99d5-d6a214ecc712"
FINGERPRINT = "e18fb00cd41f1646579b082164c80b0da3db2e1831dec9428c6fd4d82ac689ce"
OUT = ROOT / "docs/research/financial_rip_v5_ranking_v2_parity.json"


def replay_ranking_v2(client) -> dict:
    """Replay the frozen Sep-14 cohort through the production Ranking V2 path."""
    snapshot = client.table("budget_product_ranking_snapshots").select("*").eq("id", SNAPSHOT_ID).execute().data[0]
    if snapshot["cohort_fingerprint"] != FINGERPRINT:
        raise RuntimeError("frozen cohort fingerprint changed")
    budget = float(snapshot["full_market_budget"])
    rows = [r for r in _fetch_source_rows(client, SNAPSHOT_ID)
            if r["budget_type"] == "full_market" and float(r["target_budget"]) == budget]
    products = _load_exact_source_products(client, rows, str(snapshot["pinned_price_as_of"]))
    if cohort_fingerprint(products, str(snapshot["pinned_price_as_of"])) != FINGERPRINT:
        raise RuntimeError("cohort fingerprint mismatch")
    product_by_id = {str(p["sealed_product_id"]): p for p in products}

    artifacts, bases, strategies = {}, {}, []
    for source in rows:
        pid = str(source["sealed_product_id"])
        product = product_by_id[pid]
        run = str(source["source_calculation_run_id"])
        artifacts.setdefault(run, load_pack_outcome_artifact(client, run))
        random_count = int(product.get("random_pack_count") or product["pack_count"])
        if (run, random_count) not in bases:
            bases[(run, random_count)] = build_stage1_distributions_cached(artifacts[run], random_count, run)
        quantity = int(source["quantity"])
        values = build_budget_strategy_values(
            base_random_pack_values=bases[(run, random_count)], quantity=quantity,
            guaranteed_component_market_value=product.get("guaranteed_component_market_value"),
            canonical_set_key=f"budget:{pid}", run_fingerprint=None)
        cost = float(source["actual_committed_capital"])
        scored = score_budget_strategy_v2(
            values, cost, float(source["collector_appeal_score"]),
            chase_accessibility_raw=float(source["chase_accessibility_raw"]),
            prepared=PreparedFinancialRipDistribution.prepare(values))
        strategies.append({**scored, "sealedProductId": pid, "quantity": quantity,
                           "actualCommittedCapital": cost, "targetBudget": budget,
                           "_source": source})
    ranked = rank_budget_cohort_v2(strategies)
    if len(ranked) != len(rows):
        raise RuntimeError(f"ranked {len(ranked)} of {len(rows)}")

    return {"snapshot": snapshot, "sourceRows": rows, "products": products,
            "productById": product_by_id, "ranked": ranked, "budget": budget}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    prompt2 = json.loads((ROOT / "docs/research/financial_rip_v5_real_artifact_validation.json").read_text("utf-8"))
    oracle_rows = {r["sealedProductId"]: r for r in prompt2["states"][0]["rows"]}
    bo = json.loads((ROOT / "docs/research/financial_rip_v5_best_open_live_validation.json").read_text("utf-8"))
    oracle_fin_order = list(bo["currentRankings"]["financialV5"])
    oracle_overall_order = list(bo["currentRankings"]["overallV5Shadow"])

    client = get_client()
    replay = replay_ranking_v2(client)
    ranked, rows, budget = replay["ranked"], replay["sourceRows"], replay["budget"]
    mismatches = []

    for r in ranked:
        pid, ref = r["sealedProductId"], oracle_rows[r["sealedProductId"]]
        src = r["_source"]
        expect_overall = overall_shadow(ref["v5Score"], float(src["chase_accessibility_raw"]),
                                        float(src["collector_appeal_score"]))
        checks = {
            "financialV5Score": r["financialRipV5Score"] == ref["v5Score"],
            "overallV14Score": r["overallRipV14Score"] == expect_overall,
            "quantity": r["quantity"] == ref["quantity"],
            "committedCapital": math.isclose(r["actualCommittedCapital"], ref["cost"], abs_tol=1e-9),
            "pWin": math.isclose(float(r["chanceToRecoverCapital"]), ref["pWin"], abs_tol=1e-9),
            "financialV5Rank": r["financialOnlyRankV5"] == oracle_fin_order.index(pid) + 1,
            "overallV14Rank": r["budgetRankV14"] == oracle_overall_order.index(pid) + 1,
        }
        bad = [k for k, ok in checks.items() if not ok]
        if bad:
            mismatches.append({"sealedProductId": pid, "failed": bad,
                               "production": {k: r.get(k) for k in ("financialRipV5Score", "overallRipV14Score",
                                                                    "financialOnlyRankV5", "budgetRankV14")},
                               "oracle": {"v5Score": ref["v5Score"], "expectedOverall": expect_overall}})
    report = {"snapshotId": SNAPSHOT_ID, "cohortFingerprint": FINGERPRINT, "products": len(ranked),
              "rankingMethodVersion": "budget_product_ranking_v2", "mismatchCount": len(mismatches),
              "mismatches": mismatches, "perProductEquality": not mismatches,
              "checks": ["financialV5Score", "overallV14Score", "quantity", "committedCapital",
                         "pWin", "financialV5Rank", "overallV14Rank"]}
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("products", "mismatchCount", "perProductEquality")}))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    sys.exit(main())
