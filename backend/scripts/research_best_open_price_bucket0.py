"""Read-only Bucket-0 harness for Best-Open Price research.

This deliberately does not publish and does not claim to calculate production
thresholds. It pins one published Full Market snapshot, reconstructs bounded
candidate strategies through the canonical V3 -> V4 -> V12 chain, and measures
the work that a threshold engine must perform. Products that do not win in the
bounded probes are reported as unresolved, never assigned a fabricated floor.

Example:
    python -m backend.scripts.research_best_open_price_bucket0 \
      --snapshot-id c8853793-a2ac-4a62-a9a4-f5df7f9ed8a1 \
      --product-limit 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
import tracemalloc
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.calculations.evr.budget_normalized_product_ranking import (
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
    SORT_AUTHORITY_V12,
    build_budget_strategy_values,
    rank_budget_cohort,
    rank_by_financial_only,
    score_budget_strategy,
)
from backend.db.services.budget_product_ranking_authority import (
    EXPECTED_CHASE_ACCESSIBILITY_TRANSFORM_VERSION,
    EXPECTED_CHASE_ACCESSIBILITY_VERSION,
    EXPECTED_OVERALL_RIP_V12_VERSION,
    _fetch_all_ready_rows,
)
from backend.desirability.weighted_rip import compute_overall_rip_v12
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.scripts.build_budget_normalized_product_rankings import cohort_fingerprint
from backend.scripts.pokemon_snapshot_builders import get_client

METHOD_VERSION = "budget_product_best_open_price_full_market_v1_research"
_PAGE_SIZE = 1000


def quantity_price_interval_cents(budget_cents: int, quantity: int) -> tuple[int, int]:
    """Exact inclusive cent interval where floor(B/P) equals ``quantity``."""
    if budget_cents < 1 or quantity < 1:
        raise ValueError("budget_cents and quantity must be positive")
    low = budget_cents // (quantity + 1) + 1
    high = budget_cents // quantity
    return low, high


def interval_probe_cents(low: int, high: int) -> list[int]:
    """Five deterministic, deduplicated cent probes spanning an interval."""
    if low < 1 or high < low:
        raise ValueError("invalid cent interval")
    width = high - low
    return sorted({low, low + round(width * 0.25), low + round(width * 0.5),
                   low + round(width * 0.75), high})


def _rows(response: Any) -> list[dict[str, Any]]:
    return list((response.data if response else []) or [])


def _fetch_source_rows(client: Any, snapshot_id: str) -> list[dict[str, Any]]:
    """Read every row even when a snapshot is exactly at PostgREST's page cap."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        query = (
            client.table("budget_product_ranking_rows").select("*")
            .eq("snapshot_id", snapshot_id).order("sealed_product_id")
            .order("target_budget").order("budget_type")
        )
        range_query = getattr(query, "range", None)
        page = _rows(query.range(offset, offset + _PAGE_SIZE - 1).execute()) if range_query else _rows(query.execute())
        rows.extend(page)
        if range_query is None or len(page) < _PAGE_SIZE:
            return rows
        offset += _PAGE_SIZE


def _load_source(client: Any, snapshot_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    snapshots = _rows(client.table("budget_product_ranking_snapshots").select("*").eq("id", snapshot_id).limit(1).execute())
    if not snapshots:
        raise RuntimeError(f"published source snapshot {snapshot_id} does not exist")
    snapshot = snapshots[0]
    if not snapshot.get("ranked_under_v12_authority"):
        raise RuntimeError("source snapshot is not explicitly ranked under V12 authority")
    if snapshot.get("overall_rip_version") != EXPECTED_OVERALL_RIP_V12_VERSION:
        raise RuntimeError("source snapshot Overall RIP authority is incompatible with Best-Open Price V1")
    if snapshot.get("overall_rip_v12_version") != EXPECTED_OVERALL_RIP_V12_VERSION:
        raise RuntimeError("source snapshot explicit Overall RIP V12 identity is incompatible")
    if snapshot.get("chase_accessibility_version") != EXPECTED_CHASE_ACCESSIBILITY_VERSION:
        raise RuntimeError("source snapshot Chase Accessibility identity is incompatible")
    if snapshot.get("chase_accessibility_transform_version") != EXPECTED_CHASE_ACCESSIBILITY_TRANSFORM_VERSION:
        raise RuntimeError("source snapshot Chase Accessibility transform identity is incompatible")
    if not snapshot.get("cohort_fingerprint"):
        raise RuntimeError("source snapshot has no cohort fingerprint")
    if snapshot.get("ranking_method_version") != BUDGET_NORMALIZED_RANKING_METHOD_VERSION:
        raise RuntimeError("source snapshot budget-ranking method is incompatible")
    budget = float(snapshot.get("full_market_budget") or 0)
    all_rows = _fetch_source_rows(client, snapshot_id)
    source_rows = sorted(
        (row for row in all_rows if row.get("budget_type") == "full_market" and float(row["target_budget"]) == budget),
        key=lambda row: int(row["budget_rank_v12"]),
    )
    if not source_rows:
        raise RuntimeError("source snapshot has no exact Full Market rows")
    if len(source_rows) != int(snapshot.get("eligible_cohort_count") or 0):
        raise RuntimeError("Full Market cohort count does not equal snapshot authority")
    return snapshot, source_rows, all_rows


def _decimal_text(value: Any) -> str:
    decimal = Decimal(str(value))
    return format(decimal.normalize(), "f")


def _historical_authority(snapshot: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    raw_by_set: dict[str, set[str]] = defaultdict(set)
    runs_by_set: dict[str, set[str]] = defaultdict(set)
    null_products: list[str] = []
    for row in rows:
        set_id = str(row["set_id"])
        if row.get("chase_accessibility_raw") is None:
            null_products.append(str(row["sealed_product_id"]))
        else:
            raw_by_set[set_id].add(_decimal_text(row["chase_accessibility_raw"]))
        if row.get("source_calculation_run_id") is not None:
            runs_by_set[set_id].add(str(row["source_calculation_run_id"]))
    if null_products:
        raise RuntimeError(f"{len(null_products)} Full Market products have null persisted Chase Accessibility raw input")
    set_ids = sorted({str(row["set_id"]) for row in rows})
    for set_id in set_ids:
        if len(raw_by_set[set_id]) != 1:
            raise RuntimeError(f"set {set_id} has {len(raw_by_set[set_id])} distinct persisted raw values")
        if len(runs_by_set[set_id]) != 1:
            raise RuntimeError(f"set {set_id} has {len(runs_by_set[set_id])} source calculation runs")
    tuples = [{
        "snapshotId": str(snapshot["id"]),
        "cohortFingerprint": str(snapshot["cohort_fingerprint"]),
        "setId": set_id,
        "sourceCalculationRunId": next(iter(runs_by_set[set_id])),
        "chaseAccessibilityRaw": next(iter(raw_by_set[set_id])),
        "chaseAccessibilityVersion": str(snapshot["chase_accessibility_version"]),
        "chaseAccessibilityTransformVersion": str(snapshot["chase_accessibility_transform_version"]),
        "overallRipV12Version": str(snapshot["overall_rip_v12_version"]),
    } for set_id in set_ids]
    encoded = json.dumps(tuples, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"fingerprint": hashlib.sha256(encoded).hexdigest(), "setTuples": tuples,
            "rawBySet": {key: next(iter(value)) for key, value in raw_by_set.items()}}


def _verify_v12_parity(rows: Sequence[Mapping[str, Any]], *, label: str) -> dict[str, Any]:
    mismatches = []
    reconstructed = 0
    max_delta = Decimal("0")
    for row in rows:
        required = ("financial_rip_v4_score", "collector_appeal_score", "chase_accessibility_raw", "overall_rip_v12_score")
        if any(row.get(field) is None for field in required):
            mismatches.append({"sealedProductId": str(row.get("sealed_product_id")), "reason": "missing_input"})
            continue
        result = compute_overall_rip_v12(
            row["financial_rip_v4_score"], row["chase_accessibility_raw"], row["collector_appeal_score"]
        )
        actual = Decimal(str(row["overall_rip_v12_score"]))
        expected = Decimal(str(result.get("score")))
        delta = abs(actual - expected)
        max_delta = max(max_delta, delta)
        reconstructed += 1
        if delta != 0:
            mismatches.append({"sealedProductId": str(row["sealed_product_id"]),
                               "expected": str(expected), "actual": str(actual), "delta": str(delta)})
    if mismatches:
        raise RuntimeError(f"{label} V12 parity failed for {len(mismatches)}/{len(rows)} rows: {mismatches[:3]}")
    return {"rowsChecked": len(rows), "rowsReconstructed": reconstructed,
            "mismatchCount": 0, "maximumAbsoluteDelta": str(max_delta)}


def _competitor(row: Mapping[str, Any], source_rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    ordered = sorted(source_rows, key=lambda r: int(r["budget_rank_v12"]))
    return ordered[1] if str(row["sealed_product_id"]) == str(ordered[0]["sealed_product_id"]) else ordered[0]


def _financial_competitor(row: Mapping[str, Any], source_rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Financial-only analogue of _competitor(): benchmark by financial_only_rank,
    not budget_rank_v12. The Financial and RIP benchmarks may be different products."""
    ordered = sorted(source_rows, key=lambda r: int(r["financial_only_rank"]))
    return ordered[1] if str(row["sealed_product_id"]) == str(ordered[0]["sealed_product_id"]) else ordered[0]


def validate_rank_column_contiguous(rows: Sequence[Mapping[str, Any]], column: str) -> None:
    """Fail closed unless `column` is an exact 1..N permutation over `rows`.

    Used for both budget_rank_v12 (V1's existing implicit assumption, now made
    explicit) and financial_only_rank (new for the dual engine) -- a missing,
    duplicate, or non-contiguous rank column must abort before any expensive
    search runs, not silently produce a wrong benchmark or cohort-size count.
    """
    values = []
    for row in rows:
        value = row.get(column)
        if value is None:
            raise RuntimeError(f"{column} is missing for sealed_product_id={row.get('sealed_product_id')!r}")
        values.append(int(value))
    n = len(values)
    if sorted(values) != list(range(1, n + 1)):
        raise RuntimeError(f"{column} is not a contiguous 1..N permutation over {n} rows")


def validate_financial_only_rank_reconstructs(source_rows: Sequence[Mapping[str, Any]]) -> None:
    """Fail closed unless every row's persisted financial_only_rank matches a
    fresh reconstruction via the canonical rank_by_financial_only() comparator
    over this exact cohort's financial_rip_v4_score values."""
    strategies = [
        {"sealedProductId": str(row["sealed_product_id"]), "financialRipV4Score": row.get("financial_rip_v4_score")}
        for row in source_rows
    ]
    reconstructed = {
        str(entry["sealedProductId"]): entry["financialOnlyRank"]
        for entry in rank_by_financial_only(strategies)
    }
    for row in source_rows:
        pid = str(row["sealed_product_id"])
        persisted = int(row["financial_only_rank"])
        expected = reconstructed.get(pid)
        if expected != persisted:
            raise RuntimeError(
                f"financial_only_rank does not reconstruct for {pid}: "
                f"persisted={persisted} reconstructed={expected}"
            )


def _load_exact_source_products(client: Any, source_rows: Sequence[Mapping[str, Any]], price_as_of: str) -> list[dict[str, Any]]:
    """Join mutable simulation history only by the identities persisted in the snapshot."""
    expected = {
        (str(row["sealed_product_id"]), str(row["source_calculation_run_id"])): row
        for row in source_rows
    }
    matches = [
        row for row in _fetch_all_ready_rows(client)
        if (str(row["sealed_product_id"]), str(row["calculation_run_id"])) in expected
    ]
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in matches:
        by_key.setdefault((str(row["sealed_product_id"]), str(row["calculation_run_id"])), []).append(row)
    products: list[dict[str, Any]] = []
    for key, source in expected.items():
        candidates = [r for r in by_key.get(key, []) if str(r.get("price_as_of")) == str(price_as_of)]
        if not candidates:
            raise RuntimeError(f"source identity {key} resolved to no simulation row")
        identity_fields = ("set_id", "product_family", "pack_count", "random_pack_count",
                           "guaranteed_component_market_value", "product_market_cost",
                           "collector_appeal_score", "collector_appeal_version")
        signatures = {tuple(str(r.get(field)) for field in identity_fields) for r in candidates}
        if len(signatures) != 1:
            raise RuntimeError(f"source identity {key} resolved to conflicting duplicate simulation rows")
        if not math.isclose(float(candidates[0]["product_market_cost"]), float(source["product_market_price"]), abs_tol=0.00001):
            raise RuntimeError(f"source identity {key} market price does not match its published row")
        products.append(candidates[0])
    return products


def _comparator_row(row: Mapping[str, Any], budget: float) -> dict[str, Any]:
    return {
        "sealedProductId": str(row["sealed_product_id"]),
        "overallRipV12Score": row.get("overall_rip_v12_score"),
        "overallRipV12Rankable": row.get("overall_rip_v12_rankable", True),
        "financialRipV4Score": row.get("financial_rip_v4_score"),
        "chanceToRecoverCapital": row.get("chance_to_recover_capital"),
        "actualCommittedCapital": row.get("actual_committed_capital"),
        "targetBudget": budget,
    }


def _representative_sample(source_rows: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Preregister a deterministic discontinuity sample from persisted fields."""
    ordered = sorted(source_rows, key=lambda row: int(row["budget_rank_v12"]))
    reasons: dict[str, list[str]] = defaultdict(list)
    choices = {
        "current_leader": ordered[0],
        "another_top_5": ordered[min(1, len(ordered) - 1)],
        "rank_6_20": ordered[min(9, len(ordered) - 1)],
        "middle_ranked": ordered[(len(ordered) - 1) // 2],
        "bottom_quartile": ordered[min(len(ordered) - 1, math.ceil(len(ordered) * 0.75) - 1)],
        "cheapest_highest_q": max(ordered, key=lambda row: (int(row["quantity"]), -int(row["budget_rank_v12"]))),
        "expensive_low_q": min(ordered, key=lambda row: (int(row["quantity"]), -float(row["product_market_price"]))),
    }
    # Published rows do not carry the guaranteed value; this reason is filled
    # later from exact simulation products when one exists.
    for reason, row in choices.items():
        reasons[str(row["sealed_product_id"])].append(reason)
    # Ensure several families even when rank/price selections overlap.
    seen_families = set()
    for row in ordered:
        family = str(row.get("product_family"))
        if family not in seen_families:
            reasons[str(row["sealed_product_id"])].append(f"family:{family}")
            seen_families.add(family)
        if len(seen_families) >= 4:
            break
    return dict(reasons)


def run(snapshot_id: str, *, product_limit: int, max_quantities: int = 2) -> dict[str, Any]:
    client = get_client()
    tracemalloc.start()
    total_started = time.perf_counter()
    t = time.perf_counter()
    snapshot, source_rows, all_source_rows = _load_source(client, snapshot_id)
    historical = _historical_authority(snapshot, source_rows)
    authority_seconds = time.perf_counter() - t
    t = time.perf_counter()
    all_parity = _verify_v12_parity(all_source_rows, label="whole snapshot")
    full_market_parity = _verify_v12_parity(source_rows, label="Full Market")
    parity_seconds = time.perf_counter() - t
    t = time.perf_counter()
    products = _load_exact_source_products(client, source_rows, str(snapshot["pinned_price_as_of"]))
    product_source_seconds = time.perf_counter() - t
    fingerprint = cohort_fingerprint(products, str(snapshot["pinned_price_as_of"]))
    if fingerprint != snapshot.get("cohort_fingerprint"):
        raise RuntimeError("pinned cohort fingerprint does not match the published source snapshot")

    by_id = {str(p["sealed_product_id"]): p for p in products}
    source_by_id = {str(r["sealed_product_id"]): r for r in source_rows}
    if set(by_id) != set(source_by_id):
        raise RuntimeError("pinned cohort SKU identities do not exactly match Full Market rows")
    sample_reasons = _representative_sample(source_rows)
    guaranteed_products = sorted(
        (p for p in products if float(p.get("guaranteed_component_market_value") or 0) > 0),
        key=lambda p: int(source_by_id[str(p["sealed_product_id"])]["budget_rank_v12"]),
    )
    if guaranteed_products:
        sample_reasons.setdefault(str(guaranteed_products[0]["sealed_product_id"]), []).append("guaranteed_component")
    selected = sorted(products, key=lambda p: int(source_by_id[str(p["sealed_product_id"])]["budget_rank_v12"]))
    if product_limit > 0:
        # Include both ends of the ranking while keeping deterministic size.
        selected = (selected[: max(1, product_limit - 1)] + selected[-1:])[:product_limit]
    artifact_seconds = 0.0
    artifact_cache: dict[str, Any] = {}
    base_cache: dict[tuple[str, int], Any] = {}
    per_product = []
    budget = float(snapshot["full_market_budget"])
    budget_cents = int(round(budget * 100))
    quantity_cache_hits = 0
    quantity_cache_misses = 0

    for product in selected:
        pid = str(product["sealed_product_id"])
        source = source_by_id[pid]
        benchmark = _competitor(source, source_rows)
        run_id = str(product["calculation_run_id"])
        if run_id not in artifact_cache:
            t = time.perf_counter()
            artifact_cache[run_id] = load_pack_outcome_artifact(client, run_id)
            artifact_seconds += time.perf_counter() - t
        random_count = int(product.get("random_pack_count") or product["pack_count"])
        base_key = (run_id, random_count)
        if base_key not in base_cache:
            from backend.scripts.build_budget_normalized_product_rankings import build_stage1_distributions_cached
            t = time.perf_counter()
            base_cache[base_key] = build_stage1_distributions_cached(artifact_cache[run_id], random_count, run_id)
            base_seconds = time.perf_counter() - t
        else:
            base_seconds = 0.0

        current_q = int(source["quantity"])
        quantities = {current_q, current_q + 1, current_q + 2}
        if int(source["budget_rank_v12"]) == 1:
            quantities.update({current_q - 1, current_q - 2})
        if pid in sample_reasons:
            quantities.update({current_q + 4, current_q + 8, current_q + 16})
        quantities = sorted(q for q in quantities if 1 <= q <= budget_cents)
        probes = 0
        q_seconds = financial_seconds = v12_seconds = comparator_seconds = 0.0
        winning_prices: list[int] = []
        inspected = []
        a_raw = historical["rawBySet"][str(product["set_id"])]
        for q in quantities:
            low, high = quantity_price_interval_cents(budget_cents, q)
            t = time.perf_counter()
            values = build_budget_strategy_values(
                base_random_pack_values=base_cache[base_key], quantity=q,
                guaranteed_component_market_value=product.get("guaranteed_component_market_value"),
                canonical_set_key=f"budget:{pid}", run_fingerprint=None,
            )
            q_seconds += time.perf_counter() - t
            quantity_cache_misses += 1
            endpoint_results = []
            for cents in interval_probe_cents(low, high):
                t = time.perf_counter()
                scored = score_budget_strategy(
                    values, q * cents / 100.0, product.get("collector_appeal_score")
                )
                financial_seconds += time.perf_counter() - t
                t = time.perf_counter()
                overall_v12 = compute_overall_rip_v12(
                    scored["financialRipV4Score"], a_raw, product.get("collector_appeal_score")
                )
                v12_seconds += time.perf_counter() - t
                scored["overallRipV12Score"] = overall_v12["score"]
                scored["overallRipV12Rankable"] = overall_v12["rankable"]
                candidate = {"sealedProductId": pid, "targetBudget": budget,
                    "actualCommittedCapital": q * cents / 100.0, **scored}
                t = time.perf_counter()
                ranked = rank_budget_cohort([candidate, _comparator_row(benchmark, budget)], sort_authority=SORT_AUTHORITY_V12)
                comparator_seconds += time.perf_counter() - t
                won = bool(ranked and ranked[0]["sealedProductId"] == pid)
                endpoint_results.append({"priceCents": cents, "wins": won,
                    "financialRipV4Score": scored.get("financialRipV4Score"),
                    "overallRipV12Score": scored.get("overallRipV12Score")})
                probes += 1
                if won:
                    winning_prices.append(cents)
            inspected.append({"quantity": q, "lowPriceCents": low, "highPriceCents": high,
                              "endpointProbes": endpoint_results})

        monotonicity = {"financialRipV4": 0, "overallRipV12": 0, "comparator": 0}
        for interval in inspected:
            points = interval["endpointProbes"]
            for cheaper, dearer in zip(points, points[1:]):
                if cheaper["financialRipV4Score"] < dearer["financialRipV4Score"]:
                    monotonicity["financialRipV4"] += 1
                if cheaper["overallRipV12Score"] < dearer["overallRipV12Score"]:
                    monotonicity["overallRipV12"] += 1
                if not cheaper["wins"] and dearer["wins"]:
                    monotonicity["comparator"] += 1

        per_product.append({
            "sealedProductId": pid, "setId": str(product["set_id"]),
            "currentRank": int(source["budget_rank_v12"]),
            "currentMarketPrice": float(source["product_market_price"]),
            "benchmarkSealedProductId": str(benchmark["sealed_product_id"]),
            "status": "bounded_candidate_found_not_exact" if winning_prices else "unresolved_bounded_study",
            "highestWinningEndpointPrice": max(winning_prices) / 100.0 if winning_prices else None,
            "lowestQuantityInspected": min(quantities), "highestQuantityInspected": max(quantities),
            "priceEvaluationCount": probes, "baseDistributionSeconds": base_seconds,
            "quantityDistributionSeconds": q_seconds, "financialV3V4Seconds": financial_seconds,
            "v12TransformSeconds": v12_seconds, "comparatorSeconds": comparator_seconds,
            "sampleReasons": sample_reasons.get(pid, []), "intervals": inspected,
            "monotonicityViolations": monotonicity,
        })

    end_snapshot, end_full_rows, _ = _load_source(client, snapshot_id)
    end_historical = _historical_authority(end_snapshot, end_full_rows)
    if end_historical["fingerprint"] != historical["fingerprint"]:
        raise RuntimeError("source authority changed between research start and completion")
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    process_memory: dict[str, Any] = {"available": False}
    try:
        import psutil
        memory = psutil.Process().memory_info()
        process_memory = {"available": True, "workingSetBytes": memory.rss,
                          "peakWorkingSetBytes": getattr(memory, "peak_wset", None)}
    except (ImportError, OSError):
        pass

    return {
        "thresholdMethodVersion": METHOD_VERSION,
        "source": {"snapshotId": snapshot_id, "marketDate": snapshot["market_date"],
            "cohortFingerprint": fingerprint, "fullMarketBudget": budget,
            "rankingMethodVersion": snapshot["ranking_method_version"],
            "overallRipVersion": snapshot["overall_rip_version"],
            "chaseAccessibilityVersion": snapshot["chase_accessibility_version"],
            "chaseAccessibilityTransformVersion": snapshot["chase_accessibility_transform_version"],
            "historicalSourceAuthorityFingerprint": historical["fingerprint"],
            "authorityUnchangedAtCompletion": True},
        "cohort": {"skuCount": len(products), "setCount": len({str(p["set_id"]) for p in products})},
        "parity": {"wholeSnapshot": all_parity, "fullMarket": full_market_parity},
        "guard": {"boundedCoreQuantities": ["q0", "q0+1", "q0+2"],
                  "leaderAdditionalQuantities": ["q0-1", "q0-2"],
                  "sampleAdditionalQuantities": ["q0+4", "q0+8", "q0+16"],
                  "meaning": "research only; unresolved is reported, no price floor is inferred"},
        "timings": {"sourceAuthorityLoadSeconds": authority_seconds,
                    "historicalV12ParitySeconds": parity_seconds,
                    "exactProductSourceLoadSeconds": product_source_seconds,
                    "artifactLoadSeconds": artifact_seconds,
                    "baseDistributionSeconds": sum(p["baseDistributionSeconds"] for p in per_product),
                    "quantityDistributionSeconds": sum(p["quantityDistributionSeconds"] for p in per_product),
                    "financialV3V4Seconds": sum(p["financialV3V4Seconds"] for p in per_product),
                    "v12TransformSeconds": sum(p["v12TransformSeconds"] for p in per_product),
                    "comparatorSeconds": sum(p["comparatorSeconds"] for p in per_product),
                    "totalWallClockSeconds": time.perf_counter() - total_started,
                    "peakTracedMemoryBytes": peak_bytes,
                    "processMemoryAtCompletion": process_memory},
        "monotonicity": {"intervalsChecked": sum(len(p["intervals"]) for p in per_product),
                         "adjacentPricePairsChecked": sum(max(0, len(i["endpointProbes"]) - 1)
                                                           for p in per_product for i in p["intervals"]),
                         "violations": {key: sum(p["monotonicityViolations"][key] for p in per_product)
                                        for key in ("financialRipV4", "overallRipV12", "comparator")}},
        "quantityCache": {"hits": quantity_cache_hits, "misses": quantity_cache_misses,
                          "note": "no cross-product quantity reuse; canonical product keys remain isolated"},
        "quantityDiscontinuitySample": {"productCount": len(sample_reasons), "selection": sample_reasons},
        "products": per_product,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--product-limit", type=int, default=3)
    parser.add_argument("--max-quantities", type=int, default=2,
                        help="deprecated compatibility flag; bounded study is locked to q0+1/q0+2")
    parser.add_argument("--output", type=Path, default=Path("docs/research/best_open_price_bucket0_results.json"))
    args = parser.parse_args(argv)
    result = run(args.snapshot_id, product_limit=args.product_limit, max_quantities=args.max_quantities)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "source": result["source"],
                      "cohort": result["cohort"], "timings": result["timings"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
