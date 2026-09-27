"""Bucket 3 research profiler: where does PreparedFinancialRipDistribution.prepare spend time?

Read-only.  Loads the real frozen-cohort pack-outcome artifact for a few
representative products, builds real physical quantity vectors with the exact
single-q parity builder, and times every step of ``prepare`` in isolation
(best of ``--repeat``), plus the real ``prepare`` call and the candidate-parity
of each step-composed result versus the production result.  No permanent
overhead in production code: everything here re-implements the steps outside
the shipped module purely for measurement.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.calculations.evr.financial_rip_v3 import (  # noqa: E402
    JACKPOT_TAIL_SHARE, REALISTIC_TAIL_SHARE, PreparedFinancialRipDistribution,
)
from backend.calculations.evr.sealed_product_distribution import build_single_q_parity_distributions  # noqa: E402
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact  # noqa: E402
from backend.scripts.build_budget_normalized_product_rankings import build_stage1_distributions_cached  # noqa: E402
from backend.scripts.pokemon_snapshot_builders import get_client  # noqa: E402
from backend.scripts.research_best_open_price_bucket0 import _load_exact_source_products, _load_source  # noqa: E402

SNAPSHOT = "0e65fb6d-ff33-4331-99d5-d6a214ecc712"
REFERENCE = REPO_ROOT / "docs/research/financial_rip_v5_best_open_v2_control.json"


def best(fn: Callable[[], Any], repeat: int) -> float:
    b = math.inf
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        b = min(b, time.perf_counter() - t)
    return b


def profile_vector(values: np.ndarray, offset: float, repeat: int) -> Dict[str, Any]:
    n = int(values.size)
    t1 = max(1, math.ceil(n * JACKPOT_TAIL_SHARE))
    t5 = max(t1 + 1, math.ceil(n * REALISTIC_TAIL_SHARE))
    steps: Dict[str, float] = {}
    arr = np.asarray(values, dtype=np.float64).ravel()
    steps["input_conversion"] = best(lambda: np.asarray(values, dtype=np.float64).ravel(), repeat)
    steps["finite_validation"] = best(lambda: int(np.count_nonzero(~np.isfinite(arr))), repeat)
    steps["sort_stable"] = best(lambda: np.sort(arr, kind="stable"), repeat)
    s = np.sort(arr, kind="stable")
    steps["prefix_cumsum"] = best(lambda: np.cumsum(s, dtype=np.float64), repeat)
    steps["mean"] = best(lambda: float(arr.mean()), repeat)
    steps["median"] = best(lambda: float(np.median(arr)), repeat)
    steps["percentile_p05"] = best(lambda: float(np.percentile(arr, 5)), repeat)
    steps["percentile_p95"] = best(lambda: float(np.percentile(arr, 95)), repeat)
    steps["percentile_p99"] = best(lambda: float(np.percentile(arr, 99)), repeat)
    steps["distinct_count"] = best(lambda: PreparedFinancialRipDistribution._shifted_distinct_count(s, offset), repeat)
    jack, real, excl = s[n - t1:], s[n - t5:n - t1], s[:n - t1]
    steps["jackpot_aggregates"] = best(
        lambda: (float((jack + offset).mean()), float(jack.sum())), repeat)
    steps["realistic_aggregate"] = best(lambda: float((real + offset).mean()), repeat)
    steps["excluding_jackpot_mean"] = best(lambda: float(excl.mean()), repeat)
    steps["total_sum"] = best(lambda: float(arr.sum()), repeat)
    total = best(lambda: PreparedFinancialRipDistribution.prepare(values, value_offset=offset), repeat)
    steps_sum = sum(steps.values())
    return {"n": n, "stepSeconds": steps, "prepareSeconds": total, "unclassifiedSeconds": total - steps_sum,
            "rawBytes": int(values.nbytes),
            "preparedBytes": int(s.nbytes + (n + 1) * 8)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", required=True, help="comma separated product id prefixes")
    ap.add_argument("--quantities", default="1,24,120,340", help="q values to profile per product")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    ref = {r["sealedProductId"]: r for r in json.loads(REFERENCE.read_text(encoding="utf-8"))["products"]}
    prefixes = [p.strip() for p in args.products.split(",") if p.strip()]
    ids = [next(pid for pid in ref if pid.startswith(p)) for p in prefixes]
    client = get_client()
    snapshot, source_rows, _ = _load_source(client, SNAPSHOT)
    products = {str(p["sealed_product_id"]): p for p in
                _load_exact_source_products(client, source_rows, str(snapshot["pinned_price_as_of"]))}
    out: List[Dict[str, Any]] = []
    for pid in ids:
        product = products[pid]
        run_id = str(product["calculation_run_id"])
        artifact = load_pack_outcome_artifact(client, run_id)
        random_count = int(product.get("random_pack_count") or product["pack_count"])
        base = build_stage1_distributions_cached(artifact, random_count, run_id)
        guaranteed = float(product.get("guaranteed_component_market_value") or 0)
        for q in [int(x) for x in args.quantities.split(",")]:
            t = time.perf_counter()
            built = build_single_q_parity_distributions(base, quantities=[q], canonical_set_key=f"budget:{pid}",
                                                        run_fingerprint=None)
            construct = time.perf_counter() - t
            values = built["distributions"][q]
            prof = profile_vector(values, guaranteed * q, args.repeat)
            prof.update({"product": pid[:8], "q": q, "singleConstructSeconds": construct,
                         "baseOutcomeCount": int(len(base))})
            out.append(prof)
            total = prof["prepareSeconds"]
            top = sorted(prof["stepSeconds"].items(), key=lambda kv: -kv[1])[:4]
            print(f"{pid[:8]} q={q} n={prof['n']} prepare={total*1000:.1f}ms construct={construct:.2f}s "
                  + " ".join(f"{k}={v*1000:.1f}ms" for k, v in top), flush=True)
    args.output.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
