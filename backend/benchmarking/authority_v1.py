"""Product-family and Era authority studies for RIP Benchmark V1."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from decimal import Decimal, localcontext
from typing import Any, Mapping, Sequence

from backend.domain.pokemon.rip_benchmark_v1 import (
    BenchmarkError, Calibration, Reference, fingerprint, identifier, metric_row,
    number, preview_score, wire,
)

PRODUCT_BENCHMARK_KEY = "pokemon_product_family_equal_weight_v1"
PRODUCT_CALIBRATION_VERSION = "rip_product_benchmark_v1_fin5_overall5_family_mean"
PRODUCT_SHADOW_GRID_VERSION = "product_benchmark_shadow_grid_v1"
PRODUCT_SCALE_GRID = tuple(map(Decimal, ("2.5", "5", "7.5", "10", "15", "20")))
ERA_AGGREGATION_VERSION = "era_rip_aggregation_v1_equal_set_mean"


def approved_product_calibrations(model_versions: Mapping[str, str]) -> dict[str, Calibration]:
    if set(model_versions) != {"financial", "overall"} or not all(model_versions.values()):
        raise BenchmarkError("exact Product Financial/Overall model identities required")
    return {metric: Calibration(PRODUCT_CALIBRATION_VERSION, metric, model_versions[metric],
                                PRODUCT_BENCHMARK_KEY, Decimal(5))
            for metric in ("financial", "overall")}


def _quantile(values: Sequence[Decimal], p: Decimal) -> Decimal:
    ordered = sorted(values)
    position = p * (len(ordered) - 1)
    low = int(position); high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def certify_product_family_policy(products: Sequence[Mapping[str, Any]],
                                  rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Certify complete, non-singleton, family-isolated native cohorts.

    Existing ``familyRank`` is certified for Overall only: the serving
    comparator ranks Overall first. Financial has no canonical product rank and
    this function deliberately does not manufacture one.
    """
    product_ids = [identifier(p.get("sealedProductId")) for p in products]
    if len(product_ids) != len(set(product_ids)):
        raise BenchmarkError("duplicate product membership")
    native = {(r["entity_id"], r["metric_key"]): r for r in rows
              if r.get("entity_type") == "sealed_product" and r.get("metric_key") in ("financial", "overall")}
    if len(native) != 2 * len(products):
        raise BenchmarkError("complete native Financial/Overall product cohort required")
    families: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for product in products:
        family = str(product.get("productFamily") or "")
        if not family:
            raise BenchmarkError("product family missing")
        families[family].append(product)
    references: dict[tuple[str, str], Reference] = {}
    report_families = {}
    for family, members in sorted(families.items()):
        if len(members) < 2:
            raise BenchmarkError("singleton/insufficient product family")
        ids = [identifier(p["sealedProductId"]) for p in members]
        declared_sizes = {p.get("familySize") for p in members}
        ranks = [p.get("familyRank") for p in members]
        if declared_sizes != {len(members)} or sorted(ranks) != list(range(1, len(members) + 1)):
            raise BenchmarkError("published family membership/rank is incomplete")
        overall_pairs = [(number(native[(pid, "overall")]["raw_model_value"]),
                          next(p["familyRank"] for p in members if p["sealedProductId"] == pid)) for pid in ids]
        if any(a_raw > b_raw and a_rank >= b_rank for a_raw, a_rank in overall_pairs
               for b_raw, b_rank in overall_pairs):
            raise BenchmarkError("existing product rank has different semantics than family Overall cohort")
        for metric in ("financial", "overall"):
            metric_rows = [native[(pid, metric)] for pid in ids]
            values = [number(r["raw_model_value"]) for r in metric_rows]
            raw = sum(values, Decimal(0)) / len(values)
            version = str(metric_rows[0]["source_model_version"])
            references[(family, metric)] = Reference(PRODUCT_BENCHMARK_KEY, metric, version,
                str(metric_rows[0]["source_market_date"]), raw,
                fingerprint({"family": family, "metric": metric,
                    "members": sorted((r["entity_id"], str(r["raw_model_value"]), r["source_fingerprint"])
                                      for r in metric_rows)}))
        report_families[family] = {"member_count": len(members), "member_ids": sorted(ids),
            "overall_rank_authority": "existing_family_rank",
            "financial_rank_authority": "unavailable_no_existing_financial_family_rank"}
    return {"status": "certified", "benchmark_key": PRODUCT_BENCHMARK_KEY,
            "families": report_families, "references": references,
            "product_count": len(products)}


def _candidate_stats(items: Sequence[dict[str, Any]], calibration: Calibration) -> dict[str, Any]:
    scored = [{**item, "score": preview_score(item["raw"], item["reference"], calibration)} for item in items]
    scores = [x["score"] for x in scored]
    inversions = sum(1 for a in scored for b in scored if a.get("rank") is not None and b.get("rank") is not None
                     and a["rank"] < b["rank"] and a["score"] < b["score"])
    monotonic = sum(1 for a in scored for b in scored if a["family"] == b["family"]
                    and a["raw"] > b["raw"] and a["score"] < b["score"])
    displayed = [s.quantize(Decimal("0.1")) for s in scores]
    return {"score_min": min(scores), "score_max": max(scores),
        "clipped_at_0": scores.count(Decimal(0)), "clipped_at_10": scores.count(Decimal(10)),
        "p10_displayed": _quantile(scores, Decimal(".10")).quantize(Decimal("0.1")),
        "p25_displayed": _quantile(scores, Decimal(".25")).quantize(Decimal("0.1")),
        "p50_displayed": _quantile(scores, Decimal(".50")).quantize(Decimal("0.1")),
        "p75_displayed": _quantile(scores, Decimal(".75")).quantize(Decimal("0.1")),
        "p90_displayed": _quantile(scores, Decimal(".90")).quantize(Decimal("0.1")),
        "distinct_displayed_one_decimal_scores": len(set(displayed)),
        "monotonicity_violations": monotonic, "canonical_rank_inversions": inversions,
        "canonical_rank_status": "available" if all(x.get("rank") is not None for x in scored)
                                 else "unavailable_no_existing_financial_family_rank"}


def product_calibration_study(products: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]],
                              policy: Mapping[str, Any]) -> dict[str, Any]:
    references = policy["references"]
    family_by_id = {identifier(p["sealedProductId"]): str(p["productFamily"]) for p in products}
    rank_by_id = {identifier(p["sealedProductId"]): p.get("familyRank") for p in products}
    result = {"status": "shadow_candidates_not_approved", "production_calibration_selected": False,
              "grid_version": PRODUCT_SHADOW_GRID_VERSION, "benchmark_key": PRODUCT_BENCHMARK_KEY,
              "product_count": len(products), "family_cardinalities": {
                  family: info["member_count"] for family, info in policy["families"].items()}, "metrics": {}}
    for metric in ("financial", "overall"):
        native = [r for r in rows if r.get("entity_type") == "sealed_product" and r.get("metric_key") == metric]
        items = [{"entity_id": r["entity_id"], "family": family_by_id[r["entity_id"]],
                  "raw": number(r["raw_model_value"]),
                  "reference": references[(family_by_id[r["entity_id"]], metric)].raw_value,
                  "rank": rank_by_id[r["entity_id"]] if metric == "overall" else None} for r in native]
        candidates = []
        version = str(native[0]["source_model_version"])
        for scale in PRODUCT_SCALE_GRID:
            cal = Calibration(f"{PRODUCT_SHADOW_GRID_VERSION}:{metric}:scale={scale}", metric, version,
                              PRODUCT_BENCHMARK_KEY, scale)
            aggregate = _candidate_stats(items, cal)
            by_family = {}
            sensitivities = []
            for family in sorted(policy["families"]):
                subset = [x for x in items if x["family"] == family]
                stats = _candidate_stats(subset, cal)
                ref = references[(family, metric)].raw_value
                sensitivity = {f"minus_{pct}pct": preview_score(ref*(Decimal(1)-Decimal(pct)/100), ref, cal)
                               for pct in (1, 2, 5)}
                sensitivity.update({f"plus_{pct}pct": preview_score(ref*(Decimal(1)+Decimal(pct)/100), ref, cal)
                                    for pct in (1, 2, 5)})
                sensitivities.append(sensitivity)
                stats.update(reference_raw_value=ref, score_at_family_mean=preview_score(ref, ref, cal),
                             sensitivity_at_family_benchmark=sensitivity,
                             clipping_dominated=(stats["clipped_at_0"]+stats["clipped_at_10"])/len(subset) >= .25,
                             compression_dominated=(len(subset) >= 4 and
                                 stats["distinct_displayed_one_decimal_scores"] <= max(2, len(subset)//3)))
                by_family[family] = stats
            aggregate["by_family"] = by_family
            aggregate["families_dominated_by_clipping"] = [k for k, v in by_family.items() if v["clipping_dominated"]]
            aggregate["families_dominated_by_compression"] = [k for k, v in by_family.items() if v["compression_dominated"]]
            candidates.append({"scale": scale, **aggregate})
        result["metrics"][metric] = {"candidates": candidates}
    result["decision"] = {"approved": False, "selected_scale": None,
                          "reason": "human review required; no automatic product calibration policy"}
    result["artifact_fingerprint"] = fingerprint(result)
    return wire(result)


def aggregate_era_rows(set_rows: Sequence[Mapping[str, Any]], set_entries: Sequence[Mapping[str, Any]],
                       *, market_date: str, references: Mapping[str, Reference],
                       calibrations: Mapping[str, Calibration]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Equal-Set means, including Overall as mean(Set Overall), never pillar recomposition."""
    available = [r for r in set_rows if r.get("entity_type") == "set" and r.get("model_status") == "available"]
    set_ids = {r["entity_id"] for r in available}
    membership: dict[str, list[str]] = defaultdict(list)
    names = {}
    for entry in set_entries:
        sid, eid = identifier(entry.get("setId")), identifier(entry.get("eraId"))
        if sid in membership[eid]:
            raise BenchmarkError("duplicate Era member")
        membership[eid].append(sid); names[eid] = str(entry.get("eraName"))
    if set().union(*(set(v) for v in membership.values())) != set_ids:
        raise BenchmarkError("incomplete Era membership partition")
    if sum(map(len, membership.values())) != len(set_ids):
        raise BenchmarkError("Set belongs to multiple Eras")
    source = {(r["entity_id"], r["metric_key"]): r for r in available}
    means = {}
    for eid, members in membership.items():
        for metric in ("financial", "chase", "collector", "overall"):
            if any((sid, metric) not in source for sid in members):
                raise BenchmarkError("Era has unavailable member metric")
            means[(eid, metric)] = sum((number(source[(sid, metric)]["raw_model_value"]) for sid in members), Decimal(0))/len(members)
    ranks = {}
    for metric in ("financial", "chase", "collector", "overall"):
        ordered = sorted(membership, key=lambda eid: (-means[(eid, metric)], eid))
        ranks.update({(eid, metric): rank for rank, eid in enumerate(ordered, 1)})
    rows = []
    proof = {"aggregation_version": ERA_AGGREGATION_VERSION, "metrics": {}}
    for eid, members in sorted(membership.items()):
        for metric in ("financial", "chase", "collector", "overall"):
            member_rows = [source[(sid, metric)] for sid in sorted(members)]
            lineage = {"aggregation_version": ERA_AGGREGATION_VERSION,
                "aggregation": "equal_weight_mean_of_canonical_member_set_raw_scores",
                "overall_rule": "mean_of_canonical_set_overall_raw_scores" if metric == "overall" else None,
                "member_set_ids": sorted(members), "member_source_fingerprints": [r["source_fingerprint"] for r in member_rows]}
            src = {"entity_type": "era", "entity_id": eid, "market_date": market_date,
                "model_version": member_rows[0]["source_model_version"], "raw_model_value": means[(eid, metric)],
                "rank": ranks[(eid, metric)], "cohort_size": len(membership),
                "reconstruction_status": "reconstructed_compatible", "source_publication_id": member_rows[0].get("source_publication_id"),
                "lineage": lineage}
            row = metric_row(entity_type="era", entity_id=eid, metric_key=metric, market_date=market_date, source=src,
                             reference=references[metric], calibration=calibrations[metric])
            rows.append(row)
            proof["metrics"].setdefault(metric, {})[eid] = {"era_name": names[eid], "member_count": len(members),
                "member_ids": sorted(members), "raw_value": means[(eid, metric)], "global_set_reference": references[metric].raw_value,
                "benchmark_score": row["benchmark_score"], "era_rank": row["rank"], "source_lineage": lineage,
                "unavailable_members": []}
    for metric in ("financial", "chase", "collector", "overall"):
        reconciled = sum(means[(eid, metric)]*len(members) for eid, members in membership.items())/sum(map(len, membership.values()))
        if reconciled != references[metric].raw_value:
            raise BenchmarkError("Era weighted mean does not reconcile to global Set reference")
        proof["metrics"][metric]["weighted_reconciliation"] = {"value": reconciled,
            "global_set_reference": references[metric].raw_value, "exact": True}
    proof.update(status="certified", aggregation_version=ERA_AGGREGATION_VERSION,
                 era_count=len(membership), set_count=len(set_ids))
    proof["artifact_fingerprint"] = fingerprint(proof)
    return rows, wire(proof)
