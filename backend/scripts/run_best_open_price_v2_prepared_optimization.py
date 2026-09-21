"""Bucket 3 read-only runner: prepared-scorer / speculative-batch optimization A/B for fused V2 Best-Open.

Variants (all through the identical ``research_best_open_price_v2.run`` orchestration and the
identical frozen-oracle parity validation as Bucket 2):

* ``bucket2``  : Bucket 2 engine + canonical ``prepare``      (the A/B control)
* ``prepared`` : lifecycle engine + ``prepare_exact_accelerated`` (+ optional ramp/abandon policy)

Read-only: no persistence, publication, pointer or frontend write.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from backend.calculations.evr.best_open_price_v2_fused_batched import (
    BoundedBatchedDualBestOpenPriceSearch as Bucket2Search,
)
from backend.calculations.evr.best_open_price_v2_fused_batched_prepared import (
    PreparedLifecycleBatchedDualBestOpenPriceSearch as PreparedSearch,
)
import backend.scripts.research_best_open_price_v2 as research_v2
from backend.scripts.pokemon_snapshot_builders import get_client
from backend.scripts.run_best_open_price_v2_bounded_batched import (
    DEFAULT_REFERENCE, EXPECTED_AUTHORITY_FINGERPRINT, EXPECTED_FULL_COHORT_SIZE, FOUR_PRODUCTS,
    SOURCE_SNAPSHOT_ID, _RssSampler, _load, select_stratified, summarize, validate_parity,
)


def extra_summary(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    diags = [dict(r.get("diagnostics") or {}) for r in rows]

    def total(key: str) -> float:
        return float(sum(float(d.get(key) or 0) for d in diags))

    widths: Counter = Counter()
    for d in diags:
        widths.update(int(w) for w in d.get("blockWidths") or [])
    n_blocks = sum(widths.values())
    out = {
        "preparedBuilt": int(total("preparedBuilt")),
        "speculativePreparationsAvoided": int(total("speculativePreparationsAvoided")),
        "blocksAbandoned": int(total("blocksAbandoned")),
        "blocksFullyConsumed": int(total("blocksFullyConsumed")),
        "rampResets": int(total("rampResets")),
        "averageBlockWidth": (sum(w * c for w, c in widths.items()) / n_blocks) if n_blocks else 0.0,
        "blockWidthDistribution": {str(w): c for w, c in sorted(widths.items())},
        "maxRawPendingBytes": int(max((d.get("maxRawPendingBytes") or 0) for d in diags) if diags else 0),
        "maxPreparedBytes": int(max((d.get("maxPreparedBytes") or 0) for d in diags) if diags else 0),
        "maxPendingPlusPreparedBytes": int(max((d.get("maxPendingPlusPreparedBytes") or 0) for d in diags) if diags else 0),
        "consumedBuildSecondsEstimate": total("consumedBuildSecondsEstimate"),
        "speculativeBuildSecondsEstimate": total("speculativeBuildSecondsEstimate"),
        "marginalSpeculativeSeconds": total("marginalSpeculativeSeconds"),
        "marginalMeasuredBlocks": int(total("marginalMeasuredBlocks")),
    }
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("bucket2", "prepared"), required=True)
    parser.add_argument("--preset", choices=("four", "stratified", "full"), default="four")
    parser.add_argument("--products", default="")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--initial-width", type=int, default=4)
    parser.add_argument("--max-width", type=int, default=24)
    parser.add_argument("--abandon-policy", choices=("none", "reset", "halve"), default="none")
    parser.add_argument("--prepare-variant", choices=("canonical", "accelerated"), default=None)
    parser.add_argument("--trace", type=Path, default=None,
                        help="write compact per-product q-request/block trace (research only)")
    parser.add_argument("--measure-marginal", action="store_true",
                        help="research only: rebuild consumed-only blocks to measure exact speculative cost")
    parser.add_argument("--max-quantity-to-construct", type=int, default=4096)
    args = parser.parse_args(argv)

    reference = _load(args.reference)
    if reference.get("sourceAuthorityFingerprint") != EXPECTED_AUTHORITY_FINGERPRINT:
        raise RuntimeError("reference oracle authority fingerprint mismatch")
    all_ids = [str(r["sealedProductId"]) for r in reference["products"]]
    if len(all_ids) != EXPECTED_FULL_COHORT_SIZE:
        raise RuntimeError("reference oracle is not the frozen 138-product cohort")
    if args.products:
        product_ids: Optional[List[str]] = []
        for token in (t.strip() for t in args.products.split(",") if t.strip()):
            product_ids.append(next(p for p in all_ids if p.startswith(token)))
    elif args.preset == "four":
        product_ids = list(FOUR_PRODUCTS)
    elif args.preset == "stratified":
        product_ids = select_stratified(reference)
    else:
        product_ids = None
    expected_ids = product_ids if product_ids is not None else all_ids

    prepare_variant = args.prepare_variant or ("accelerated" if args.variant == "prepared" else "canonical")
    bounded: Dict[str, Any] = {
        "initial_width": args.initial_width, "max_width": args.max_width,
        "prepare_variant": prepare_variant,
    }
    trace_store: Dict[str, List[Dict[str, Any]]] = {}
    if args.variant == "prepared":
        research_v2.DualBestOpenPriceSearch = PreparedSearch
        bounded["abandon_policy"] = args.abandon_policy
        bounded["measure_speculative_marginal"] = bool(args.measure_marginal)
        if args.trace is not None:
            bounded["trace"] = []  # replaced per product below via wrapper
    else:
        research_v2.DualBestOpenPriceSearch = Bucket2Search

    if args.variant == "prepared" and args.trace is not None:
        class _TracingSearch(PreparedSearch):
            def search(self):
                self.trace = []
                try:
                    return super().search()
                finally:
                    trace_store[str(self.product_id)] = {
                        "budgetCents": self.budget_cents, "currentPriceCents": self.current_price_cents,
                        "maxQuantityToConstruct": self.max_quantity_to_construct,
                        "n": int(self.rng_outcome_count), "events": self.trace,
                    }
        research_v2.DualBestOpenPriceSearch = _TracingSearch
        bounded.pop("trace", None)

    checkpoint_rows: List[Dict[str, Any]] = []
    if args.checkpoint and args.resume and args.checkpoint.exists():
        checkpoint_rows = [json.loads(line) for line in args.checkpoint.read_text(encoding="utf-8").splitlines() if line.strip()]
    skip = {str(r["sealedProductId"]) for r in checkpoint_rows}
    deltas: Dict[str, float] = {}
    last = [time.perf_counter()]
    done = [len(skip)]

    def on_row(row: Dict[str, Any]) -> None:
        now = time.perf_counter()
        pid = str(row["sealedProductId"])
        deltas[pid] = now - last[0]
        last[0] = now
        done[0] += 1
        row["_productWallSeconds"] = deltas[pid]
        if args.checkpoint:
            args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
            with args.checkpoint.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        print(f"[{done[0]}/{len(expected_ids)}] {pid[:8]} rip={row.get('ripBestOpenPriceCents')} "
              f"fin={row.get('financialBestOpenPriceCents')} wall={deltas[pid]:.1f}s "
              f"engine={row.get('searchWallSeconds', 0):.1f}s", flush=True)

    sampler = _RssSampler()
    sampler.start()
    started = time.perf_counter()
    try:
        result = research_v2.run(
            get_client(),
            source_snapshot_id=SOURCE_SNAPSHOT_ID,
            expected_source_authority_fingerprint=EXPECTED_AUTHORITY_FINGERPRINT,
            product_ids=product_ids,
            max_quantity_to_construct=args.max_quantity_to_construct,
            skip_product_ids=skip or None,
            checkpoint_callback=on_row,
            bounded_batching=bounded,
        )
    finally:
        wall = time.perf_counter() - started
        sampler.stop()

    rows = checkpoint_rows + list(result["products"])
    for row in rows:
        if "_productWallSeconds" in row:
            deltas.setdefault(str(row["sealedProductId"]), float(row["_productWallSeconds"]))
    validation = validate_parity(reference, {"products": rows}, expected_ids=expected_ids)
    summary = summarize(rows, deltas)
    summary.update(extra_summary(rows))
    payload = {
        "phase": "BEST_OPEN_PRICE_V2_BUCKET3_PREPARED_SCORER_OPTIMIZATION",
        "variant": args.variant, "readOnly": True,
        "preset": "explicit" if args.products else args.preset,
        "config": {"initialWidth": args.initial_width, "maxWidth": args.max_width,
                   "abandonPolicy": args.abandon_policy, "prepareVariant": prepare_variant,
                   "measureMarginal": bool(args.measure_marginal), "resumedProducts": len(skip)},
        "profiling": {"wallSeconds": wall, "peakRssBytes": sampler.peak_rss_bytes,
                      "baselineRssBytes": sampler.baseline_rss_bytes},
        "validation": validation, "summary": summary, "productIds": expected_ids,
        "productWallSeconds": {pid[:8]: round(deltas.get(pid, 0.0), 3) for pid in expected_ids},
        "engineResult": {"products": rows},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    if args.trace is not None:
        args.trace.write_text(json.dumps(trace_store, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "variant": args.variant, "profiling": payload["profiling"],
                      "validation": {k: v for k, v in validation.items() if k != "mismatches"},
                      "summary": summary}, indent=2, sort_keys=True), flush=True)
    return 0 if validation["allExact"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
