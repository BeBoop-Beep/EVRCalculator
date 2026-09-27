"""Read-only, lineage-pinned Financial V4/V5 current and temporal replay."""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import kendalltau, pearsonr, spearmanr

from backend.calculations.evr.budget_normalized_product_ranking import build_budget_strategy_values
from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.calculations.evr.financial_rip_v4 import build_financial_rip_v4
from backend.calculations.evr.financial_rip_v4_config import FINANCIAL_RIP_V4_VERSION
from backend.calculations.evr.financial_rip_v5_candidate import CANDIDATE_ID, score_financial_rip_v5_candidate
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.scripts.build_budget_normalized_product_rankings import build_stage1_distributions_cached, cohort_fingerprint
from backend.scripts.pokemon_snapshot_builders import get_client
from backend.scripts.research_best_open_price_bucket0 import _fetch_source_rows, _load_exact_source_products

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/research/financial_rip_v5_real_artifact_validation.json"
UNCHANGED = ("true_win_frequency", "typical_retention", "realistic_upside",
             "jackpot_upside", "base_economic_efficiency")


def corr(rows, a, b):
    x, y = [float(r[a]) for r in rows], [float(r[b]) for r in rows]
    return {"pearson": float(pearsonr(x, y).statistic) if len(x) > 2 else None,
            "spearman": float(spearmanr(x, y).statistic) if len(x) > 2 else None}


def rank(rows, score_key):
    ordered = sorted(rows, key=lambda r: (-float(r[score_key]), str(r["sealedProductId"])))
    return {r["sealedProductId"]: i for i, r in enumerate(ordered, 1)}


def summarize(rows):
    v4, v5 = rank(rows, "v4Score"), rank(rows, "v5Score")
    movements = np.array([abs(v5[r["sealedProductId"]] - v4[r["sealedProductId"]]) for r in rows])
    deltas = np.array([r["scoreDelta"] for r in rows])
    return {
        "count": len(rows), "setCount": len({r["setId"] for r in rows}),
        "scoreCorrelation": corr(rows, "v4Score", "v5Score"),
        "rankSpearman": float(spearmanr(list(v4.values()), [v5[k] for k in v4]).statistic),
        "rankKendall": float(kendalltau(list(v4.values()), [v5[k] for k in v4]).statistic),
        "rankMovement": {"mean": float(movements.mean()), "median": float(np.median(movements)),
                         "p90": float(np.percentile(movements, 90)), "max": int(movements.max()),
                         "unchanged": int(np.count_nonzero(movements == 0)),
                         "oneToTwo": int(np.count_nonzero((movements >= 1) & (movements <= 2))),
                         "threeToFive": int(np.count_nonzero((movements >= 3) & (movements <= 5))),
                         "aboveFive": int(np.count_nonzero(movements > 5))},
        "delta": {"mean": float(deltas.mean()), "median": float(np.median(deltas)),
                  "p10": float(np.percentile(deltas, 10)), "p90": float(np.percentile(deltas, 90)),
                  "maxAbsolute": float(np.max(np.abs(deltas)))},
        "topOverlap": {str(k): len(set(sorted(v4, key=v4.get)[:k]) & set(sorted(v5, key=v5.get)[:k]))
                       for k in (5, 10, 20)},
        "srTypicalCorrelation": corr(rows, "shortfallResilience", "typicalRetentionScore"),
    }


def replay(client, snapshot, artifact_cache, base_cache):
    snapshot_id = str(snapshot["id"])
    all_rows = _fetch_source_rows(client, snapshot_id)
    budget = float(snapshot["full_market_budget"])
    source_rows = [r for r in all_rows if r["budget_type"] == "full_market" and float(r["target_budget"]) == budget]
    if len(source_rows) != int(snapshot["eligible_cohort_count"]):
        raise RuntimeError(f"{snapshot_id}: cohort count mismatch")
    products = _load_exact_source_products(client, source_rows, str(snapshot["pinned_price_as_of"]))
    if cohort_fingerprint(products, str(snapshot["pinned_price_as_of"])) != snapshot["cohort_fingerprint"]:
        raise RuntimeError(f"{snapshot_id}: cohort fingerprint mismatch")
    product_by_id = {str(p["sealed_product_id"]): p for p in products}
    out = []
    for i, source in enumerate(source_rows, 1):
        pid = str(source["sealed_product_id"])
        product = product_by_id[pid]
        run = str(source["source_calculation_run_id"])
        if run != str(product["calculation_run_id"]):
            raise RuntimeError(f"{pid}: source run mismatch")
        if run not in artifact_cache:
            last_error = None
            for attempt in range(3):
                try:
                    artifact_cache[run] = load_pack_outcome_artifact(client, run)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    time.sleep(attempt + 1)
            if last_error:
                raise last_error
        artifact = artifact_cache[run]
        random_count = int(product.get("random_pack_count") or product["pack_count"])
        base_key = (run, random_count)
        if base_key not in base_cache:
            base_cache[base_key] = build_stage1_distributions_cached(artifact, random_count, run)
        quantity = int(source["quantity"])
        values = build_budget_strategy_values(
            base_random_pack_values=base_cache[base_key], quantity=quantity,
            guaranteed_component_market_value=product.get("guaranteed_component_market_value"),
            canonical_set_key=f"budget:{pid}", run_fingerprint=None,
        )
        prepared = PreparedFinancialRipDistribution.prepare(values)
        cost = float(source["actual_committed_capital"])
        v4 = build_financial_rip_v4(prepared, cost)
        v5 = score_financial_rip_v5_candidate(prepared, cost)
        if v4["status"] != "ready" or v5["status"] != "ready":
            raise RuntimeError(f"{pid}: score unavailable")
        for key in UNCHANGED:
            if v4["components"][key] != v5["components"][key]:
                raise RuntimeError(f"{pid}: component mismatch {key}")
        if not math.isclose(float(v4["score"]), float(source["financial_rip_v4_score"]), abs_tol=.0002):
            raise RuntimeError(f"{pid}: V4 stored score mismatch {v4['score']} vs {source['financial_rip_v4_score']}")
        components = {k: {"v4Score": float(v4["components"][k]["score"]),
                          "v5Score": float(v5["components"][k]["score"])} for k in UNCHANGED}
        components["loss_resilience"] = {"v4Score": float(v4["components"]["loss_resilience"]["score"])}
        components["shortfall_resilience"] = {"v5Score": float(v5["components"]["shortfall_resilience"]["score"])}
        out.append({
            "sealedProductId": pid, "productName": product.get("product_name"),
            "setId": str(source["set_id"]), "productFamily": source["product_family"],
            "sourceRunId": run, "artifactSha256": artifact.metadata["raw_sha256"],
            "artifactOutcomeCount": artifact.metadata["outcome_count"],
            "marketDate": snapshot["market_date"], "priceAsOf": product["price_as_of"],
            "price": float(source["product_market_price"]), "budget": budget,
            "quantity": quantity, "cost": cost, "unusedCapital": float(source["unused_capital"]),
            "randomPackCount": random_count,
            "guaranteedComponentValue": float(product.get("guaranteed_component_market_value") or 0),
            "expectedValue": float(prepared.mean_base), "medianValue": float(prepared.median_base),
            "p95Value": float(prepared.p95_base),
            "pWin": float(v4["components"]["true_win_frequency"]["raw"]["trueWinProbability"]),
            "typicalRetentionRaw": v4["components"]["typical_retention"]["raw"],
            "baseEconomicEfficiencyRaw": v4["components"]["base_economic_efficiency"]["raw"],
            "jackpotRaw": v4["components"]["jackpot_upside"]["raw"],
            "realisticUpsideRaw": v4["components"]["realistic_upside"]["raw"],
            "lossResilienceRaw": v4["components"]["loss_resilience"]["raw"],
            "shortfallResilienceRaw": v5["components"]["shortfall_resilience"]["raw"],
            "components": components, "v4Score": float(v4["score"]), "v5Score": float(v5["score"]),
            "scoreDelta": round(float(v5["score"]) - float(v4["score"]), 4),
            "componentDelta": round(float(v5["components"]["shortfall_resilience"]["score"])
                                    - float(v4["components"]["loss_resilience"]["score"]), 4),
            "shortfallResilience": float(v5["components"]["shortfall_resilience"]["score"]),
            "typicalRetentionScore": float(v4["components"]["typical_retention"]["score"]),
            "trueWinFrequencyScore": float(v4["components"]["true_win_frequency"]["score"]),
            "baseEconomicEfficiencyScore": float(v4["components"]["base_economic_efficiency"]["score"]),
            "lossResilienceScore": float(v4["components"]["loss_resilience"]["score"]),
            "storedV4Score": float(source["financial_rip_v4_score"]),
            "storedFinancialRank": int(source["financial_only_rank"]),
        })
        if i % 25 == 0:
            print(f"{snapshot['market_date']}: {i}/{len(source_rows)}", flush=True)
    r4, r5 = rank(out, "v4Score"), rank(out, "v5Score")
    for row in out:
        pid = row["sealedProductId"]
        row["v4Rank"] = r4[pid]
        row["v5Rank"] = r5[pid]
        row["rankMovement"] = r4[pid] - r5[pid]
    return {"snapshot": {k: snapshot[k] for k in ("id", "market_date", "pinned_price_as_of",
              "full_market_budget", "eligible_cohort_count", "cohort_fingerprint",
              "ranking_method_version", "financial_rip_version", "overall_rip_version")},
            "summary": summarize(out), "rows": out}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=OUT)
    args = p.parse_args()
    client = get_client()
    snapshots = client.table("budget_product_ranking_snapshots").select("*").eq("publication_status", "published").order("created_at", desc=True).execute().data
    if not snapshots:
        raise RuntimeError("no published ranking snapshot")
    if snapshots[0]["financial_rip_version"] != FINANCIAL_RIP_V4_VERSION:
        raise RuntimeError("current Financial authority changed")
    result = {"candidateVersion": CANDIDATE_ID, "controlVersion": FINANCIAL_RIP_V4_VERSION,
              "readOnly": True, "states": [], "unavailableStates": []}
    for snapshot in snapshots:
        try:
            # Keep only one market state's outcome vectors in memory at a time.
            state = replay(client, snapshot, {}, {})
            result["states"].append(state)
            print(f"completed {snapshot['market_date']} ({len(state['rows'])} products)", flush=True)
        except Exception as exc:
            result["unavailableStates"].append({"snapshotId": snapshot["id"], "marketDate": snapshot["market_date"],
                                                "reason": str(exc)})
            print(f"unavailable {snapshot['market_date']}: {exc}", flush=True)
            if snapshot["id"] == snapshots[0]["id"]:
                raise
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
