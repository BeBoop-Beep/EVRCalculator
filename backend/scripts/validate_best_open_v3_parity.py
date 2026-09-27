"""Read-only Best-Open V3 parity against the frozen Sep-14 Prompt-3 oracle.

Seeds the PRODUCTION V3 engine (``best_open_price_v3``: ``build_financial_rip_v5`` +
``compute_overall_rip_v14`` on the unchanged fused exact-cent search) from the
PRODUCTION Ranking V2 replay, then requires per-product equality with
docs/research/financial_rip_v5_best_open_live_validation.json for both new
authorities (138 x 2 = 276 thresholds): threshold cent, quantity, benchmark
product, threshold V5/V14 scores, P(win), and exactness. No database writes.
Resumable: per-product results are checkpointed under logs/.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import uuid
from functools import lru_cache
from pathlib import Path

from backend.calculations.evr.best_open_price_v3 import (
    BEST_OPEN_PRICE_V3_METHOD_VERSION,
    PreparedV5Candidate,
    build_dual_best_open_v3_search,
    run_dual_best_open_v3,
)
from backend.calculations.evr.budget_normalized_product_ranking import (
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2,
    build_budget_strategy_values,
)
from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.calculations.evr.sealed_product_distribution import (
    build_single_q_parity_distributions,
    single_q_parity_batch_width,
)
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.scripts.build_budget_normalized_product_rankings import build_stage1_distributions_cached
from backend.scripts.pokemon_snapshot_builders import get_client
from backend.scripts.research_best_open_price_bucket0 import _historical_authority
from backend.scripts.validate_ranking_v2_parity import replay_ranking_v2

ROOT = Path(__file__).resolve().parents[2]
ORACLE = ROOT / "docs/research/financial_rip_v5_best_open_live_validation.json"
CHECKPOINT = ROOT / "logs/financial_rip_v5_best_open_v3_parity_checkpoint.json"
OUT = ROOT / "docs/research/financial_rip_v5_best_open_v3_parity.json"


def _atomic(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
    os.replace(tmp, path)


def compare_axis(prod: dict, ref: dict, *, financial_axis: bool) -> list:
    """Per-threshold equality against the frozen research artifact."""
    t, rt = prod["threshold"], ref["threshold"]
    checks = {
        "priceCents": t["priceCents"] == rt["priceCents"],
        "quantity": t["quantity"] == rt["quantity"],
        "benchmarkProductId": prod["benchmarkProductId"] == ref["benchmarkProductId"],
        "financialV5Score": t["financialRipV5Score"] == rt["financialRipV5CandidateScore"],
        "overallV14Score": t["overallRipV14Score"] == rt["overallRipFinancialV5ShadowScore"],
        "pWin": math.isclose(float(t["chanceToRecoverCapital"]), float(rt["chanceToRecoverCapital"]), abs_tol=1e-12),
        "committedCapital": math.isclose(t["actualCommittedCapital"], rt["actualCommittedCapital"], abs_tol=1e-9),
        "thresholdWins": bool(t["wins"]) and prod["exactness"]["thresholdWins"],
        "adjacentCentLoses": prod["exactness"]["oneCentMaximal"] is True
        and prod["exactness"]["nextPriceWins"] in (False, None),
        "status": prod["status"] == ref["status"] == "exact",
    }
    return [k for k, ok in checks.items() if not ok]


def run(product_limit: int = 0, product_id: str | None = None, restart: bool = False) -> int:
    oracle = json.loads(ORACLE.read_text("utf-8"))
    oracle_by_id = {p["sealedProductId"]: p for p in oracle["products"]}
    client = get_client()
    replay = replay_ranking_v2(client)
    snapshot, source_rows, ranked = replay["snapshot"], replay["sourceRows"], replay["ranked"]
    budget, product_by_id = replay["budget"], replay["productById"]
    authority = _historical_authority(snapshot, source_rows)
    if oracle["sourceSnapshotId"] != str(snapshot["id"]):
        raise RuntimeError("oracle and replay snapshot differ")
    fin_order = sorted(ranked, key=lambda r: r["financialOnlyRankV5"])
    overall_order = sorted(ranked, key=lambda r: r["budgetRankV14"])
    fin_rank = {r["sealedProductId"]: r["financialOnlyRankV5"] for r in ranked}
    overall_rank = {r["sealedProductId"]: r["budgetRankV14"] for r in ranked}
    source_by_id = {str(r["sealed_product_id"]): r for r in source_rows}

    done = {}
    if CHECKPOINT.exists() and not restart:
        done = json.loads(CHECKPOINT.read_text("utf-8")).get("results", {})
    order = [r["sealedProductId"] for r in overall_order]
    if product_id:
        order = [p for p in order if p == product_id]
    if product_limit:
        order = order[:product_limit]

    for n, pid in enumerate(order, 1):
        if pid in done:
            continue
        source, product = source_by_id[pid], product_by_id[pid]
        run_id = str(source["source_calculation_run_id"])
        artifact = load_pack_outcome_artifact(client, run_id)
        base = build_stage1_distributions_cached(
            artifact, int(product.get("random_pack_count") or product["pack_count"]), run_id)
        offset_per_unit = float(product.get("guaranteed_component_market_value") or 0)
        chase_raw = float(authority["rawBySet"][str(source["set_id"])])
        collector = float(source["collector_appeal_score"])

        def make(q, prepared):
            return PreparedV5Candidate(pid, q, prepared, collector, chase_raw, budget)

        @lru_cache(maxsize=8)
        def factory(q: int):
            values = build_budget_strategy_values(
                base_random_pack_values=base, quantity=q, guaranteed_component_market_value=None,
                canonical_set_key=f"budget:{pid}", run_fingerprint=None)
            return make(q, PreparedFinancialRipDistribution.prepare(values, value_offset=offset_per_unit * q))

        def batch_factory(quantities):
            built = build_single_q_parity_distributions(
                base, quantities=quantities, canonical_set_key=f"budget:{pid}", run_fingerprint=None)
            out = {}
            for q in quantities:
                values = built["distributions"].pop(q)
                out[q] = make(q, PreparedFinancialRipDistribution.prepare(values, value_offset=offset_per_unit * q))
            return out

        bench_fin = fin_order[1] if fin_rank[pid] == 1 else fin_order[0]
        bench_overall = overall_order[1] if overall_rank[pid] == 1 else overall_order[0]
        width = single_q_parity_batch_width(len(base), requested_width=8,
                                            maximum_quantity=min(4096, round(budget * 100)))
        search = build_dual_best_open_v3_search(
            product_id=pid, budget_cents=round(budget * 100),
            current_price_cents=round(float(source["product_market_price"]) * 100),
            current_quantity=int(source["quantity"]),
            overall_v14_current_rank=overall_rank[pid], overall_v14_benchmark=bench_overall,
            financial_v5_current_rank=fin_rank[pid], financial_v5_benchmark=bench_fin,
            source_ranking_method_version=BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2,
            prepare_quantity=factory, prepare_quantities=batch_factory,
            source_authority_fingerprint=authority["fingerprint"],
            expected_source_authority_fingerprint=authority["fingerprint"],
            quantity_batch_size=width, enable_quantity_prefetch=True, rng_outcome_count=len(base))
        result = run_dual_best_open_v3(search)
        ref = oracle_by_id[pid]
        failed = {"financial": compare_axis(result["financialResult"], ref["financialV5"], financial_axis=True),
                  "overall": compare_axis(result["overallResult"], ref["overallV5Shadow"], financial_axis=False)}
        done[pid] = {
            "sealedProductId": pid, "failed": failed,
            "financial": {k: result["financialResult"]["threshold"][k] for k in
                          ("priceCents", "quantity", "financialRipV5Score", "chanceToRecoverCapital")},
            "overall": {k: result["overallResult"]["threshold"][k] for k in
                        ("priceCents", "quantity", "overallRipV14Score", "financialRipV5Score")},
            "methodVersion": result["overallResult"]["methodVersion"],
            "wallSeconds": result["financialResult"]["wallSeconds"],
        }
        _atomic(CHECKPOINT, {"results": done})
        print(f"{n}/{len(order)} {product.get('product_name')} failed={failed}", flush=True)

    mismatches = {p: r["failed"] for p, r in done.items() if r["failed"]["financial"] or r["failed"]["overall"]}
    report = {
        "methodVersion": BEST_OPEN_PRICE_V3_METHOD_VERSION,
        "sourceRankingMethod": BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2,
        "snapshotId": str(snapshot["id"]), "productsCompared": len(done),
        "thresholdsCompared": 2 * len(done), "mismatchedProducts": len(mismatches),
        "mismatches": mismatches, "complete": len(done) == len(oracle_by_id),
        "perThresholdEquality": not mismatches and len(done) == len(oracle_by_id),
    }
    if not product_limit and not product_id:
        OUT.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "mismatches"}))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--product-limit", type=int, default=0)
    p.add_argument("--product-id")
    p.add_argument("--restart", action="store_true")
    a = p.parse_args()
    sys.exit(run(a.product_limit, a.product_id, a.restart))
