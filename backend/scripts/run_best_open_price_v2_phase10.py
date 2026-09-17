"""Phase 10 read-only validation runner for Best-Open Price V2.

Runs the dual Financial/RIP exact search against the frozen Sep. 14 Budget
Ranking authority, writes a JSON research artifact, and performs cohort-level
validation/analysis. This script contains no persistence or publication calls.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.scripts.pokemon_snapshot_builders import get_client
from backend.scripts.research_best_open_price_v2 import run as run_v2

SOURCE_SNAPSHOT_ID = "0e65fb6d-ff33-4331-99d5-d6a214ecc712"
EXPECTED_AUTHORITY_FINGERPRINT = "faad453f7d29eff1831fb2e212a13dad7d9d553536dc283af90c9bfbd53e48b0"
EXPECTED_FULL_COHORT_SIZE = 138
DEFAULT_OUTPUT = Path("logs/best_open_price_v2_phase10_sep14.json")


def _percentile(values: Sequence[float], q: float) -> float | None:
    clean = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * (q / 100.0)
    lo = int(math.floor(position))
    hi = int(math.ceil(position))
    if lo == hi:
        return clean[lo]
    weight = position - lo
    return clean[lo] * (1.0 - weight) + clean[hi] * weight


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    pairs = [
        (float(x), float(y))
        for x, y in zip(xs, ys)
        if x is not None and y is not None
        and math.isfinite(float(x)) and math.isfinite(float(y))
    ]
    if len(pairs) < 2:
        return None
    xvals = [p[0] for p in pairs]
    yvals = [p[1] for p in pairs]
    xmean = statistics.fmean(xvals)
    ymean = statistics.fmean(yvals)
    xdev = [x - xmean for x in xvals]
    ydev = [y - ymean for y in yvals]
    xss = sum(v * v for v in xdev)
    yss = sum(v * v for v in ydev)
    if xss <= 0 or yss <= 0:
        return None
    return sum(x * y for x, y in zip(xdev, ydev)) / math.sqrt(xss * yss)


def _group_summary(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key)), []).append(row)
    out: dict[str, Any] = {}
    for name, items in sorted(grouped.items()):
        dollar = [float(item["financialMinusRipDollars"]) for item in items]
        pct = [float(item["financialMinusRipPercentOfRip"]) for item in items]
        out[name] = {
            "count": len(items),
            "financialAboveRip": sum(v > 0 for v in dollar),
            "equal": sum(v == 0 for v in dollar),
            "financialBelowRip": sum(v < 0 for v in dollar),
            "medianDifferenceDollars": _percentile(dollar, 50),
            "medianDifferencePercentOfRip": _percentile(pct, 50),
        }
    return out


def analyze(result: Mapping[str, Any], *, expected_count: int) -> dict[str, Any]:
    products = list(result.get("products") or [])
    cohort = dict(result.get("cohortAnalysis") or {})
    if result.get("status") != "complete":
        raise RuntimeError(f"V2 Phase 10 engine returned status={result.get('status')!r}")
    if len(products) != expected_count:
        raise RuntimeError(f"attempted product count {len(products)} != expected {expected_count}")
    if int(cohort.get("ripResolved") or 0) != expected_count:
        raise RuntimeError("RIP threshold resolution is incomplete")
    if int(cohort.get("financialResolved") or 0) != expected_count:
        raise RuntimeError("Financial threshold resolution is incomplete")
    if int(cohort.get("unresolved") or 0) != 0:
        raise RuntimeError("one or more dual-threshold rows are unresolved")

    derived: list[dict[str, Any]] = []
    exactness_failures: list[dict[str, Any]] = []
    for row in products:
        rip = row.get("ripBestOpenPrice")
        fin = row.get("financialBestOpenPrice")
        if rip is None or fin is None:
            raise RuntimeError(f"missing dual threshold for {row.get('sealedProductId')}")
        rip = float(rip)
        fin = float(fin)
        current = float(row["currentMarketPrice"])
        diff = fin - rip
        diff_pct_rip = diff / rip if rip else 0.0
        rip_distance = current - rip
        fin_distance = current - fin
        record = {
            "sealedProductId": row.get("sealedProductId"),
            "setId": row.get("setId"),
            "productFamily": row.get("productFamily"),
            "currentBudgetRank": row.get("currentBudgetRank"),
            "currentFinancialOnlyRank": row.get("currentFinancialOnlyRank"),
            "currentMarketPrice": current,
            "ripBestOpenPrice": rip,
            "financialBestOpenPrice": fin,
            "financialMinusRipDollars": diff,
            "financialMinusRipPercentOfRip": diff_pct_rip,
            "currentMinusRipDollars": rip_distance,
            "currentMinusRipPercent": rip_distance / current if current else None,
            "currentMinusFinancialDollars": fin_distance,
            "currentMinusFinancialPercent": fin_distance / current if current else None,
            "currentFinancialRipV4Score": row.get("currentFinancialRipV4Score"),
            "currentCollectorAppealScore": row.get("currentCollectorAppealScore"),
            "currentChaseAccessibilityRaw": row.get("currentChaseAccessibilityRaw"),
        }
        derived.append(record)
        for axis in ("rip", "financial"):
            exactness = row.get(f"{axis}Exactness") or {}
            if exactness.get("thresholdWins") is not True or exactness.get("oneCentMaximal") is not True:
                exactness_failures.append({
                    "sealedProductId": row.get("sealedProductId"),
                    "axis": axis,
                    "exactness": exactness,
                })
    if exactness_failures:
        raise RuntimeError(f"exactness failed for {len(exactness_failures)} axis/product pairs: {exactness_failures[:3]}")

    diffs = [r["financialMinusRipDollars"] for r in derived]
    diff_pcts = [r["financialMinusRipPercentOfRip"] for r in derived]
    rip_dist_pct = [r["currentMinusRipPercent"] for r in derived if r["currentMinusRipPercent"] is not None]
    fin_dist_pct = [r["currentMinusFinancialPercent"] for r in derived if r["currentMinusFinancialPercent"] is not None]

    diagnostics = [dict(row.get("diagnostics") or {}) for row in products]
    naive = sum(int(d.get("naiveScoreCount") or 0) for d in diagnostics)
    unique_scores = sum(int(d.get("uniqueCandidatePricesScored") or 0) for d in diagnostics)
    cache_hits = sum(int(d.get("scoreCacheHits") or d.get("sharedScoreCacheHits") or 0) for d in diagnostics)
    cache_misses = sum(int(d.get("scoreCacheMisses") or 0) for d in diagnostics)
    cache_evictions = sum(int(d.get("scoreCacheEvictions") or 0) for d in diagnostics)
    quantities = [int(d.get("uniqueQuantitiesConstructed") or 0) for d in diagnostics]

    order_desc = sorted(derived, key=lambda r: r["financialMinusRipDollars"], reverse=True)
    order_asc = list(reversed(order_desc))
    financial_scores = [float(r["currentFinancialRipV4Score"]) for r in derived]
    collector_scores = [float(r["currentCollectorAppealScore"]) for r in derived]
    chase_scores = [float(r["currentChaseAccessibilityRaw"]) for r in derived]

    return {
        "completion": {
            "expected": expected_count,
            "attempted": len(products),
            "ripResolved": int(cohort.get("ripResolved") or 0),
            "financialResolved": int(cohort.get("financialResolved") or 0),
            "unresolved": int(cohort.get("unresolved") or 0),
            "exactnessFailures": 0,
        },
        "divergence": {
            "financialAboveRip": sum(v > 0 for v in diffs),
            "equal": sum(v == 0 for v in diffs),
            "financialBelowRip": sum(v < 0 for v in diffs),
            "differenceDollars": {
                "p25": _percentile(diffs, 25),
                "median": _percentile(diffs, 50),
                "p75": _percentile(diffs, 75),
            },
            "differencePercentOfRip": {
                "p25": _percentile(diff_pcts, 25),
                "median": _percentile(diff_pcts, 50),
                "p75": _percentile(diff_pcts, 75),
            },
            "largestFinancialPremiums": order_desc[:10],
            "largestRipPremiums": order_asc[:10],
        },
        "currentMarketDistance": {
            "ripPercent": {
                "p25": _percentile(rip_dist_pct, 25),
                "median": _percentile(rip_dist_pct, 50),
                "p75": _percentile(rip_dist_pct, 75),
            },
            "financialPercent": {
                "p25": _percentile(fin_dist_pct, 25),
                "median": _percentile(fin_dist_pct, 50),
                "p75": _percentile(fin_dist_pct, 75),
            },
        },
        "relationships": {
            "financialMinusRipPercentVsFinancialRipV4": _pearson(diff_pcts, financial_scores),
            "financialMinusRipPercentVsCollectorAppeal": _pearson(diff_pcts, collector_scores),
            "financialMinusRipPercentVsChaseAccessibilityRaw": _pearson(diff_pcts, chase_scores),
        },
        "byProductFamily": _group_summary(derived, "productFamily"),
        "bySetId": _group_summary(derived, "setId"),
        "sharedWork": {
            "naiveScoreCount": naive,
            "uniqueCandidatePricesScored": unique_scores,
            "scoreReuseSavings": naive - unique_scores,
            "scoreCacheHits": cache_hits,
            "scoreCacheMisses": cache_misses,
            "scoreCacheEvictions": cache_evictions,
            "scoreCacheHitRate": cache_hits / (cache_hits + cache_misses) if (cache_hits + cache_misses) else None,
            "uniqueQuantitiesConstructed": {
                "sum": sum(quantities),
                "p50PerProduct": _percentile(quantities, 50),
                "p95PerProduct": _percentile(quantities, 95),
                "maxPerProduct": max(quantities) if quantities else None,
            },
        },
    }


class _RssSampler:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.peak_rss_bytes: int | None = None

    def start(self) -> None:
        try:
            import psutil
            process = psutil.Process()
        except (ImportError, OSError):
            return

        def sample() -> None:
            while not self._stop.wait(0.25):
                try:
                    rss = int(process.memory_info().rss)
                except OSError:
                    return
                self.peak_rss_bytes = rss if self.peak_rss_bytes is None else max(self.peak_rss_bytes, rss)

        self._thread = threading.Thread(target=sample, name="best-open-v2-rss", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source-snapshot-id", default=SOURCE_SNAPSHOT_ID)
    parser.add_argument("--expected-source-authority-fingerprint", default=EXPECTED_AUTHORITY_FINGERPRINT)
    parser.add_argument("--only-product-id", action="append")
    parser.add_argument("--max-quantity-to-construct", type=int, default=4096)
    args = parser.parse_args(argv)

    client = get_client()
    expected_count = len(args.only_product_id) if args.only_product_id else EXPECTED_FULL_COHORT_SIZE
    sampler = _RssSampler()
    started = time.perf_counter()
    sampler.start()
    try:
        result = run_v2(
            client,
            source_snapshot_id=args.source_snapshot_id,
            expected_source_authority_fingerprint=args.expected_source_authority_fingerprint,
            product_ids=args.only_product_id,
            max_quantity_to_construct=args.max_quantity_to_construct,
        )
    finally:
        sampler.stop()
    wall_seconds = time.perf_counter() - started
    analysis = analyze(result, expected_count=expected_count)

    payload = {
        "phase": "BEST_OPEN_PRICE_V2_PHASE10_READ_ONLY",
        "readOnly": True,
        "source": {
            "snapshotId": args.source_snapshot_id,
            "expectedAuthorityFingerprint": args.expected_source_authority_fingerprint,
            "expectedProductCount": expected_count,
        },
        "profiling": {
            "wallSeconds": wall_seconds,
            "peakRssBytes": sampler.peak_rss_bytes,
        },
        "analysis": analysis,
        "engineResult": result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "profiling": payload["profiling"],
        "completion": analysis["completion"],
        "divergence": {
            key: analysis["divergence"][key]
            for key in ("financialAboveRip", "equal", "financialBelowRip", "differenceDollars", "differencePercentOfRip")
        },
        "sharedWork": analysis["sharedWork"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
