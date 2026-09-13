"""Read-only Bucket-1 prepared-scorer parity and exact-search study."""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.calculations.evr.best_open_price import (
    BEST_OPEN_PRICE_METHOD_VERSION,
    ExactBestOpenPriceSearch,
    PreparedCanonicalCandidate,
)
from backend.calculations.evr.budget_normalized_product_ranking import (
    SORT_AUTHORITY_V12,
    build_budget_strategy_values,
    rank_budget_cohort,
)
from backend.calculations.evr.financial_rip_v3 import (
    PreparedFinancialRipDistribution,
    build_financial_rip_v3,
)
from backend.calculations.evr.financial_rip_v4 import project_financial_rip_v4_from_v3_payload
from backend.desirability.weighted_rip import compute_overall_rip_v12
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.scripts.build_budget_normalized_product_rankings import build_stage1_distributions_cached
from backend.scripts.pokemon_snapshot_builders import get_client
from backend.scripts.research_best_open_price_bucket0 import (
    _comparator_row,
    _competitor,
    _historical_authority,
    _load_exact_source_products,
    _load_source,
    _representative_sample,
    _verify_v12_parity,
)

SOURCE_SNAPSHOT_ID = "c8853793-a2ac-4a62-a9a4-f5df7f9ed8a1"
EXPECTED_AUTHORITY_FINGERPRINT = "5d12b32481819807989c597c50b0fbf49e2086dde5cf2fe943555d49b6cd3620"


def _payload_equivalent(left: Any, right: Any, *, tolerance: float = 1e-6) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= tolerance
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _payload_equivalent(left[key], right[key], tolerance=tolerance) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _payload_equivalent(a, b, tolerance=tolerance) for a, b in zip(left, right)
        )
    return left == right


def _assert_scoring_payload_parity(current: Mapping[str, Any], prepared: Mapping[str, Any], context: str) -> None:
    exact_paths = (
        ("status",), ("statusReason",), ("rankable",), ("score",),
        ("audit", "normalizedInputs"),
    )
    for path in exact_paths:
        left: Any = current
        right: Any = prepared
        for key in path:
            left, right = left.get(key), right.get(key)
        if left != right:
            raise RuntimeError(f"prepared scoring parity mismatch at {'.'.join(path)} for {context}")
    for component, left in (current.get("components") or {}).items():
        right = (prepared.get("components") or {}).get(component) or {}
        for key in ("score", "weight", "contribution", "available", "subScores"):
            if left.get(key) != right.get(key):
                raise RuntimeError(f"prepared component parity mismatch at {component}.{key} for {context}")
    if not _payload_equivalent(current, prepared):
        raise RuntimeError(f"prepared disclosure parity exceeds 1e-6 for {context}")


def _assert_v4_parity(current: Mapping[str, Any], prepared: Mapping[str, Any], context: str) -> None:
    for key in ("score", "status", "statusReason", "rankable", "scoreVersion"):
        if current.get(key) != prepared.get(key):
            raise RuntimeError(f"prepared V4 parity mismatch at {key} for {context}")
    for component, left in (current.get("components") or {}).items():
        right = (prepared.get("components") or {}).get(component) or {}
        for key in ("score", "weight", "contribution", "available", "subScores"):
            if left.get(key) != right.get(key):
                raise RuntimeError(f"prepared V4 component mismatch at {component}.{key} for {context}")
    if not _payload_equivalent(current, prepared):
        raise RuntimeError(f"prepared V4 disclosure parity exceeds 1e-6 for {context}")


def _candidate_row(pid: str, budget: float, capital: float, v3: Mapping[str, Any],
                   v4: Mapping[str, Any], v12: Mapping[str, Any]) -> dict[str, Any]:
    raw = {key: record.get("raw") for key, record in
           ((v3.get("audit") or {}).get("normalizedInputs") or {}).items()}
    return {"sealedProductId": pid, "targetBudget": budget,
            "actualCommittedCapital": capital, "financialRipV4Score": v4.get("score"),
            "overallRipV12Score": v12.get("score"),
            "overallRipV12Rankable": bool(v12.get("rankable")),
            "chanceToRecoverCapital": raw.get("true_win_probability")}


def _assert_parity(pid: str, values: Any, prepared: PreparedFinancialRipDistribution,
                   cost: float, collector: float, raw_accessibility: Any,
                   benchmark: Mapping[str, Any], budget: float) -> None:
    current = build_financial_rip_v3(values, cost)
    fast = prepared.score(cost)
    _assert_scoring_payload_parity(current, fast, f"{pid} at {cost}")
    current_v4 = project_financial_rip_v4_from_v3_payload(current)
    fast_v4 = project_financial_rip_v4_from_v3_payload(fast)
    _assert_v4_parity(current_v4, fast_v4, f"{pid} at {cost}")
    current_v12 = compute_overall_rip_v12(current_v4.get("score"), raw_accessibility, collector)
    fast_v12 = compute_overall_rip_v12(fast_v4.get("score"), raw_accessibility, collector)
    if current_v12 != fast_v12:
        raise RuntimeError(f"prepared V12 parity mismatch for {pid} at {cost}")
    current_rank = rank_budget_cohort(
        [_candidate_row(pid, budget, cost, current, current_v4, current_v12), dict(benchmark)],
        sort_authority=SORT_AUTHORITY_V12,
    )
    fast_rank = rank_budget_cohort(
        [_candidate_row(pid, budget, cost, fast, fast_v4, fast_v12), dict(benchmark)],
        sort_authority=SORT_AUTHORITY_V12,
    )
    if current_rank != fast_rank:
        raise RuntimeError(f"prepared comparator parity mismatch for {pid} at {cost}")


def run(bucket0_artifact: Path) -> dict[str, Any]:
    client = get_client()
    started = time.perf_counter()
    tracemalloc.start()
    snapshot, source_rows, all_rows = _load_source(client, SOURCE_SNAPSHOT_ID)
    authority = _historical_authority(snapshot, source_rows)
    if authority["fingerprint"] != EXPECTED_AUTHORITY_FINGERPRINT:
        raise RuntimeError("Bucket 1 source-authority fingerprint mismatch")
    snapshot_parity = _verify_v12_parity(all_rows, label="whole snapshot")
    full_parity = _verify_v12_parity(source_rows, label="Full Market")
    products = _load_exact_source_products(client, source_rows, str(snapshot["pinned_price_as_of"]))
    product_by_id = {str(p["sealed_product_id"]): p for p in products}
    source_by_id = {str(r["sealed_product_id"]): r for r in source_rows}
    bucket0 = json.loads(bucket0_artifact.read_text(encoding="utf-8"))
    if bucket0["source"]["historicalSourceAuthorityFingerprint"] != authority["fingerprint"]:
        raise RuntimeError("Bucket 0 artifact authority does not match Bucket 1")

    artifact_cache: dict[str, Any] = {}
    base_cache: dict[tuple[str, int], Any] = {}
    strategy_values: dict[tuple[str, int], Any] = {}
    prepared_cache: dict[tuple[str, int], PreparedFinancialRipDistribution] = {}
    construction_seconds = preparation_seconds = raw_seconds = prepared_seconds = published_parity_seconds = 0.0
    published_checked = bounded_distributions = price_checks = comparator_checks = 0
    budget = float(snapshot["full_market_budget"])

    def values_and_prepared(pid: str, q: int):
        nonlocal construction_seconds, preparation_seconds
        key = (pid, q)
        if key in strategy_values:
            return strategy_values[key], prepared_cache[key]
        product = product_by_id[pid]
        run_id = str(product["calculation_run_id"])
        if run_id not in artifact_cache:
            artifact_cache[run_id] = load_pack_outcome_artifact(client, run_id)
        base_key = (run_id, int(product.get("random_pack_count") or product["pack_count"]))
        if base_key not in base_cache:
            base_cache[base_key] = build_stage1_distributions_cached(
                artifact_cache[run_id], base_key[1], run_id
            )
        t = time.perf_counter()
        random_values = build_budget_strategy_values(
            base_random_pack_values=base_cache[base_key], quantity=q,
            guaranteed_component_market_value=None, canonical_set_key=f"budget:{pid}",
            run_fingerprint=None,
        )
        construction_seconds += time.perf_counter() - t
        guaranteed = float(product.get("guaranteed_component_market_value") or 0) * q
        t = time.perf_counter()
        prepared = PreparedFinancialRipDistribution.prepare(random_values, value_offset=guaranteed)
        preparation_seconds += time.perf_counter() - t
        # Materialization exists only for the reference parity oracle, never the prepared search.
        values = random_values + guaranteed if guaranteed else random_values
        strategy_values[key], prepared_cache[key] = values, prepared
        return values, prepared

    for block in bucket0["products"]:
        pid = str(block["sealedProductId"])
        source = source_by_id[pid]
        product = product_by_id[pid]
        benchmark = _comparator_row(_competitor(source, source_rows), budget)
        collector = float(product["collector_appeal_score"])
        a_raw = authority["rawBySet"][str(product["set_id"])]
        q0 = int(source["quantity"])
        values, prepared = values_and_prepared(pid, q0)
        t = time.perf_counter()
        _assert_parity(pid, values, prepared, float(source["actual_committed_capital"]),
                       collector, a_raw, benchmark, budget)
        published_parity_seconds += time.perf_counter() - t
        published_v4 = project_financial_rip_v4_from_v3_payload(
            prepared.score(float(source["actual_committed_capital"]))
        )
        published_v12 = compute_overall_rip_v12(published_v4["score"], a_raw, collector)
        if published_v4["score"] != float(source["financial_rip_v4_score"]) or \
                published_v12["score"] != float(source["overall_rip_v12_score"]):
            raise RuntimeError(f"published strategy parity mismatch for {pid}")
        published_checked += 1
        for interval in block["intervals"]:
            q = int(interval["quantity"])
            values, prepared = values_and_prepared(pid, q)
            bounded_distributions += 1
            for point in interval["endpointProbes"]:
                cents = int(point["priceCents"])
                t = time.perf_counter()
                current = build_financial_rip_v3(values, q * cents / 100.0)
                raw_seconds += time.perf_counter() - t
                t = time.perf_counter()
                fast = prepared.score(q * cents / 100.0)
                prepared_seconds += time.perf_counter() - t
                _assert_scoring_payload_parity(current, fast, f"{pid}, q={q}, cents={cents}")
                cv4, fv4 = project_financial_rip_v4_from_v3_payload(current), project_financial_rip_v4_from_v3_payload(fast)
                cv12 = compute_overall_rip_v12(cv4["score"], a_raw, collector)
                fv12 = compute_overall_rip_v12(fv4["score"], a_raw, collector)
                _assert_v4_parity(cv4, fv4, f"{pid}, q={q}, cents={cents}")
                if cv12 != fv12:
                    raise RuntimeError(f"real-data V12 parity mismatch for {pid}, q={q}, cents={cents}")
                left = rank_budget_cohort([_candidate_row(pid, budget, q*cents/100,
                                                           current, cv4, cv12), dict(benchmark)], sort_authority=SORT_AUTHORITY_V12)
                right = rank_budget_cohort([_candidate_row(pid, budget, q*cents/100,
                                                            fast, fv4, fv12), dict(benchmark)], sort_authority=SORT_AUTHORITY_V12)
                if left != right:
                    raise RuntimeError(f"real-data comparator parity mismatch for {pid}, q={q}, cents={cents}")
                price_checks += 1
                comparator_checks += 1
        # Bound cohort memory: keep only the current product's strategies.
        for key in [key for key in strategy_values if key[0] == pid]:
            del strategy_values[key], prepared_cache[key]
        gc.collect()

    sample_reasons = _representative_sample(source_rows)
    guaranteed = sorted((p for p in products if float(p.get("guaranteed_component_market_value") or 0) > 0),
                        key=lambda p: int(source_by_id[str(p["sealed_product_id"])]["budget_rank_v12"]))
    if guaranteed:
        sample_reasons.setdefault(str(guaranteed[0]["sealed_product_id"]), []).append("guaranteed_component")
    sample_results = []
    budget_cents = int(round(budget * 100))
    for pid, reasons in sample_reasons.items():
        product, source = product_by_id[pid], source_by_id[pid]
        benchmark = _comparator_row(_competitor(source, source_rows), budget)
        def factory(q: int, *, _pid=pid, _product=product) -> PreparedCanonicalCandidate:
            _, prepared = values_and_prepared(_pid, q)
            del strategy_values[(_pid, q)], prepared_cache[(_pid, q)]
            return PreparedCanonicalCandidate(
                _pid, q, prepared, float(_product["collector_appeal_score"]),
                float(authority["rawBySet"][str(_product["set_id"])]), budget,
            )
        engine = ExactBestOpenPriceSearch(
            product_id=pid, budget_cents=budget_cents,
            current_price_cents=int(round(float(source["product_market_price"]) * 100)),
            current_quantity=int(source["quantity"]), current_rank=int(source["budget_rank_v12"]),
            benchmark=benchmark, prepare_quantity=factory,
            source_authority_fingerprint=authority["fingerprint"],
            expected_source_authority_fingerprint=EXPECTED_AUTHORITY_FINGERPRINT,
        )
        result = engine.search()
        result["sampleReasons"] = reasons
        if result["status"] != "exact":
            raise RuntimeError(f"representative threshold unresolved for {pid}: {result['status']}")
        threshold = result["threshold"]
        if not threshold["wins"]:
            raise RuntimeError(f"representative threshold does not win for {pid}")
        p = int(threshold["priceCents"])
        if p < budget_cents and ((engine.is_leader) or p < engine.current_price_cents):
            if engine.evaluate_price(p + 1)["wins"]:
                raise RuntimeError(f"representative threshold is not one-cent maximal for {pid}")
        sample_results.append(result)
        engine.clear()
        for key in [key for key in strategy_values if key[0] == pid]:
            del strategy_values[key], prepared_cache[key]
        gc.collect()

    end_snapshot, end_rows, _ = _load_source(client, SOURCE_SNAPSHOT_ID)
    if _historical_authority(end_snapshot, end_rows)["fingerprint"] != authority["fingerprint"]:
        raise RuntimeError("source authority changed during Bucket 1 study")
    _, traced_peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    process_memory = {"available": False}
    try:
        import psutil
        memory = psutil.Process().memory_info()
        process_memory = {"available": True, "workingSetBytes": memory.rss,
                          "peakWorkingSetBytes": getattr(memory, "peak_wset", None)}
    except (ImportError, OSError):
        pass
    return {
        "methodVersion": BEST_OPEN_PRICE_METHOD_VERSION,
        "source": {"snapshotId": SOURCE_SNAPSHOT_ID, "cohortFingerprint": snapshot["cohort_fingerprint"],
                   "historicalSourceAuthorityFingerprint": authority["fingerprint"],
                   "authorityUnchangedAtCompletion": True},
        "historicalParity": {"wholeSnapshot": snapshot_parity, "fullMarket": full_parity},
        "preparedParity": {"publishedStrategies": published_checked,
                           "boundedPhysicalDistributions": bounded_distributions,
                           "priceEvaluations": price_checks, "comparatorEvaluations": comparator_checks,
                           "mismatches": 0},
        "performance": {"quantityConstructionSeconds": construction_seconds,
                        "preparedCreationSeconds": preparation_seconds,
                        "publishedStrategyParitySeconds": published_parity_seconds,
                        "rawRepeatedScoringSeconds": raw_seconds,
                        "preparedRepeatedScoringSeconds": prepared_seconds,
                        "repeatedPriceSpeedup": raw_seconds / prepared_seconds if prepared_seconds else None,
                        "totalWallSeconds": time.perf_counter() - started,
                        "peakTracedMemoryBytes": traced_peak, "processMemoryAtCompletion": process_memory},
        "exactThresholdSample": sample_results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket0-artifact", type=Path,
                        default=Path("docs/research/best_open_price_bucket0_results.json"))
    parser.add_argument("--output", type=Path,
                        default=Path("docs/research/best_open_price_bucket1_results.json"))
    args = parser.parse_args(argv)
    result = run(args.bucket0_artifact)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "parity": result["preparedParity"],
                      "performance": result["performance"],
                      "sampleCount": len(result["exactThresholdSample"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
