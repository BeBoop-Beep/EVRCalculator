"""Bucket 3 research: trace-replay simulator for batch-width / ramp policies.

Replays the ACTUAL per-product q-request sequences (recorded by
``run_best_open_price_v2_prepared_optimization --trace``) through the real
``PreparedLifecycleBatchedDualBestOpenPriceSearch`` planner with fake builders,
so widths, phase resets, speculation and abandoned-block behaviour are those of
the real code.  The physical build cost is a fitted linear model
(``a*max(q) + b*sum(q) + c`` in units of one n-outcome pass); the simulator is
only used to eliminate poor policies - finalists are judged by REAL timing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from backend.calculations.evr.best_open_price_v2_fused_batched_prepared import (
    PreparedLifecycleBatchedDualBestOpenPriceSearch as Search,
)


class _Sim(Search):
    def _validate_candidate(self, quantity, candidate):  # replay only
        return None


def fit_cost_model(traces: Dict[str, Any]) -> Tuple[float, float, float, int]:
    rows, ys = [], []
    for t in traces.values():
        for e in t["events"]:
            if e["kind"] == "block":
                p = e["planned"]
                rows.append([max(p), sum(p), 1.0])
                ys.append(e["seconds"])
    a, *_ = np.linalg.lstsq(np.asarray(rows), np.asarray(ys), rcond=None)
    pred = np.asarray(rows) @ a
    r2 = 1.0 - float(((np.asarray(ys) - pred) ** 2).sum() / ((np.asarray(ys) - np.mean(ys)) ** 2).sum())
    return float(a[0]), float(a[1]), float(a[2]), len(ys), r2


def simulate(traces: Dict[str, Any], *, initial_width: int, max_width: int, abandon: str,
             model: Tuple[float, float, float]) -> Dict[str, Any]:
    a, b, c = model
    totals = dict(blocks=0, generated=0, consumed=0, speculative=0, seconds=0.0, resets=0, abandoned=0)
    widths: List[int] = []
    for pid, t in traces.items():
        n = int(t["n"])
        events = [e for e in t["events"] if e["kind"] == "request"]
        z = np.broadcast_to(np.zeros(1, dtype=np.float64), (n,))
        state: Dict[str, Any] = {"seconds": 0.0}

        def build(quantities, **_kw):
            qs = list(quantities)
            state["seconds"] += (a * max(qs) + b * sum(qs) + c) * (n / 1_000_000.0)
            return {"distributions": {q: z for q in qs}, "meta": {}}

        s = _Sim(
            product_id="sim", budget_cents=int(t["budgetCents"]), current_price_cents=int(t["currentPriceCents"]),
            current_quantity=2, rip_current_rank=2,
            rip_benchmark={"sealedProductId": "r", "thresholdCents": 1},
            financial_current_rank=2, financial_benchmark={"sealedProductId": "f", "thresholdCents": 1},
            source_authority_fingerprint="fp", expected_source_authority_fingerprint="fp",
            max_quantity_to_construct=int(t["maxQuantityToConstruct"]),
            prepare_quantity=lambda q: object(),
            build_block=build, prepare_from_values=lambda q, v: object(),
            rng_outcome_count=n, initial_width=initial_width, max_width=max_width, abandon_policy=abandon,
        )
        for e in events:
            s._phase = e["phase"]
            s._resident_candidate = None
            s._resident_quantity = None
            s._candidate(int(e["q"]))
        s._finalize_block(abandoned=True)
        totals["blocks"] += s._batch_build_count
        totals["generated"] += s._block_generated_count
        totals["consumed"] += s._consumed_from_block
        totals["speculative"] += s._block_generated_count - s._consumed_from_block
        totals["seconds"] += state["seconds"]
        totals["resets"] += s._ramp_resets
        totals["abandoned"] += s._blocks_abandoned
        widths.extend(s._block_width_history)
    totals["avgWidth"] = float(np.mean(widths)) if widths else 0.0
    totals["speculativeRatio"] = totals["speculative"] / totals["generated"] if totals["generated"] else 0.0
    return totals


POLICIES = {
    "control_const24": dict(initial_width=24, abandon="none"),
    "A_8_16_24": dict(initial_width=8, abandon="none"),
    "B_4_8_16_24_bucket2": dict(initial_width=4, abandon="none"),
    "B2_2_4_8_16_24": dict(initial_width=2, abandon="none"),
    "C_reset_init4": dict(initial_width=4, abandon="reset"),
    "C_reset_init8": dict(initial_width=8, abandon="reset"),
    "C_halve_init4": dict(initial_width=4, abandon="halve"),
    "C_halve_init8": dict(initial_width=8, abandon="halve"),
    "const12": dict(initial_width=12, abandon="none"),
    "const16": dict(initial_width=16, abandon="none"),
}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--max-width", type=int, default=24)
    args = ap.parse_args(argv)
    traces = json.loads(args.trace.read_text(encoding="utf-8"))
    a, b, c, nblocks, r2 = fit_cost_model(traces)
    out = {"costModel": {"perMaxQ": a, "perSumQ": b, "perBlock": c, "fitBlocks": nblocks, "r2": r2,
                         "unit": "seconds per 1M outcomes"}, "policies": {}}
    for name, cfg in POLICIES.items():
        res = simulate(traces, initial_width=cfg["initial_width"], max_width=args.max_width,
                       abandon=cfg["abandon"], model=(a, b, c))
        out["policies"][name] = res
        print(f"{name:24s} blocks={res['blocks']:5d} gen={res['generated']:6d} spec={res['speculative']:5d} "
              f"({res['speculativeRatio']*100:5.1f}%) avgW={res['avgWidth']:5.1f} resets={res['resets']:4d} "
              f"modeled_build_s={res['seconds']:8.1f}", flush=True)
    args.output.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
