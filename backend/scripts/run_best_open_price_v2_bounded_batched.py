"""Bucket 2 read-only runner: bounded exact multi-q batching for fused V2 Best-Open.

Runs either the proven fused streaming control (``--engine control``) or the
bounded look-ahead candidate (``--engine batched``) through the identical
``research_best_open_price_v2.run`` orchestration, then requires exact parity
against the frozen threshold oracle
(``docs/research/financial_rip_v5_best_open_v2_control.json``): cents, threshold
quantities, benchmark identities, threshold score evidence and the P* / P*+1
exactness payload for every attempted product and both axes.

Read-only: no persistence, migration, publication, pointer update or frontend
write.  Checkpoints go to a local JSONL under ``logs/`` only.
"""
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from backend.calculations.evr.best_open_price_v2_fused import (
    DualBestOpenPriceSearch as ControlSearch,
)
from backend.calculations.evr.best_open_price_v2_fused_batched import (
    BoundedBatchedDualBestOpenPriceSearch as BatchedSearch,
)
from backend.scripts.pokemon_snapshot_builders import get_client
import backend.scripts.research_best_open_price_v2 as research_v2

SOURCE_SNAPSHOT_ID = "0e65fb6d-ff33-4331-99d5-d6a214ecc712"
EXPECTED_AUTHORITY_FINGERPRINT = "faad453f7d29eff1831fb2e212a13dad7d9d553536dc283af90c9bfbd53e48b0"
EXPECTED_FULL_COHORT_SIZE = 138
DEFAULT_REFERENCE = Path("docs/research/financial_rip_v5_best_open_v2_control.json")

FOUR_PRODUCTS = (
    "c29f8489-22db-4ad0-9022-c1a40e503f14",
    "dbfd9f2d-5509-45b2-a08f-ba5e09ad2ff4",
    "9f17422e-60e7-4487-a2bf-f11819a48f34",
    "2c4b1825-03d4-4bfa-9438-2878a3f05d58",
)
SLOWEST_FIVE_PREFIXES = ("29a5781f", "9f17422e", "0ac601d0", "3053c510", "f4f8fbc0")

_EVIDENCE_FIELDS = (
    "ripThresholdFinancialRipV4Score", "ripThresholdOverallRipV12Score",
    "ripThresholdChanceToRecoverCapital", "ripThresholdActualCommittedCapital",
    "financialThresholdFinancialRipV4Score", "financialThresholdOverallRipV12Score",
    "financialThresholdChanceToRecoverCapital", "financialThresholdActualCommittedCapital",
)


class _RssSampler:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.peak_rss_bytes: Optional[int] = None
        self.baseline_rss_bytes: Optional[int] = None

    def start(self) -> None:
        try:
            import psutil
            process = psutil.Process()
            self.baseline_rss_bytes = int(process.memory_info().rss)
            self.peak_rss_bytes = self.baseline_rss_bytes
        except (ImportError, OSError):
            return

        def sample() -> None:
            while not self._stop.wait(0.2):
                try:
                    rss = int(process.memory_info().rss)
                except OSError:
                    return
                self.peak_rss_bytes = max(self.peak_rss_bytes or 0, rss)

        self._thread = threading.Thread(target=sample, name="bo-bounded-rss", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _cents(row: Mapping[str, Any], axis: str) -> Optional[int]:
    value = row.get("ripBestOpenPriceCents" if axis == "rip" else "financialBestOpenPriceCents")
    return int(value) if value is not None else None


def select_stratified(reference: Mapping[str, Any]) -> list[str]:
    """Deterministic stratified subset chosen from the frozen oracle."""
    rows = list(reference["products"])
    by_id = {str(r["sealedProductId"]): r for r in rows}

    def max_q(r):
        return max(int(r.get("ripThresholdQuantity") or 0), int(r.get("financialThresholdQuantity") or 0),
                   int(r.get("currentQuantity") or 0))

    def construction(r):
        return float((r.get("diagnostics") or {}).get("quantityConstructionSeconds") or 0.0)

    def scores(r):
        return int((r.get("diagnostics") or {}).get("uniqueCandidatePricesScored") or 0)

    chosen: list[str] = []

    def add(row):
        pid = str(row["sealedProductId"])
        if pid not in chosen:
            chosen.append(pid)

    add(min(rows, key=lambda r: int(r["currentBudgetRank"])))                  # current #1 leader
    for r in rows:
        if int(r.get("currentQuantity") or 0) == 1:
            add(r)                                                              # q=1 product(s)
    low = [r for r in rows if max_q(r) <= 12]
    if low:
        add(max(low, key=scores))                                               # expensive low-q
    ordered_q = sorted(rows, key=max_q)
    add(ordered_q[len(ordered_q) // 2])                                         # medium-q
    add(ordered_q[-1])                                                          # highest-q
    for prefix in SLOWEST_FIVE_PREFIXES:                                        # slowest fused
        for pid in by_id:
            if pid.startswith(prefix):
                add(by_id[pid])
    for pid in FOUR_PRODUCTS:
        add(by_id[pid])
    families = sorted({str(r.get("productFamily")) for r in rows})
    for family in families:                                                     # per-family: slowest + median
        members = sorted((r for r in rows if str(r.get("productFamily")) == family),
                         key=lambda r: (construction(r), str(r["sealedProductId"])))
        add(members[-1])
        add(members[len(members) // 2])
    return chosen


def validate_parity(
    reference: Mapping[str, Any], result: Mapping[str, Any], *, expected_ids: Sequence[str],
) -> dict[str, Any]:
    ref = {str(r["sealedProductId"]): r for r in reference["products"]}
    got = {str(r["sealedProductId"]): r for r in result["products"]}
    if set(got) != set(expected_ids):
        raise RuntimeError(f"product set mismatch: missing={sorted(set(expected_ids)-set(got))} "
                           f"extra={sorted(set(got)-set(expected_ids))}")
    threshold_matches = 0
    mismatches = []
    exactness_failures = []
    unresolved = 0
    for pid in sorted(got):
        expected, actual = ref[pid], got[pid]
        ok = True
        detail: dict[str, Any] = {"sealedProductId": pid}
        if not actual.get("resolved"):
            unresolved += 1
            ok = False
        for axis in ("rip", "financial"):
            qkey = "ripThresholdQuantity" if axis == "rip" else "financialThresholdQuantity"
            bkey = "ripBenchmarkSealedProductId" if axis == "rip" else "financialBenchmarkSealedProductId"
            ekey = "ripExactness" if axis == "rip" else "financialExactness"
            same_cents = _cents(expected, axis) == _cents(actual, axis)
            threshold_matches += int(same_cents)
            same_q = expected.get(qkey) == actual.get(qkey)
            same_bench = expected.get(bkey) == actual.get(bkey)
            same_exact = expected.get(ekey) == actual.get(ekey)
            ex = actual.get(ekey) or {}
            exact = (ex.get("thresholdWins") is True and ex.get("oneCentMaximal") is True
                     and ex.get("nextPriceWins") is not True)
            if not exact:
                exactness_failures.append({"sealedProductId": pid, "axis": axis})
            axis_ok = same_cents and same_q and same_bench and same_exact and exact
            detail[axis] = {"cents": [_cents(expected, axis), _cents(actual, axis)],
                            "quantity": [expected.get(qkey), actual.get(qkey)],
                            "benchmarkMatch": same_bench, "exactnessEqual": same_exact}
            ok = ok and axis_ok
        evidence_equal = all(expected.get(f) == actual.get(f) for f in _EVIDENCE_FIELDS)
        detail["thresholdEvidenceEqual"] = evidence_equal
        ok = ok and evidence_equal
        if not ok:
            mismatches.append(detail)
    return {
        "productCount": len(got),
        "thresholdCount": len(got) * 2,
        "thresholdMatches": threshold_matches,
        "unresolved": unresolved,
        "exactnessFailures": len(exactness_failures),
        "mismatchedProducts": len(mismatches),
        "allExact": threshold_matches == len(got) * 2 and not mismatches
                    and not exactness_failures and unresolved == 0,
        "mismatches": mismatches[:20],
    }


def _pct(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


def summarize(rows: Sequence[Mapping[str, Any]], deltas: Mapping[str, float]) -> dict[str, Any]:
    diags = [dict(r.get("diagnostics") or {}) for r in rows]

    def total(key: str) -> float:
        return sum(float(d.get(key) or 0) for d in diags)

    walls = [float(r.get("searchWallSeconds") or 0.0) for r in rows]
    product_walls = [float(deltas[str(r["sealedProductId"])]) for r in rows if str(r["sealedProductId"]) in deltas]
    generated = total("quantityBatchQuantities")
    speculative = total("speculativeQuantitiesGeneratedNotConsumed")
    out = {
        "products": len(rows),
        "candidatePricesScored": int(total("uniqueCandidatePricesScored")),
        "quantityConstructions": int(total("quantityConstructionCount")),
        "uniqueQuantitiesRequested": int(total("uniqueQuantitiesRequested") or total("uniqueQuantitiesConstructed")),
        "quantitiesConsumed": int(total("quantitiesConsumed")),
        "batchBuilds": int(total("quantityBatchBuilds")),
        "batchQuantitiesGenerated": int(generated),
        "speculativeGeneratedNotConsumed": int(speculative),
        "speculativeWasteRatio": (speculative / generated) if generated else 0.0,
        "fallbacks": int(total("quantityBatchFallbacks")),
        "maxPendingQuantities": int(max((d.get("maximumPendingBatchCandidates") or 0) for d in diags) if diags else 0),
        "maxActivePreparedQuantities": int(max((d.get("maximumActivePreparedQuantities") or d.get("maximumResidentSharedQuantities") or 0) for d in diags) if diags else 0),
        "maxEstimatedBatchBytes": int(max((d.get("maximumEstimatedBatchBytes") or 0) for d in diags) if diags else 0),
        "physicalQuantityConstructionSeconds": total("physicalQuantityConstructionSeconds") or total("quantityConstructionSeconds"),
        "preparedScorerSeconds": total("preparedScorerSeconds"),
        "quantityConstructionSecondsInclPrepare": total("quantityConstructionSeconds"),
        "candidateScoringSeconds": total("priceScoringSeconds"),
        "comparatorSeconds": total("comparatorSeconds"),
        "effectiveRngDraws": int(total("effectiveRngDraws")),
        "legacyEquivalentRngDraws": int(total("legacyEquivalentRngDraws")),
        "engineWallSecondsSum": sum(walls),
        "engineWallMedian": statistics.median(walls) if walls else 0.0,
        "engineWallP95": _pct(walls, 0.95),
        "engineWallMax": max(walls) if walls else 0.0,
        "productWallSecondsSum": sum(product_walls),
        "productWallMedian": statistics.median(product_walls) if product_walls else 0.0,
        "productWallP95": _pct(product_walls, 0.95),
        "productWallMax": max(product_walls) if product_walls else 0.0,
    }
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("control", "batched"), required=True)
    parser.add_argument("--preset", choices=("four", "stratified", "full"), default="four")
    parser.add_argument("--products", default="", help="comma separated ids; overrides --preset")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--initial-width", type=int, default=4)
    parser.add_argument("--max-width", type=int, default=24)
    parser.add_argument("--max-quantity-to-construct", type=int, default=4096)
    parser.add_argument("--source-snapshot-id", default=SOURCE_SNAPSHOT_ID)
    parser.add_argument("--expected-source-authority-fingerprint", default=EXPECTED_AUTHORITY_FINGERPRINT)
    args = parser.parse_args(argv)

    reference = _load(args.reference)
    if reference.get("sourceAuthorityFingerprint") != args.expected_source_authority_fingerprint:
        raise RuntimeError("reference oracle authority fingerprint mismatch")
    all_ids = [str(r["sealedProductId"]) for r in reference["products"]]
    if len(all_ids) != EXPECTED_FULL_COHORT_SIZE:
        raise RuntimeError("reference oracle is not the frozen 138-product cohort")

    if args.products:
        product_ids = [p.strip() for p in args.products.split(",") if p.strip()]
    elif args.preset == "four":
        product_ids = list(FOUR_PRODUCTS)
    elif args.preset == "stratified":
        product_ids = select_stratified(reference)
    else:
        product_ids = None
    expected_ids = product_ids if product_ids is not None else all_ids

    research_v2.DualBestOpenPriceSearch = BatchedSearch if args.engine == "batched" else ControlSearch
    bounded = (
        {"initial_width": args.initial_width, "max_width": args.max_width}
        if args.engine == "batched" else None
    )

    checkpoint_rows: list[dict[str, Any]] = []
    if args.checkpoint and args.resume and args.checkpoint.exists():
        checkpoint_rows = [json.loads(line) for line in args.checkpoint.read_text(encoding="utf-8").splitlines() if line.strip()]
    skip = {str(r["sealedProductId"]) for r in checkpoint_rows}
    deltas: dict[str, float] = {}
    last = [time.perf_counter()]
    done = [len(skip)]

    def on_row(row: dict[str, Any]) -> None:
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
        client = get_client()
        result = research_v2.run(
            client,
            source_snapshot_id=args.source_snapshot_id,
            expected_source_authority_fingerprint=args.expected_source_authority_fingerprint,
            product_ids=product_ids,
            max_quantity_to_construct=args.max_quantity_to_construct,
            skip_product_ids=skip or None,
            checkpoint_callback=on_row,
            bounded_batching=bounded,
        ) if args.engine == "batched" else research_v2.run(
            client,
            source_snapshot_id=args.source_snapshot_id,
            expected_source_authority_fingerprint=args.expected_source_authority_fingerprint,
            product_ids=product_ids,
            max_quantity_to_construct=args.max_quantity_to_construct,
            skip_product_ids=skip or None,
            checkpoint_callback=on_row,
        )
    finally:
        wall = time.perf_counter() - started
        sampler.stop()

    rows = checkpoint_rows + list(result["products"])
    for row in rows:
        if "_productWallSeconds" in row:
            deltas.setdefault(str(row["sealedProductId"]), float(row["_productWallSeconds"]))
    merged = {"products": rows}
    validation = validate_parity(reference, merged, expected_ids=expected_ids)
    summary = summarize(rows, deltas)
    payload = {
        "phase": "BEST_OPEN_PRICE_V2_BUCKET2_BOUNDED_QUANTITY_BATCHING",
        "engine": args.engine,
        "readOnly": True,
        "preset": "explicit" if args.products else args.preset,
        "source": {
            "snapshotId": args.source_snapshot_id,
            "authorityFingerprint": args.expected_source_authority_fingerprint,
            "oracle": str(args.reference),
        },
        "config": {"initialWidth": args.initial_width, "maxWidth": args.max_width,
                   "resumedProducts": len(skip)},
        "profiling": {
            "wallSeconds": wall,
            "peakRssBytes": sampler.peak_rss_bytes,
            "baselineRssBytes": sampler.baseline_rss_bytes,
        },
        "validation": validation,
        "summary": summary,
        "productIds": expected_ids,
        "engineResult": merged,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "engine": args.engine, "profiling": payload["profiling"],
                      "validation": {k: v for k, v in validation.items() if k != "mismatches"},
                      "summary": summary}, indent=2, sort_keys=True), flush=True)
    return 0 if validation["allExact"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
