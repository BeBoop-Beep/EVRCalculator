"""Phase 10C read-only full-cohort benchmark for fused Best-Open Price V2.

Runs the fused dual-threshold engine against the frozen Sep. 14 Full Market
authority and compares every RIP/Financial threshold to the completed
sequential Phase-10 artifact.  This is research-only: no persistence,
migration, publication, pointer update, or frontend write occurs here.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.calculations.evr.best_open_price_v2_fused import (
    DualBestOpenPriceSearch as FusedDualBestOpenPriceSearch,
)
from backend.scripts.pokemon_snapshot_builders import get_client
import backend.scripts.research_best_open_price_v2 as research_v2


SOURCE_SNAPSHOT_ID = "0e65fb6d-ff33-4331-99d5-d6a214ecc712"
EXPECTED_AUTHORITY_FINGERPRINT = "faad453f7d29eff1831fb2e212a13dad7d9d553536dc283af90c9bfbd53e48b0"
EXPECTED_FULL_COHORT_SIZE = 138
DEFAULT_REFERENCE = Path("logs/best_open_price_v2_phase10_sep14.json")
DEFAULT_OUTPUT = Path("logs/best_open_price_v2_phase10c_fused_full.json")


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
                self.peak_rss_bytes = (
                    rss if self.peak_rss_bytes is None else max(self.peak_rss_bytes, rss)
                )

        self._thread = threading.Thread(
            target=sample, name="best-open-v2-phase10c-rss", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)


def _engine_result(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    candidate = payload.get("engineResult")
    if isinstance(candidate, Mapping):
        return candidate
    return payload


def _products(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    engine = _engine_result(payload)
    rows = engine.get("products") or []
    if not isinstance(rows, list):
        raise RuntimeError("reference/fused payload has no product list")
    return [dict(row) for row in rows]


def _threshold_cents(row: Mapping[str, Any], axis: str) -> int | None:
    cents_key = (
        "ripBestOpenPriceCents" if axis == "rip" else "financialBestOpenPriceCents"
    )
    value = row.get(cents_key)
    if value is not None:
        return int(value)

    dollars_key = "ripBestOpenPrice" if axis == "rip" else "financialBestOpenPrice"
    value = row.get(dollars_key)
    if value is None:
        return None
    return int(round(float(value) * 100))


def _threshold_quantity(row: Mapping[str, Any], axis: str) -> int | None:
    key = "ripThresholdQuantity" if axis == "rip" else "financialThresholdQuantity"
    value = row.get(key)
    return int(value) if value is not None else None


def _benchmark_id(row: Mapping[str, Any], axis: str) -> str | None:
    key = (
        "ripBenchmarkSealedProductId"
        if axis == "rip"
        else "financialBenchmarkSealedProductId"
    )
    value = row.get(key)
    return str(value) if value is not None else None


def validate_parity(
    reference_payload: Mapping[str, Any],
    fused_payload: Mapping[str, Any],
    *,
    expected_count: int = EXPECTED_FULL_COHORT_SIZE,
) -> dict[str, Any]:
    reference_rows = _products(reference_payload)
    fused_rows = _products(fused_payload)

    reference = {str(row["sealedProductId"]): row for row in reference_rows}
    fused = {str(row["sealedProductId"]): row for row in fused_rows}

    if len(reference) != expected_count:
        raise RuntimeError(
            f"reference cohort size {len(reference)} != expected {expected_count}"
        )
    if len(fused) != expected_count:
        raise RuntimeError(
            f"fused cohort size {len(fused)} != expected {expected_count}"
        )
    if set(reference) != set(fused):
        missing = sorted(set(reference) - set(fused))
        extra = sorted(set(fused) - set(reference))
        raise RuntimeError(
            f"fused/reference cohort identity mismatch: missing={missing} extra={extra}"
        )

    rows = []
    threshold_matches = 0
    exactness_failures = []
    mismatches = []

    for product_id in sorted(reference):
        expected = reference[product_id]
        actual = fused[product_id]
        row_result: dict[str, Any] = {"sealedProductId": product_id}
        product_ok = True

        for axis in ("rip", "financial"):
            expected_cents = _threshold_cents(expected, axis)
            actual_cents = _threshold_cents(actual, axis)
            cents_match = expected_cents == actual_cents
            threshold_matches += int(cents_match)
            product_ok = product_ok and cents_match

            expected_quantity = _threshold_quantity(expected, axis)
            actual_quantity = _threshold_quantity(actual, axis)
            quantity_match = expected_quantity == actual_quantity
            product_ok = product_ok and quantity_match

            expected_benchmark = _benchmark_id(expected, axis)
            actual_benchmark = _benchmark_id(actual, axis)
            benchmark_match = expected_benchmark == actual_benchmark
            product_ok = product_ok and benchmark_match

            exactness = dict(actual.get(f"{axis}Exactness") or {})
            exact = (
                exactness.get("thresholdWins") is True
                and exactness.get("oneCentMaximal") is True
                and exactness.get("nextPriceWins") is not True
            )
            if not exact:
                exactness_failures.append(
                    {
                        "sealedProductId": product_id,
                        "axis": axis,
                        "exactness": exactness,
                    }
                )
                product_ok = False

            row_result[axis] = {
                "expectedCents": expected_cents,
                "actualCents": actual_cents,
                "thresholdMatch": cents_match,
                "expectedQuantity": expected_quantity,
                "actualQuantity": actual_quantity,
                "quantityMatch": quantity_match,
                "expectedBenchmark": expected_benchmark,
                "actualBenchmark": actual_benchmark,
                "benchmarkMatch": benchmark_match,
                "exactness": exactness,
            }

        row_result["matched"] = product_ok
        rows.append(row_result)
        if not product_ok:
            mismatches.append(row_result)

    expected_threshold_matches = expected_count * 2
    if threshold_matches != expected_threshold_matches or mismatches or exactness_failures:
        raise RuntimeError(
            "fused full-cohort parity failed: "
            f"thresholds={threshold_matches}/{expected_threshold_matches}, "
            f"mismatched_products={len(mismatches)}, "
            f"exactness_failures={len(exactness_failures)}"
        )

    return {
        "productCount": expected_count,
        "thresholdCount": expected_threshold_matches,
        "thresholdMatches": threshold_matches,
        "allThresholdsMatched": True,
        "exactnessFailures": 0,
        "mismatchedProducts": 0,
        "rows": rows,
    }


def _summarize_diagnostics(result: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics = [dict(row.get("diagnostics") or {}) for row in _products(result)]
    naive = sum(int(d.get("naiveScoreCount") or 0) for d in diagnostics)
    unique = sum(int(d.get("uniqueCandidatePricesScored") or 0) for d in diagnostics)
    reuse = sum(int(d.get("scoreReuseSavings") or 0) for d in diagnostics)
    constructions = sum(int(d.get("quantityConstructionCount") or 0) for d in diagnostics)
    unique_quantities = sum(int(d.get("uniqueQuantitiesConstructed") or 0) for d in diagnostics)
    max_resident = max(
        (int(d.get("maximumResidentSharedQuantities") or 0) for d in diagnostics),
        default=0,
    )
    evictions = sum(int(d.get("scoreCacheEvictions") or 0) for d in diagnostics)
    return {
        "naiveScoreCount": naive,
        "uniqueCandidatePricesScored": unique,
        "scoreReuseSavings": reuse,
        "scoreReuseRate": reuse / naive if naive else None,
        "quantityConstructionCount": constructions,
        "uniqueQuantitiesConstructed": unique_quantities,
        "maximumResidentSharedQuantities": max_resident,
        "scoreCacheEvictions": evictions,
    }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source-snapshot-id", default=SOURCE_SNAPSHOT_ID)
    parser.add_argument(
        "--expected-source-authority-fingerprint",
        default=EXPECTED_AUTHORITY_FINGERPRINT,
    )
    parser.add_argument("--max-quantity-to-construct", type=int, default=4096)
    parser.add_argument(
        "--self-check-reference",
        action="store_true",
        help="Run the 276-threshold parity gate against the reference artifact itself; no DB access.",
    )
    args = parser.parse_args(argv)

    reference_payload = _load_json(args.reference)

    if args.self_check_reference:
        validation = validate_parity(reference_payload, reference_payload)
        print(
            json.dumps(
                {
                    "mode": "reference-self-check",
                    "reference": str(args.reference),
                    "thresholdMatches": validation["thresholdMatches"],
                    "allThresholdsMatched": validation["allThresholdsMatched"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    research_v2.DualBestOpenPriceSearch = FusedDualBestOpenPriceSearch

    sampler = _RssSampler()
    sampler.start()
    started = time.perf_counter()
    try:
        fused_result = research_v2.run(
            get_client(),
            source_snapshot_id=args.source_snapshot_id,
            expected_source_authority_fingerprint=args.expected_source_authority_fingerprint,
            product_ids=None,
            max_quantity_to_construct=args.max_quantity_to_construct,
        )
    finally:
        wall_seconds = time.perf_counter() - started
        sampler.stop()

    validation = validate_parity(reference_payload, fused_result)
    shared_work = _summarize_diagnostics(fused_result)

    if shared_work["maximumResidentSharedQuantities"] > 1:
        raise RuntimeError(
            "fused full-cohort run violated streaming residency invariant: "
            f"{shared_work['maximumResidentSharedQuantities']}"
        )
    if shared_work["scoreCacheEvictions"] != 0:
        raise RuntimeError(
            "fused full-cohort run unexpectedly reported score-cache evictions"
        )

    payload = {
        "phase": "BEST_OPEN_PRICE_V2_PHASE10C_FUSED_FULL_BASELINE",
        "readOnly": True,
        "source": {
            "snapshotId": args.source_snapshot_id,
            "expectedAuthorityFingerprint": args.expected_source_authority_fingerprint,
            "expectedProductCount": EXPECTED_FULL_COHORT_SIZE,
            "referenceArtifact": str(args.reference),
        },
        "profiling": {
            "wallSeconds": wall_seconds,
            "peakRssBytes": sampler.peak_rss_bytes,
        },
        "validation": validation,
        "sharedWork": shared_work,
        "engineResult": fused_result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "profiling": payload["profiling"],
                "thresholdMatches": validation["thresholdMatches"],
                "allThresholdsMatched": validation["allThresholdsMatched"],
                "sharedWork": shared_work,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
