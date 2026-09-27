"""Source-certified, read-only RIP Benchmark V1 shadow assembly and calibration.

This module consumes already-published serving contracts.  It never computes a
canonical model, changes a rank, selects a release, or writes benchmark tables.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any, Iterable, Mapping, Sequence

from backend.domain.pokemon.rip_benchmark_v1 import (
    BenchmarkError, Calibration, day, fingerprint, identifier, metric_row,
    number, preview_score, wire,
)
from backend.benchmarking.evidence_v1 import select_exact_product_results

SET_COHORT_SIZE = 22
BENCHMARK_KEY = "pokemon_equal_weight_eligible_sets_v1"
GRID_VERSION = "rip_benchmark_shadow_grid_v1"
DEFAULT_SCALE_GRID: Mapping[str, tuple[Decimal, ...]] = {
    "financial": tuple(map(Decimal, ("2.5", "5", "7.5", "10"))),
    "chase": tuple(map(Decimal, ("5", "10", "15", "20"))),
    "collector": tuple(map(Decimal, ("5", "10", "15", "20"))),
    "overall": tuple(map(Decimal, ("2.5", "5", "7.5", "10"))),
}


@dataclass(frozen=True)
class CertifiedSetCohort:
    market_date: str
    publication_id: str
    rows: tuple[dict[str, Any], ...]
    source_fingerprint: str


def _required_score(block: Mapping[str, Any], *, version: str, rank_key: str = "rank",
                    size_key: str = "cohortSize", version_key: str = "version") -> tuple[Decimal, int, int]:
    if (block.get(version_key) != version or block.get("status") not in ("ready", None)
            or block.get("rankable") is False):
        raise BenchmarkError("model block is unavailable or has wrong version")
    rank, size = block.get(rank_key), block.get(size_key)
    if type(rank) is not int or type(size) is not int or not 1 <= rank <= size:
        raise BenchmarkError("canonical rank/cohort missing")
    return number(block.get("score")), rank, size


def certify_set_cohort(snapshot_row: Mapping[str, Any], release: Mapping[str, Any]) -> CertifiedSetCohort:
    """Certify the exact active V12 22-set serving cohort.

    The release pointer/header must be supplied by the caller after a before/after
    pointer check.  V14 is intentionally refused: Prompt 2 cannot activate or
    silently reinterpret its generic-ledger authority.
    """
    payload = snapshot_row.get("ranking_payload_json") or {}
    meta = payload.get("meta") or {}
    snap = meta.get("snapshot") or {}
    cohort = ((meta.get("publicAnalyticsCohort") or {}).get("overallRanked") or {})
    source_day = day(snap.get("simulationSourceMarketDate")).isoformat()
    publication_id = identifier(snap.get("publicationId"))
    if release.get("score_source_policy") != "live_v12_v4_storage":
        raise BenchmarkError("shadow adapter currently certifies live V12/V4 storage only")
    versions = {
        "financial": release.get("financial_version"), "chase": release.get("chase_version"),
        "collector": release.get("collector_version"), "overall": release.get("overall_version"),
    }
    expected = {identifier(x) for x in cohort.get("rankedSetIds") or []}
    if (cohort.get("publishable") is not True or cohort.get("rankedSetCount") != SET_COHORT_SIZE
            or len(expected) != SET_COHORT_SIZE):
        raise BenchmarkError("current canonical 22-set cohort is not publishable and complete")
    targets = {identifier(t.get("set_id")): t for t in payload.get("targets") or []
               if t.get("set_id") in expected}
    if set(targets) != expected:
        raise BenchmarkError("ranked cohort does not resolve to exactly one target per set")

    rows: list[dict[str, Any]] = []
    for sid in sorted(expected):
        target = targets[sid]
        run_id = identifier(target.get("calculation_run_id"))
        financial = target.get("financialRipV4") or {}
        chase = target.get("chaseAccessibility") or {}
        collector = (target.get("openingExperience") or {}).get("collectorAppeal") or {}
        overall = target.get("overallRipV12") or {}
        f_raw, f_rank, f_size = _required_score(financial, version=versions["financial"],
                                                version_key="scoreVersion")
        c_raw, c_rank, c_size = _required_score(collector, version=versions["collector"])
        o_raw, o_rank, o_size = _required_score(overall, version=versions["overall"])
        if (chase.get("chaseAccessibilityStatus") != "ready"
                or chase.get("chaseAccessibilityVersion") != versions["chase"]
                or day(chase.get("chaseAccessibilityMarketDate")).isoformat() != source_day
                or identifier(chase.get("chaseAccessibilityCalculationRunId")) != run_id):
            raise BenchmarkError("Chase source is not the exact coherent calculation run")
        ch_raw, ch_rank, ch_size = (number(chase.get("modelScore")), chase.get("setRank"),
                                    chase.get("setCohortSize"))
        if type(ch_rank) is not int or type(ch_size) is not int or not 1 <= ch_rank <= ch_size:
            raise BenchmarkError("canonical Chase rank/cohort missing")
        if {f_size, ch_size, c_size, o_size} != {SET_COHORT_SIZE}:
            raise BenchmarkError("mixed canonical cohort sizes")
        components = overall.get("components") or {}
        if (number((components.get("financialRipV4") or {}).get("score")) != f_raw
                or number((components.get("chaseAccessibility") or {}).get("score")) != ch_raw
                or number((components.get("collectorAppeal") or {}).get("score")) != c_raw):
            raise BenchmarkError("Overall component lineage does not match certified pillars")
        common = {"entity_type": "set", "entity_id": sid, "market_date": source_day,
                  "reconstruction_status": "persisted_exact", "calculation_run_id": run_id,
                  "source_publication_id": publication_id,
                  "lineage": {"rankings_publication_id": publication_id,
                              "rankings_market_date": snap.get("marketDate"),
                              "simulation_source_market_date": source_day,
                              "calculation_run_id": run_id,
                              "authority": "live_v12_v4_storage"}}
        blocks = {
            "financial": (f_raw, f_rank, f_size), "chase": (ch_raw, ch_rank, ch_size),
            "collector": (c_raw, c_rank, c_size), "overall": (o_raw, o_rank, o_size),
        }
        for metric, (raw, rank, size) in blocks.items():
            source = {**common, "raw_model_value": raw, "rank": rank, "cohort_size": size,
                      "model_version": versions[metric]}
            rows.append(metric_row(entity_type="set", entity_id=sid, metric_key=metric,
                                   market_date=source_day, source=source))
    _validate_rank_authority(rows)
    proof = {"publication_id": publication_id, "source_day": source_day,
             "versions": versions, "rows": rows}
    return CertifiedSetCohort(source_day, publication_id, tuple(rows), fingerprint(proof))


def _validate_rank_authority(rows: Sequence[Mapping[str, Any]]) -> None:
    for metric in ("financial", "chase", "collector", "overall"):
        subset = [r for r in rows if r.get("metric_key") == metric]
        if len(subset) != SET_COHORT_SIZE or {r.get("cohort_size") for r in subset} != {SET_COHORT_SIZE}:
            raise BenchmarkError("incomplete metric rank authority")
        for left in subset:
            for right in subset:
                if (number(left["raw_model_value"]) > number(right["raw_model_value"])
                        and left["rank"] >= right["rank"]):
                    raise BenchmarkError("canonical rank contradicts raw model ordering")


def unavailable_era_rows(*, era_id: str, market_date: str,
                         financial_evidence: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """No era model aggregation is authorized; evidence is a separate concern."""
    return [metric_row(entity_type="era", entity_id=era_id, metric_key=metric,
                       market_date=market_date,
                       unavailable_reason="unavailable_era_model_contract")
            for metric in ("financial", "chase", "collector", "overall")]


def inherited_product_source(set_row: Mapping[str, Any], *, product_id: str,
                             parent_set_id: str) -> dict[str, Any]:
    """Project only the parent Set source; metric_row removes inherited rank."""
    if set_row.get("entity_type") != "set" or set_row.get("entity_id") != identifier(parent_set_id):
        raise BenchmarkError("inherited source does not belong to parent set")
    return {
        "entity_type": "set", "entity_id": set_row["entity_id"],
        "market_date": set_row["source_market_date"],
        "model_version": set_row["source_model_version"],
        "raw_model_value": set_row["raw_model_value"], "rank": set_row.get("rank"),
        "cohort_size": set_row.get("cohort_size"),
        "reconstruction_status": "persisted_exact",
        "source_publication_id": set_row.get("source_publication_id"),
        "calculation_run_id": set_row.get("calculation_run_id"),
        "lineage": {**dict(set_row.get("source_lineage") or {}),
                    "inheritance": "parent_set", "sealed_product_id": identifier(product_id)},
    }


def certify_product_rows(published_products: Sequence[Mapping[str, Any]],
                         result_rows: Sequence[Mapping[str, Any]], *,
                         run_by_set: Mapping[str, str], set_rows: Sequence[Mapping[str, Any]],
                         market_date: str, financial_version: str,
                         overall_version: str, publication_id: str) -> list[dict[str, Any]]:
    """Certify native product Financial/Overall and inherited Set pillars.

    Financial is read from the exact stored result selected by the publication's
    ``(product, run)`` pair. Overall is read from that same serving-generation
    product record. No generic-ledger duplicate is averaged.
    """
    exact = select_exact_product_results(published_products, result_rows, run_by_set=run_by_set)
    by_pair = {(identifier(r["sealed_product_id"]), identifier(r["calculation_run_id"])): r for r in exact}
    parents = {(r["entity_id"], r["metric_key"]): r for r in set_rows}
    output: list[dict[str, Any]] = []
    for product in published_products:
        pid, sid = identifier(product.get("sealedProductId")), identifier(product.get("setId"))
        run = identifier(product.get("calculationRunId"))
        result = by_pair[(pid, run)]
        result_id = identifier(result.get("id"))
        financial_raw = number(result.get("financial_rip_v4_score"))
        if (result.get("financial_rip_v4_version") != financial_version
                or financial_raw != number(product.get("financialRipAbsoluteScore"))):
            raise BenchmarkError("exact product Financial result disagrees with published product")
        overall = product.get("overallRipV12") or {}
        if overall.get("version") != overall_version or overall.get("status") != "ready":
            raise BenchmarkError("product Overall is not from selected serving generation")
        lineage = {"product_rankings_publication_id": identifier(publication_id),
                   "calculation_run_id": run, "source_result_id": result_id,
                   "authority": "exact_published_product_result_run"}
        native = {
            "entity_type": "sealed_product", "entity_id": pid, "market_date": day(market_date).isoformat(),
            "reconstruction_status": "persisted_exact", "calculation_run_id": run,
            "source_result_id": result_id, "source_publication_id": identifier(publication_id),
            "lineage": lineage,
        }
        output.append(metric_row(entity_type="sealed_product", entity_id=pid, parent_set_id=sid,
            metric_key="financial", market_date=market_date,
            source={**native, "model_version": financial_version, "raw_model_value": financial_raw,
                    "rank": None, "cohort_size": None}))
        rank, size = product.get("familyRank"), product.get("familySize")
        if type(rank) is not int or type(size) is not int or not 1 <= rank <= size:
            raise BenchmarkError("published product Overall family rank is invalid")
        output.append(metric_row(entity_type="sealed_product", entity_id=pid, parent_set_id=sid,
            metric_key="overall", market_date=market_date,
            source={**native, "model_version": overall_version,
                    "raw_model_value": number(overall.get("score")), "rank": rank, "cohort_size": size}))
        for metric in ("chase", "collector"):
            parent = parents.get((sid, metric))
            if parent is None:
                raise BenchmarkError(f"missing certified parent Set {metric} source")
            source = inherited_product_source(parent, product_id=pid, parent_set_id=sid)
            output.append(metric_row(entity_type="sealed_product", entity_id=pid, parent_set_id=sid,
                metric_key=metric, market_date=market_date, source=source))
    return sorted(output, key=lambda r: (r["entity_id"], r["metric_key"]))


def _quantile(values: Sequence[Decimal], p: Decimal) -> Decimal:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    with localcontext() as ctx:
        ctx.prec = 50
        position = p * (len(ordered) - 1)
        low = int(position); high = min(low + 1, len(ordered) - 1)
        fraction = position - low
        return ordered[low] + (ordered[high] - ordered[low]) * fraction


def calibration_analysis(rows: Sequence[Mapping[str, Any]], *,
                         grids: Mapping[str, Iterable[Decimal]] = DEFAULT_SCALE_GRID) -> dict[str, Any]:
    """Evaluate fixed candidates.  The result deliberately contains no selection."""
    report: dict[str, Any] = {"status": "shadow_candidates_not_approved",
        "grid_version": GRID_VERSION, "benchmark_key": BENCHMARK_KEY,
        "production_calibration_selected": False, "metrics": {}}
    for metric, scales in grids.items():
        subset = [r for r in rows if r.get("metric_key") == metric and r.get("model_status") == "available"]
        if len(subset) != SET_COHORT_SIZE:
            raise BenchmarkError(f"{metric} does not have the complete certified cohort")
        raw = [number(r["raw_model_value"]) for r in subset]
        reference = sum(raw, Decimal(0)) / len(raw)
        summary = {"count": len(raw), "raw_mean": reference,
                   "raw_median": _quantile(raw, Decimal(".5")), "raw_min": min(raw),
                   "raw_max": max(raw), "raw_p10": _quantile(raw, Decimal(".1")),
                   "raw_p25": _quantile(raw, Decimal(".25")), "raw_p75": _quantile(raw, Decimal(".75")),
                   "raw_p90": _quantile(raw, Decimal(".9")), "benchmark_raw_value": reference,
                   "candidates": []}
        version = str(subset[0]["source_model_version"])
        for scale_value in scales:
            scale = number(scale_value)
            cal = Calibration(f"{GRID_VERSION}:{metric}:scale={scale}", metric, version,
                              BENCHMARK_KEY, scale)
            scores = [preview_score(v, reference, cal) for v in raw]
            monotonicity = sum(1 for a in range(len(raw)) for b in range(len(raw))
                               if raw[a] > raw[b] and scores[a] < scores[b])
            inversions = sum(1 for a in range(len(subset)) for b in range(len(subset))
                             if subset[a]["rank"] < subset[b]["rank"] and scores[a] < scores[b])
            sensitivity = {}
            for pct in (Decimal(".01"), Decimal(".02"), Decimal(".05")):
                sensitivity[f"plus_{int(pct*100)}pct"] = preview_score(reference*(1+pct), reference, cal)
                sensitivity[f"minus_{int(pct*100)}pct"] = preview_score(reference*(1-pct), reference, cal)
            summary["candidates"].append({"scale": scale, "score_min": min(scores),
                "score_max": max(scores), "percent_clipped_at_0": Decimal(100)*scores.count(Decimal(0))/len(scores),
                "percent_clipped_at_10": Decimal(100)*scores.count(Decimal(10))/len(scores),
                "distinct_displayed_one_decimal_scores": len({s.quantize(Decimal("0.1")) for s in scores}),
                "monotonicity_violations": monotonicity, "rank_inversions": inversions,
                "score_at_benchmark": preview_score(reference, reference, cal),
                "sensitivity_at_benchmark": sensitivity})
        report["metrics"][metric] = summary
    report["consequences"] = (
        "Smaller scales spread scores and increase clipping/ties; larger scales preserve more headroom "
        "but compress displayed differences. Canonical ranks remain independent in every candidate."
    )
    report["artifact_fingerprint"] = fingerprint(report)
    return wire(report)
