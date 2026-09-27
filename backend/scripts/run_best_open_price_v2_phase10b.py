"""Phase 10B read-only benchmark for the fused V2 dual Best-Open search.

Runs four frozen Sep. 14 products chosen from the completed Phase-10 cohort:
the worst scoring offender/current #1, the largest RIP premium, the maximum
quantity-construction case, and the largest Financial premium.  The fused
engine must reproduce all eight frozen thresholds to the cent before it can be
considered for the production V2 path.

No persistence, migration, pointer update, or publication occurs here.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path
from typing import Any, Sequence

from backend.calculations.evr.best_open_price_v2_fused import (
    DualBestOpenPriceSearch as FusedDualBestOpenPriceSearch,
)
from backend.scripts.pokemon_snapshot_builders import get_client
import backend.scripts.research_best_open_price_v2 as research_v2

SOURCE_SNAPSHOT_ID = "0e65fb6d-ff33-4331-99d5-d6a214ecc712"
EXPECTED_AUTHORITY_FINGERPRINT = "faad453f7d29eff1831fb2e212a13dad7d9d553536dc283af90c9bfbd53e48b0"
DEFAULT_OUTPUT = Path("logs/best_open_price_v2_phase10b_four_product.json")

FROZEN_THRESHOLDS = {
    # Current #1 / Phase-10 worst scoring offender.
    "c29f8489-22db-4ad0-9022-c1a40e503f14": {"rip": 1395, "financial": 1386},
    # Largest RIP-over-Financial premium.
    "dbfd9f2d-5509-45b2-a08f-ba5e09ad2ff4": {"rip": 66243, "financial": 60974},
    # Maximum Phase-10 physical quantity construction (186 distinct q values).
    "9f17422e-60e7-4487-a2bf-f11819a48f34": {"rip": 407, "financial": 409},
    # Largest Financial-over-RIP dollar premium.
    "2c4b1825-03d4-4bfa-9438-2878a3f05d58": {"rip": 22417, "financial": 23053},
}

# Phase-10 sequential baselines available from the frozen artifact.  The
# fourth product was selected from the divergence tail rather than the top-15
# scoring extraction, so no per-product score baseline is asserted for it.
PHASE10_BASELINES = {
    "c29f8489-22db-4ad0-9022-c1a40e503f14": {
        "naiveScores": 257223, "uniqueScores": 257223, "uniqueQuantities": 95,
    },
    "dbfd9f2d-5509-45b2-a08f-ba5e09ad2ff4": {
        "naiveScores": 131420, "uniqueScores": 131420, "uniqueQuantities": 2,
    },
    "9f17422e-60e7-4487-a2bf-f11819a48f34": {
        "naiveScores": 1018, "uniqueScores": 510, "uniqueQuantities": 186,
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
            read_rss = lambda: int(process.memory_info().rss)
        except (ImportError, OSError):
            try:
                import ctypes
                from ctypes import wintypes

                class Counters(ctypes.Structure):
                    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                                ("PeakWorkingSetSize", ctypes.c_size_t),
                                ("WorkingSetSize", ctypes.c_size_t),
                                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                                ("PagefileUsage", ctypes.c_size_t),
                                ("PeakPagefileUsage", ctypes.c_size_t)]

                def read_rss() -> int:
                    value = Counters()
                    value.cb = ctypes.sizeof(value)
                    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
                    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [
                        ctypes.c_void_p, ctypes.POINTER(Counters), wintypes.DWORD]
                    handle = ctypes.windll.kernel32.GetCurrentProcess()
                    if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(value), value.cb):
                        raise OSError("GetProcessMemoryInfo failed")
                    return int(value.PeakWorkingSetSize)
            except (ImportError, AttributeError, OSError):
                return

        def sample() -> None:
            while not self._stop.wait(0.25):
                try:
                    rss = read_rss()
                except OSError:
                    return
                self.peak_rss_bytes = rss if self.peak_rss_bytes is None else max(
                    self.peak_rss_bytes, rss
                )

        self._thread = threading.Thread(
            target=sample, name="best-open-v2-phase10b-rss", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)


def _threshold_cents(row: dict[str, Any], axis: str) -> int | None:
    key = "ripBestOpenPriceCents" if axis == "rip" else "financialBestOpenPriceCents"
    value = row.get(key)
    return int(value) if value is not None else None


def _validate(result: dict[str, Any], *, maximum_resident: int = 1) -> dict[str, Any]:
    products = list(result.get("products") or [])
    by_id = {str(row["sealedProductId"]): row for row in products}
    if set(by_id) != set(FROZEN_THRESHOLDS):
        raise RuntimeError(
            f"Phase 10B cohort mismatch: expected={sorted(FROZEN_THRESHOLDS)} actual={sorted(by_id)}"
        )

    rows = []
    all_matched = True
    total_unique_scores = 0
    total_naive_scores = 0
    total_reuse = 0
    max_resident_quantities = 0
    total_quantity_constructions = 0

    for product_id, expected in FROZEN_THRESHOLDS.items():
        row = by_id[product_id]
        diagnostics = dict(row.get("diagnostics") or {})
        actual_rip = _threshold_cents(row, "rip")
        actual_financial = _threshold_cents(row, "financial")
        rip_exactness = row.get("ripExactness") or {}
        financial_exactness = row.get("financialExactness") or {}
        matched = (
            actual_rip == expected["rip"]
            and actual_financial == expected["financial"]
            and rip_exactness.get("thresholdWins") is True
            and rip_exactness.get("oneCentMaximal") is True
            and financial_exactness.get("thresholdWins") is True
            and financial_exactness.get("oneCentMaximal") is True
        )
        all_matched = all_matched and matched
        unique_scores = int(diagnostics.get("uniqueCandidatePricesScored") or 0)
        naive_scores = int(diagnostics.get("naiveScoreCount") or 0)
        reuse = int(diagnostics.get("scoreReuseSavings") or 0)
        resident = int(diagnostics.get("maximumResidentSharedQuantities") or 0)
        constructions = int(diagnostics.get("quantityConstructionCount") or 0)
        total_unique_scores += unique_scores
        total_naive_scores += naive_scores
        total_reuse += reuse
        max_resident_quantities = max(max_resident_quantities, resident)
        total_quantity_constructions += constructions

        baseline = PHASE10_BASELINES.get(product_id)
        rows.append({
            "sealedProductId": product_id,
            "matchedFrozenThresholds": matched,
            "expectedRipCents": expected["rip"],
            "actualRipCents": actual_rip,
            "expectedFinancialCents": expected["financial"],
            "actualFinancialCents": actual_financial,
            "ripExactness": rip_exactness,
            "financialExactness": financial_exactness,
            "uniqueCandidatePricesScored": unique_scores,
            "naiveScoreCount": naive_scores,
            "scoreReuseSavings": reuse,
            "scoreCacheEvictions": int(diagnostics.get("scoreCacheEvictions") or 0),
            "uniqueQuantitiesConstructed": int(diagnostics.get("uniqueQuantitiesConstructed") or 0),
            "quantityConstructionCount": constructions,
            "maximumResidentSharedQuantities": resident,
            "phase10Baseline": baseline,
            "uniqueScoreReductionVsPhase10": (
                baseline["uniqueScores"] - unique_scores if baseline is not None else None
            ),
            "uniqueScoreReductionPercentVsPhase10": (
                (baseline["uniqueScores"] - unique_scores) / baseline["uniqueScores"]
                if baseline is not None and baseline["uniqueScores"]
                else None
            ),
        })

    if not all_matched:
        failures = [row for row in rows if not row["matchedFrozenThresholds"]]
        raise RuntimeError(f"fused threshold parity failed: {failures}")
    if max_resident_quantities > maximum_resident:
        raise RuntimeError(
            f"fused streaming retained {max_resident_quantities} shared quantities; expected <= {maximum_resident}"
        )
    if any(row["scoreCacheEvictions"] != 0 for row in rows):
        raise RuntimeError("fused search unexpectedly reported score-cache evictions")

    return {
        "allEightThresholdsMatched": True,
        "productCount": len(rows),
        "products": rows,
        "totals": {
            "naiveScoreCount": total_naive_scores,
            "uniqueCandidatePricesScored": total_unique_scores,
            "scoreReuseSavings": total_reuse,
            "scoreReuseRate": total_reuse / total_naive_scores if total_naive_scores else None,
            "maximumResidentSharedQuantities": max_resident_quantities,
            "quantityConstructionCount": total_quantity_constructions,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source-snapshot-id", default=SOURCE_SNAPSHOT_ID)
    parser.add_argument(
        "--expected-source-authority-fingerprint",
        default=EXPECTED_AUTHORITY_FINGERPRINT,
    )
    parser.add_argument("--max-quantity-to-construct", type=int, default=4096)
    parser.add_argument("--enable-quantity-prefetch", action="store_true")
    args = parser.parse_args(argv)

    # Keep the validated Phase-10 cohort orchestration/source guards exactly as
    # they are; swap only its V2 dual-search class for this benchmark process.
    research_v2.DualBestOpenPriceSearch = FusedDualBestOpenPriceSearch

    sampler = _RssSampler()
    sampler.start()
    started = time.perf_counter()
    try:
        result = research_v2.run(
            get_client(),
            source_snapshot_id=args.source_snapshot_id,
            expected_source_authority_fingerprint=args.expected_source_authority_fingerprint,
            product_ids=list(FROZEN_THRESHOLDS),
            max_quantity_to_construct=args.max_quantity_to_construct,
            enable_quantity_prefetch=args.enable_quantity_prefetch,
        )
    finally:
        wall_seconds = time.perf_counter() - started
        sampler.stop()

    validation = _validate(result, maximum_resident=8 if args.enable_quantity_prefetch else 1)
    payload = {
        "phase": "BEST_OPEN_PRICE_V2_PHASE10B_FUSED_STREAMING",
        "readOnly": True,
        "sourceSnapshotId": args.source_snapshot_id,
        "expectedAuthorityFingerprint": args.expected_source_authority_fingerprint,
        "profiling": {
            "wallSeconds": wall_seconds,
            "peakRssBytes": sampler.peak_rss_bytes,
        },
        "validation": validation,
        "engineResult": result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "profiling": payload["profiling"],
        "allEightThresholdsMatched": validation["allEightThresholdsMatched"],
        "totals": validation["totals"],
        "products": [{
            "sealedProductId": row["sealedProductId"],
            "ripCents": row["actualRipCents"],
            "financialCents": row["actualFinancialCents"],
            "uniqueScores": row["uniqueCandidatePricesScored"],
            "baselineUniqueScores": (
                row["phase10Baseline"]["uniqueScores"] if row["phase10Baseline"] else None
            ),
            "scoreReductionPercent": row["uniqueScoreReductionPercentVsPhase10"],
            "uniqueQuantities": row["uniqueQuantitiesConstructed"],
            "quantityConstructions": row["quantityConstructionCount"],
            "maxResidentQuantities": row["maximumResidentSharedQuantities"],
        } for row in validation["products"]],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
