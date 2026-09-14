"""Read-only full-cohort exact Best-Open Price validation and profiling."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.calculations.evr.best_open_price import (
    BEST_OPEN_PRICE_METHOD_VERSION,
    BestOpenPriceSearchError,
    ExactBestOpenPriceSearch,
    PreparedCanonicalCandidate,
)
from backend.calculations.evr.budget_normalized_product_ranking import build_budget_strategy_values
from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.calculations.evr.sealed_product_distribution import (
    build_single_q_parity_distributions,
    single_q_parity_batch_width,
)
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.scripts.build_budget_normalized_product_rankings import (
    build_stage1_distributions_cached,
    cohort_fingerprint,
)
from backend.scripts.pokemon_snapshot_builders import get_client
from backend.scripts.research_best_open_price_bucket0 import (
    _comparator_row,
    _competitor,
    _historical_authority,
    _load_exact_source_products,
    _load_source,
)
from backend.scripts.research_best_open_price_bucket1 import (
    EXPECTED_AUTHORITY_FINGERPRINT,
    SOURCE_SNAPSHOT_ID,
)


def _memory() -> dict[str, Any]:
    try:
        import psutil
        info = psutil.Process().memory_info()
        return {"rssBytes": info.rss, "peakWorkingSetBytes": getattr(info, "peak_wset", None),
                "pagefileBytes": getattr(info, "pagefile", None),
                "peakPagefileBytes": getattr(info, "peak_pagefile", None)}
    except (ImportError, OSError):
        return {"rssBytes": None, "peakWorkingSetBytes": None,
                "pagefileBytes": None, "peakPagefileBytes": None}


def _status(current_rank: int, current_cents: int, threshold_cents: int) -> str:
    if current_rank == 1 and threshold_cents > current_cents:
        return "current_number_one_with_headroom"
    if threshold_cents == current_cents:
        return "resolved_at_market"
    if threshold_cents < current_cents:
        return "resolved_below_market"
    return "resolved_above_market"


def _percentile(values: Sequence[float], q: float) -> float | None:
    return round(float(np.percentile(values, q)), 6) if values else None


def _group_summary(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row[key])].append(row)
    return {name: {"attempted": len(items),
                   "resolved": sum(str(item["status"]).startswith("resolved") or
                                   item["status"] == "current_number_one_with_headroom" for item in items),
                   "medianPriceGapPercent": _percentile(
                       [float(item["priceGapPercent"]) for item in items
                        if item.get("priceGapPercent") is not None and item["currentBudgetRank"] != 1], 50)}
            for name, items in sorted(groups.items())}


def _cohort_analysis(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    resolved = [row for row in rows if row.get("bestOpenPrice") is not None]
    discounts = [float(row["priceGapPercent"]) for row in resolved if row["currentBudgetRank"] != 1]
    deltas = [int(row["quantityDelta"]) for row in resolved]
    status_counts = Counter(str(row["status"]) for row in rows)
    return {
        "attempted": len(rows), "resolved": len(resolved), "unresolved": len(rows) - len(resolved),
        "statusCounts": dict(sorted(status_counts.items())),
        "discountPercentiles": {"p25": _percentile(discounts, 25), "p50": _percentile(discounts, 50),
                                "p75": _percentile(discounts, 75), "largest": max(discounts) if discounts else None},
        "discountBands": {
            "under5Percent": sum(value < 0.05 for value in discounts),
            "under10Percent": sum(value < 0.10 for value in discounts),
            "under20Percent": sum(value < 0.20 for value in discounts),
            "20To40Percent": sum(0.20 <= value <= 0.40 for value in discounts),
            "over40Percent": sum(value > 0.40 for value in discounts),
        },
        "quantityDelta": {"minimum": min(deltas) if deltas else None,
                          "p25": _percentile(deltas, 25), "median": _percentile(deltas, 50),
                          "p75": _percentile(deltas, 75), "maximum": max(deltas) if deltas else None},
        "productFamily": _group_summary(rows, "productFamily"),
        "set": _group_summary(rows, "setId"),
        "rankDiscountCorrelation": (
            round(float(np.corrcoef(
                [row["currentBudgetRank"] for row in resolved if row["currentBudgetRank"] != 1], discounts
            )[0, 1]), 6) if len(discounts) > 1 else None
        ),
    }


def _write_checkpoint(path: Path, payload: Mapping[str, Any]) -> float:
    started = time.perf_counter()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return time.perf_counter() - started


def run(
    output: Path,
    *,
    quantity_batch_size: int = 0,
    reference_path: Path | None = None,
    product_ids: Sequence[str] | None = None,
    run_determinism: bool = True,
    source_snapshot_id: str = SOURCE_SNAPSHOT_ID,
    expected_source_authority_fingerprint: str | None = EXPECTED_AUTHORITY_FINGERPRINT,
) -> dict[str, Any]:
    """Execute the validated exact engine against one explicit V12 Full Market source.

    Research defaults remain pinned to the original Bucket-2 authority. The
    production prepared-data wrapper supplies the CURRENT published snapshot ID
    and its freshly reconstructed source-authority fingerprint, which reuses
    the identical search/scoring implementation without carrying the historical
    Sep-8 identity into future daily publications.
    """
    total_started = time.perf_counter()
    timings = Counter()
    client = get_client()
    t = time.perf_counter()
    snapshot, source_rows, _ = _load_source(client, source_snapshot_id)
    authority = _historical_authority(snapshot, source_rows)
    expected_fingerprint = expected_source_authority_fingerprint or authority["fingerprint"]
    if authority["fingerprint"] != expected_fingerprint:
        raise RuntimeError("Bucket 2 source-authority fingerprint mismatch")
    products = _load_exact_source_products(client, source_rows, str(snapshot["pinned_price_as_of"]))
    reconstructed_cohort_fingerprint = cohort_fingerprint(products, str(snapshot["pinned_price_as_of"]))
    if reconstructed_cohort_fingerprint != str(snapshot.get("cohort_fingerprint") or ""):
        raise RuntimeError("pinned cohort fingerprint does not match the published source snapshot")
    timings["sourceAuthorityLoadingSeconds"] += time.perf_counter() - t
    baseline_memory = _memory()
    source_by_id = {str(row["sealed_product_id"]): row for row in source_rows}
    product_by_id = {str(row["sealed_product_id"]): row for row in products}
    if set(source_by_id) != set(product_by_id):
        raise RuntimeError("pinned cohort SKU identities do not exactly match Full Market rows")
    ordered = sorted(products, key=lambda row: int(source_by_id[str(row["sealed_product_id"])]["budget_rank_v12"]))
    if product_ids:
        selected = set(product_ids)
        ordered = [row for row in ordered if str(row["sealed_product_id"]) in selected]
        if len(ordered) != len(selected):
            raise RuntimeError("one or more requested product IDs are outside the authority cohort")
    budget = float(snapshot["full_market_budget"])
    budget_cents = int(round(budget * 100))
    results: list[dict[str, Any]] = []
    memory_samples: list[dict[str, Any]] = []
    optimized = quantity_batch_size > 0
    reference_rows = {}
    if reference_path is not None:
        reference_payload = json.loads(reference_path.read_text(encoding="utf-8"))
        reference_rows = {row["sealedProductId"]: row for row in reference_payload["products"]}
    if output.exists():
        checkpoint = json.loads(output.read_text(encoding="utf-8"))
        if checkpoint.get("status") == "running":
            if checkpoint.get("sourceAuthorityFingerprint") != authority["fingerprint"]:
                raise RuntimeError("checkpoint source-authority fingerprint mismatch")
            if bool(checkpoint.get("optimized")) != optimized:
                raise RuntimeError("checkpoint construction mode mismatch")
            results = list(checkpoint.get("products") or [])
            for index, row in enumerate(results, 1):
                row_timing = row.get("timings") or {}
                for key, field in (
                    ("packArtifactLoadingSeconds", "artifactSeconds"),
                    ("baseDistributionConstructionSeconds", "baseSeconds"),
                    ("quantityDistributionConstructionSeconds", "quantityConstructionSeconds"),
                    ("preparedScorerConstructionSeconds", "preparedConstructionSeconds"),
                    ("candidatePriceScoringSeconds", "candidateScoringSeconds"),
                    ("comparatorSeconds", "comparatorSeconds"),
                    ("exactnessVerificationSeconds", "exactnessVerificationSeconds"),
                    ("cleanupSeconds", "cleanupSeconds"),
                ):
                    timings[key] += float(row_timing.get(field) or 0)
                memory_samples.append({"index": index, "productId": row["sealedProductId"],
                                       "beforeRssBytes": row["memory"]["before"]["rssBytes"],
                                       "peakBoundaryRssBytes": row["memory"]["peakBoundary"]["rssBytes"],
                                       "afterCleanupRssBytes": row["memory"]["afterCleanup"]["rssBytes"]})

    def execute_product(product: Mapping[str, Any], *, deterministic_replay: bool = False) -> dict[str, Any]:
        pid = str(product["sealed_product_id"])
        source = source_by_id[pid]
        competitor = _competitor(source, source_rows)
        benchmark = _comparator_row(competitor, budget)
        run_id = str(product["calculation_run_id"])
        before = _memory()
        t = time.perf_counter()
        artifact_error = None
        for attempt in range(3):
            try:
                artifact = load_pack_outcome_artifact(client, run_id)
                artifact_error = None
                break
            except Exception as exc:  # bounded retry; final exception remains fail-closed
                artifact_error = exc
                if attempt < 2:
                    time.sleep(attempt + 1)
        if artifact_error is not None:
            raise artifact_error
        artifact_seconds = time.perf_counter() - t
        t = time.perf_counter()
        random_count = int(product.get("random_pack_count") or product["pack_count"])
        base = build_stage1_distributions_cached(artifact, random_count, run_id)
        base_seconds = time.perf_counter() - t
        effective_batch_size = (
            single_q_parity_batch_width(
                len(base), requested_width=quantity_batch_size, maximum_quantity=4096,
            ) if optimized else 1
        )
        construction_seconds = 0.0
        preparation_seconds = 0.0
        batch_effective_draws = 0
        batch_legacy_draws = 0
        batch_estimated_peak_bytes = 0
        batch_count = 0

        def factory(quantity: int) -> PreparedCanonicalCandidate:
            nonlocal construction_seconds, preparation_seconds
            started = time.perf_counter()
            random_values = build_budget_strategy_values(
                base_random_pack_values=base, quantity=quantity,
                guaranteed_component_market_value=None,
                canonical_set_key=f"budget:{pid}", run_fingerprint=None,
            )
            construction_seconds += time.perf_counter() - started
            started = time.perf_counter()
            prepared = PreparedFinancialRipDistribution.prepare(
                random_values,
                value_offset=float(product.get("guaranteed_component_market_value") or 0) * quantity,
            )
            preparation_seconds += time.perf_counter() - started
            return PreparedCanonicalCandidate(
                pid, quantity, prepared, float(product["collector_appeal_score"]),
                float(authority["rawBySet"][str(product["set_id"])]), budget,
            )

        def batch_factory(quantities: Sequence[int]) -> Mapping[int, PreparedCanonicalCandidate]:
            nonlocal construction_seconds, preparation_seconds
            nonlocal batch_effective_draws, batch_legacy_draws
            nonlocal batch_estimated_peak_bytes, batch_count
            started = time.perf_counter()
            built = build_single_q_parity_distributions(
                base, quantities=quantities, canonical_set_key=f"budget:{pid}",
                run_fingerprint=None,
            )
            construction_seconds += time.perf_counter() - started
            meta = built["meta"]
            batch_effective_draws += int(meta["effectiveRngDraws"])
            batch_legacy_draws += int(meta["legacyEquivalentRngDraws"])
            batch_estimated_peak_bytes = max(
                batch_estimated_peak_bytes, int(meta["estimatedPeakConstructionBytes"])
            )
            batch_count += 1
            prepared_batch = {}
            values_by_quantity = built["distributions"]
            for quantity in quantities:
                values = values_by_quantity.pop(quantity)
                started = time.perf_counter()
                prepared = PreparedFinancialRipDistribution.prepare(
                    values,
                    value_offset=float(product.get("guaranteed_component_market_value") or 0) * quantity,
                )
                preparation_seconds += time.perf_counter() - started
                prepared_batch[quantity] = PreparedCanonicalCandidate(
                    pid, quantity, prepared, float(product["collector_appeal_score"]),
                    float(authority["rawBySet"][str(product["set_id"])]), budget,
                )
            return prepared_batch

        engine = ExactBestOpenPriceSearch(
            product_id=pid, budget_cents=budget_cents,
            current_price_cents=int(round(float(source["product_market_price"]) * 100)),
            current_quantity=int(source["quantity"]), current_rank=int(source["budget_rank_v12"]),
            benchmark=benchmark, prepare_quantity=factory,
            source_authority_fingerprint=authority["fingerprint"],
            expected_source_authority_fingerprint=expected_fingerprint,
            prepare_quantities=batch_factory if optimized else None,
            quantity_batch_size=effective_batch_size,
        )
        search_started = time.perf_counter()
        try:
            searched = engine.search()
            search_error = None
        except BestOpenPriceSearchError as exc:
            searched = engine._payload("unresolved_search_invariant", None, search_started)
            search_error = str(exc)
        search_seconds = time.perf_counter() - search_started
        peak = _memory()
        threshold = searched.get("threshold")
        current_cents = engine.current_price_cents
        current_rank = engine.current_rank
        if threshold:
            threshold_cents = int(threshold["priceCents"])
            status = _status(current_rank, current_cents, threshold_cents)
            gap_dollars = (current_cents - threshold_cents) / 100.0
            gap_percent = (current_cents - threshold_cents) / current_cents
            threshold_quantity = int(threshold["quantity"])
        else:
            threshold_cents = None
            status = searched["status"]
            gap_dollars = gap_percent = threshold_quantity = None
        if threshold and budget_cents // threshold_cents != threshold_quantity:
            raise RuntimeError(f"threshold quantity mismatch for {pid}")
        if current_rank != 1 and threshold_cents is not None and threshold_cents > current_cents:
            raise RuntimeError(f"non-leader threshold above market for {pid}")
        cleanup_started = time.perf_counter()
        engine.clear()
        del engine, base, artifact
        gc.collect()
        cleanup_seconds = time.perf_counter() - cleanup_started
        after = _memory()
        if not deterministic_replay:
            timings["packArtifactLoadingSeconds"] += artifact_seconds
            timings["baseDistributionConstructionSeconds"] += base_seconds
            timings["quantityDistributionConstructionSeconds"] += construction_seconds
            timings["preparedScorerConstructionSeconds"] += preparation_seconds
            timings["candidatePriceScoringSeconds"] += float(searched.get("candidateScoringSeconds") or 0)
            timings["comparatorSeconds"] += float(searched.get("comparatorSeconds") or 0)
            timings["exactnessVerificationSeconds"] += float(searched.get("exactnessVerificationSeconds") or 0)
            timings["cleanupSeconds"] += cleanup_seconds
        row = {
            "sealedProductId": pid, "productName": product.get("product_name"),
            "setId": str(product["set_id"]), "productFamily": product.get("product_family"),
            "sourceCalculationRunId": run_id,
            "currentMarketPrice": current_cents / 100.0,
            "currentBudgetRank": current_rank,
            "currentOverallRipV12Score": float(source["overall_rip_v12_score"]),
            "currentFinancialRipV4Score": source.get("financial_rip_v4_score"),
            "currentCollectorAppealScore": source.get("collector_appeal_score"),
            "currentChaseAccessibilityRaw": source.get("chase_accessibility_raw"),
            "currentChanceToRecoverCapital": source.get("chance_to_recover_capital"),
            "currentActualCommittedCapital": source.get("actual_committed_capital"),
            "bestOpenPrice": threshold_cents / 100.0 if threshold_cents is not None else None,
            "bestOpenPriceCents": threshold_cents, "status": status,
            "priceGapDollars": gap_dollars, "priceGapPercent": gap_percent,
            "priceGapInterpretation": "leader_headroom" if int(source["budget_rank_v12"]) == 1 else "required_discount",
            "currentQuantity": int(source["quantity"]), "thresholdQuantity": threshold_quantity,
            "quantityDelta": threshold_quantity - int(source["quantity"]) if threshold_quantity is not None else None,
            "thresholdActualCommittedCapital": threshold.get("actualCommittedCapital") if threshold else None,
            "thresholdFinancialRipV4Score": threshold.get("financialRipV4Score") if threshold else None,
            "thresholdOverallRipV12Score": threshold.get("overallRipV12Score") if threshold else None,
            "thresholdChanceToRecoverCapital": threshold.get("chanceToRecoverCapital") if threshold else None,
            "benchmarkSealedProductId": str(competitor["sealed_product_id"]),
            "benchmarkProductName": product_by_id[str(competitor["sealed_product_id"])].get("product_name"),
            "benchmarkOverallRipV12Score": float(competitor["overall_rip_v12_score"]),
            "benchmarkFinancialRipV4Score": competitor.get("financial_rip_v4_score"),
            "benchmarkChanceToRecoverCapital": competitor.get("chance_to_recover_capital"),
            "benchmarkActualCommittedCapital": competitor.get("actual_committed_capital"),
            "quantitiesConstructed": searched.get("physicalQuantitiesConstructed", []),
            "candidatePriceEvaluations": searched.get("evaluationCount", 0),
            "bracketExpansions": searched.get("bracketExpansions", 0),
            "bracketRefinements": searched.get("bracketRefinements", 0),
            "fallbackCount": searched.get("monotonicityFallbackCount", 0),
            "minimumQuantityInspected": searched.get("minimumQuantityInspected"),
            "maximumQuantityInspected": searched.get("maximumQuantityInspected"),
            "lowestCandidatePriceReached": ((searched.get("lowestCandidatePriceCents") or 0) / 100.0
                                             if searched.get("lowestCandidatePriceCents") else None),
            "quantityCacheHits": searched.get("quantityCacheHits", 0),
            "quantityCacheMisses": searched.get("quantityCacheMisses", 0),
            "quantityCacheEvictions": searched.get("quantityCacheEvictions", 0),
            "maximumResidentLargeDistributions": searched.get("maximumResidentQuantities", 0),
            "quantityBatchBuilds": searched.get("quantityBatchBuilds", 0),
            "quantityBatchQuantities": searched.get("quantityBatchQuantities", 0),
            "quantityBatchFallbacks": searched.get("quantityBatchFallbacks", 0),
            "maximumPendingBatchCandidates": searched.get("maximumPendingBatchCandidates", 0),
            "batchEffectiveRngDraws": batch_effective_draws,
            "batchLegacyEquivalentRngDraws": batch_legacy_draws,
            "batchEstimatedPeakConstructionBytes": batch_estimated_peak_bytes,
            "batchFactoryCalls": batch_count,
            "effectiveQuantityBatchSize": effective_batch_size,
            "exactness": searched.get("exactness"), "searchError": search_error,
            "searchWallSeconds": search_seconds,
            "timings": {"artifactSeconds": artifact_seconds, "baseSeconds": base_seconds,
                        "quantityConstructionSeconds": construction_seconds,
                        "preparedConstructionSeconds": preparation_seconds,
                        "candidateScoringSeconds": searched.get("candidateScoringSeconds", 0),
                        "comparatorSeconds": searched.get("comparatorSeconds", 0),
                        "exactnessVerificationSeconds": searched.get("exactnessVerificationSeconds", 0),
                        "cleanupSeconds": cleanup_seconds},
            "memory": {"before": before, "peakBoundary": peak, "afterCleanup": after},
        }
        if reference_rows:
            reference = reference_rows.get(pid)
            if reference is None:
                raise RuntimeError(f"Bucket 2 reference row missing for {pid}")
            parity_fields = (
                "status", "bestOpenPriceCents", "thresholdQuantity",
                "benchmarkSealedProductId",
            )
            mismatches = [field for field in parity_fields if row.get(field) != reference.get(field)]
            if row.get("exactness") != reference.get("exactness"):
                mismatches.append("exactness")
            if mismatches:
                raise RuntimeError(f"Bucket 2 reference mismatch for {pid}: {mismatches}")
            row["bucket2ReferenceParity"] = True
        return row

    completed_ids = {row["sealedProductId"] for row in results}
    for index, product in enumerate(ordered, 1):
        if str(product["sealed_product_id"]) in completed_ids:
            continue
        row = execute_product(product)
        results.append(row)
        memory_samples.append({"index": index, "productId": row["sealedProductId"],
                               "beforeRssBytes": row["memory"]["before"]["rssBytes"],
                               "peakBoundaryRssBytes": row["memory"]["peakBoundary"]["rssBytes"],
                               "afterCleanupRssBytes": row["memory"]["afterCleanup"]["rssBytes"]})
        checkpoint = {"status": "running", "completed": index, "total": len(ordered),
                      "optimized": optimized, "quantityBatchSize": quantity_batch_size,
                      "sourceAuthorityFingerprint": authority["fingerprint"], "products": results}
        timings["artifactSerializationSeconds"] += _write_checkpoint(output, checkpoint)
        print(json.dumps({"completed": index, "rank": row["currentBudgetRank"], "status": row["status"],
                          "seconds": round(row["searchWallSeconds"], 3),
                          "maxQ": row["maximumQuantityInspected"]}), flush=True)

    # Deterministic subset: leader, fastest, slowest, high-q, guaranteed, hash-selected.
    subset_ids = []
    if run_determinism:
        full_results = sorted(results, key=lambda row: row["currentBudgetRank"])
        fastest = min(results, key=lambda row: row["searchWallSeconds"])
        slowest = max(results, key=lambda row: row["searchWallSeconds"])
        high_q = max(results, key=lambda row: row["currentQuantity"])
        guaranteed = next((row for row in results if float(product_by_id[row["sealedProductId"]].get(
            "guaranteed_component_market_value") or 0) > 0), full_results[0])
        random_row = min(results, key=lambda row: hashlib.sha256(row["sealedProductId"].encode()).hexdigest())
        subset_ids = list(dict.fromkeys([full_results[0]["sealedProductId"], fastest["sealedProductId"],
                                         slowest["sealedProductId"], high_q["sealedProductId"],
                                         guaranteed["sealedProductId"], random_row["sealedProductId"]]))
    deterministic = []
    deterministic_keys = ("bestOpenPriceCents", "status", "thresholdQuantity",
                          "thresholdFinancialRipV4Score", "thresholdOverallRipV12Score",
                          "thresholdChanceToRecoverCapital", "benchmarkSealedProductId")
    for pid in subset_ids:
        replay = execute_product(product_by_id[pid], deterministic_replay=True)
        original = next(row for row in results if row["sealedProductId"] == pid)
        matches = all(replay.get(key) == original.get(key) for key in deterministic_keys)
        if not matches:
            raise RuntimeError(f"deterministic replay mismatch for {pid}")
        deterministic.append({"sealedProductId": pid, "matches": True,
                              "originalSeconds": original["searchWallSeconds"],
                              "replaySeconds": replay["searchWallSeconds"]})

    end_snapshot, end_rows, _ = _load_source(client, source_snapshot_id)
    end_authority = _historical_authority(end_snapshot, end_rows)
    if end_authority["fingerprint"] != authority["fingerprint"]:
        raise RuntimeError("Bucket 2 source authority changed during execution")
    analysis = _cohort_analysis(results)
    final_memory = _memory()
    total_seconds = time.perf_counter() - total_started
    timing_payload = dict(timings)
    timing_payload["totalWallSeconds"] = total_seconds
    timing_payload["phasePercentOfWall"] = {
        key: round(value * 100.0 / total_seconds, 4) for key, value in timings.items()
    }
    after_values = [sample["afterCleanupRssBytes"] for sample in memory_samples if sample["afterCleanupRssBytes"]]
    memory_payload = {
        "baselineAfterAuthorityLoad": baseline_memory,
        "cohortPeakWorkingSetBytes": final_memory["peakWorkingSetBytes"],
        "finalAfterCleanup": final_memory,
        "productBoundarySamples": memory_samples,
        "afterCleanupFirstQuartileMedianBytes": _percentile(after_values[:max(1, len(after_values)//4)], 50),
        "afterCleanupLastQuartileMedianBytes": _percentile(after_values[-max(1, len(after_values)//4):], 50),
    }
    payload = {
        "status": "complete", "methodVersion": BEST_OPEN_PRICE_METHOD_VERSION,
        "constructionMode": ("independent_single_q_flat_stream_batch_v1" if optimized else "legacy_single_q"),
        "quantityBatchSize": quantity_batch_size,
        "source": {"snapshotId": source_snapshot_id, "cohortFingerprint": snapshot["cohort_fingerprint"],
                   "historicalSourceAuthorityFingerprint": authority["fingerprint"],
                   "authorityUnchangedAtCompletion": True, "fullMarketBudget": budget},
        "products": results, "cohortAnalysis": analysis, "timings": timing_payload,
        "memory": memory_payload,
        "lru": {"insertions": sum(row["quantityCacheMisses"] for row in results),
                "hits": sum(row["quantityCacheHits"] for row in results),
                "misses": sum(row["quantityCacheMisses"] for row in results),
                "evictions": sum(row["quantityCacheEvictions"] for row in results),
                "maximumResidentLargeDistributions": max(row["maximumResidentLargeDistributions"] for row in results)},
        "determinism": {"subsetCount": len(deterministic), "allMatched": True, "rows": deterministic},
        "bucket2ReferenceParity": {
            "required": bool(reference_rows),
            "matched": sum(row.get("bucket2ReferenceParity") is True for row in results),
            "total": len(results),
        },
    }
    timings["artifactSerializationSeconds"] += _write_checkpoint(output, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path("docs/research/best_open_price_bucket2_results.json"))
    parser.add_argument("--quantity-batch-size", type=int, default=0)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--only-product-id", action="append")
    parser.add_argument("--skip-determinism", action="store_true")
    parser.add_argument("--source-snapshot-id", default=SOURCE_SNAPSHOT_ID)
    parser.add_argument("--expected-source-authority-fingerprint")
    args = parser.parse_args(argv)
    expected = args.expected_source_authority_fingerprint
    if args.source_snapshot_id == SOURCE_SNAPSHOT_ID and expected is None:
        expected = EXPECTED_AUTHORITY_FINGERPRINT
    result = run(
        args.output,
        quantity_batch_size=args.quantity_batch_size,
        reference_path=args.reference,
        product_ids=args.only_product_id,
        run_determinism=not args.skip_determinism,
        source_snapshot_id=args.source_snapshot_id,
        expected_source_authority_fingerprint=expected,
    )
    print(json.dumps({"output": str(args.output), "analysis": result["cohortAnalysis"],
                      "timings": result["timings"], "lru": result["lru"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
