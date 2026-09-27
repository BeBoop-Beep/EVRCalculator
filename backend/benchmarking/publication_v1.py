"""Production-shaped RIP Benchmark V1 assembler with publication disabled.

All database operations in this module are reads.  The returned request is
validated for ``publish_pokemon_rip_benchmark_v1`` but is never submitted.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable, Mapping, Sequence
from uuid import NAMESPACE_URL, uuid5

from backend.benchmarking.evidence_v1 import (
    attach_evidence, evidence_from_scope, map_era_identities, product_evidence,
)
from backend.benchmarking.authority_v1 import (
    aggregate_era_rows, certify_product_family_policy, product_calibration_study,
)
from backend.benchmarking.preview_v1 import candidate_request
from backend.benchmarking.shadow_v1 import (
    BENCHMARK_KEY, SET_COHORT_SIZE, certify_product_rows, certify_set_cohort,
    unavailable_era_rows,
)
from backend.db.services.rip_release import bundle_for_model
from backend.domain.pokemon.rip_benchmark_v1 import (
    APPROVED_CALIBRATION_VERSION, BenchmarkError, Reference,
    approved_calibrations, day, fingerprint, number, preview_score, wire,
)

V3_CONTRACT = "pokemon-rip-stats-v3"
V3_BASIS = "all_modeled_products_per_pack_equivalent"


def _one(query: Any, label: str) -> dict[str, Any]:
    rows = list(query.limit(2).execute().data or [])
    if len(rows) != 1:
        raise BenchmarkError(f"missing or ambiguous {label}")
    return dict(rows[0])


def _pointer(client: Any) -> dict[str, Any]:
    return _one(client.table("pokemon_overall_rip_current_publication")
        .select("publication_run_id,rankings_generation_id,set_page_generation_id")
        .eq("scope", "pokemon"), "active release pointer")


def _counts(client: Any) -> dict[str, int]:
    result = {}
    for key, table in (("headers", "pokemon_rip_benchmark_publications_v1"),
                       ("rows", "pokemon_rip_benchmark_rows_v1")):
        response = client.table(table).select("id" if key == "headers" else "entity_id", count="exact").limit(1).execute()
        result[key] = int(getattr(response, "count", 0) or 0)
    return result


def _flatten_products(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    families = ((payload.get("productFamilyRankings") or {}).get("families") or {})
    products = [dict(product) for family in families.values()
                for product in (family.get("products") or [])]
    ids = [str(p.get("sealedProductId")) for p in products]
    if len(products) != 138 or len(set(ids)) != len(ids):
        raise BenchmarkError("expected exact current 138-product serving cohort")
    return products


def _references(set_rows: Sequence[Mapping[str, Any]]) -> dict[str, Reference]:
    result = {}
    for metric in ("financial", "chase", "collector", "overall"):
        rows = [r for r in set_rows if r.get("metric_key") == metric]
        if len(rows) != SET_COHORT_SIZE:
            raise BenchmarkError("incomplete Set reference cohort")
        values = [number(r["raw_model_value"]) for r in rows]
        raw = sum(values, Decimal(0)) / len(values)
        version = str(rows[0]["source_model_version"])
        proof = fingerprint({"benchmark_key": BENCHMARK_KEY, "metric": metric,
            "source_model_version": version, "members": sorted(
                (r["entity_id"], str(r["raw_model_value"]), r["source_fingerprint"]) for r in rows)})
        result[metric] = Reference(BENCHMARK_KEY, metric, version,
                                   str(rows[0]["source_market_date"]), raw, proof)
    return result


def _score_row(row: Mapping[str, Any], reference: Reference, calibration: Any) -> dict[str, Any]:
    result = deepcopy(dict(row))
    if result.get("model_status") == "unavailable":
        return result
    if (result.get("source_model_version") != calibration.source_model_version
            or reference.source_model_version != calibration.source_model_version):
        raise BenchmarkError("row/reference/calibration model mismatch")
    result.update(benchmark_status="available", benchmark_reason=None,
                  benchmark_raw_value=reference.raw_value,
                  benchmark_source_fingerprint=reference.source_fingerprint,
                  benchmark_score=preview_score(result["raw_model_value"], reference.raw_value, calibration))
    result["source_lineage"] = {**dict(result.get("source_lineage") or {}),
        "benchmark_calibration": {"version": calibration.version,
            "transform": calibration.transform_version, "scale": str(calibration.scale),
            "reference_key": reference.benchmark_key}}
    return result


def _opening_snapshot(client: Any, market_date: str) -> dict[str, Any]:
    return _one(client.table("pokemon_rip_stats_snapshots")
        .select("id,market_date,publication_status,contract_version,methodology_version,weighting_version,"
                "cohort_fingerprint,source_run_fingerprint,payload_json,published_at")
        .eq("market_date", day(market_date).isoformat()).eq("publication_status", "published")
        .eq("contract_version", V3_CONTRACT)
        .eq("methodology_version", "hierarchical_product_per_pack_empirical_v1")
        .eq("weighting_version", "equal-set_equal-family_equal-sku-v1"),
        "same-day Opening Economics V3 snapshot")


def _result_rows(client: Any, products: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    runs = sorted({str(p["calculationRunId"]) for p in products})
    fields = ("id,sealed_product_id,set_id,calculation_run_id,financial_rip_v4_score,financial_rip_v4_version,"
              "product_market_cost,expected_value,pack_count,random_pack_count,accessory_value_included,price_as_of,"
              "chance_to_recover_cost,p05_value,median_value,p95_value,p99_value,expected_loss_when_losing")
    rows = list(client.table("simulation_sealed_product_results").select(fields)
                .in_("calculation_run_id", runs).execute().data or [])
    return [dict(row) for row in rows]


def _price_date_forensics(client: Any, products: Sequence[Mapping[str, Any]],
                          result_rows: Sequence[Mapping[str, Any]], market_date: str) -> dict[str, Any]:
    ids = sorted({str(p["sealedProductId"]) for p in products})
    runs = sorted({str(p["calculationRunId"]) for p in products})
    next_day = (day(market_date) + timedelta(days=1)).isoformat()
    observations = list(client.table("sealed_product_price_observations")
        .select("sealed_product_id,captured_at,created_at,source").in_("sealed_product_id", ids)
        .gte("captured_at", f"{market_date}T00:00:00Z").lt("captured_at", f"{next_day}T00:00:00Z")
        .execute().data or [])
    run_rows = list(client.table("calculation_runs").select("id,market_date,created_at")
                    .in_("id", runs).execute().data or [])
    observed_ids = {str(r["sealed_product_id"]) for r in observations}
    result_dates = {str(r.get("price_as_of")) for r in result_rows}
    run_dates = {str(r.get("market_date")) for r in run_rows}
    observation_created = sorted(str(r.get("created_at")) for r in observations if r.get("created_at"))
    run_created = sorted(str(r.get("created_at")) for r in run_rows if r.get("created_at"))
    stale_before_run = (result_dates == {(day(market_date)-timedelta(days=1)).isoformat()}
        and run_dates == {market_date} and len(observed_ids) == len(ids)
        and observation_created and run_created and observation_created[-1] < run_created[0])
    return {"classification": "stale_snapshot_publication_sequencing" if stale_before_run else "undetermined_fail_closed",
        "model_market_dates": sorted(run_dates), "product_price_as_of_dates": sorted(result_dates),
        "affected_product_count": sum(str(r.get("price_as_of")) != market_date for r in result_rows),
        "product_count": len(ids), "same_day_observation_product_count": len(observed_ids),
        "same_day_observation_created_min": observation_created[0] if observation_created else None,
        "same_day_observation_created_max": observation_created[-1] if observation_created else None,
        "calculation_run_created_min": run_created[0] if run_created else None,
        "calculation_run_created_max": run_created[-1] if run_created else None,
        "db_follow_up_required": False if stale_before_run else None,
        "required_action": "rebuild_and_gate_same_day_sealed_snapshot_before_simulation" if stale_before_run
                           else "do_not_guess_temporal_contract"}


def _attach_financial_evidence(rows: list[dict[str, Any]], opening: Mapping[str, Any],
                               result_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    economics = (opening.get("payload_json") or {}).get("openingEconomics") or {}
    sets = {str(x.get("setId")): x for x in economics.get("sets") or []}
    eras = {str(x.get("eraName")): x for x in economics.get("eras") or []}
    era_ids = map_era_identities(economics.get("sets") or [], economics.get("eras") or [])
    results = {(str(r.get("sealed_product_id")), str(r.get("calculation_run_id"))): r for r in result_rows}
    output = []
    for row in rows:
        if row["metric_key"] != "financial":
            output.append(row); continue
        try:
            if row["entity_type"] == "set":
                scope = sets[row["entity_id"]]
                row = attach_evidence(row, evidence_from_scope(scope), market_date=opening["market_date"],
                                      source_snapshot_id=opening["id"])
            elif row["entity_type"] == "era":
                name = next(name for name, eid in era_ids.items() if eid == row["entity_id"])
                row = attach_evidence(row, evidence_from_scope(eras[name]), market_date=opening["market_date"],
                                      source_snapshot_id=opening["id"])
            else:
                source = results[(row["entity_id"], str(row["calculation_run_id"]))]
                values = product_evidence(source, market_date=opening["market_date"],
                    expected_run_id=row["calculation_run_id"], expected_result_id=row["source_result_id"])
                row = attach_evidence(row, values, market_date=opening["market_date"],
                    calculation_run_id=row["calculation_run_id"], source_result_id=row["source_result_id"])
        except (BenchmarkError, KeyError, StopIteration):
            # Evidence absence never erases an available canonical model score.
            row = dict(row)
            row["financial_evidence_reason"] = "exact_same_day_financial_evidence_unavailable"
        output.append(row)
    return output


def _statistics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result = {}
    for metric in ("financial", "chase", "collector", "overall"):
        scored = [r for r in rows if r["entity_type"] == "set" and r["metric_key"] == metric
                  and r["benchmark_status"] == "available"]
        scores = [number(r["benchmark_score"]) for r in scored]
        monotonicity = sum(1 for a in scored for b in scored
                           if number(a["raw_model_value"]) > number(b["raw_model_value"])
                           and number(a["benchmark_score"]) < number(b["benchmark_score"]))
        inversions = sum(1 for a in scored for b in scored
                         if a.get("rank") < b.get("rank") and number(a["benchmark_score"]) < number(b["benchmark_score"]))
        result[metric] = {"reference_raw_value": scored[0]["benchmark_raw_value"],
            "score_min": min(scores), "score_max": max(scores),
            "clipped_at_0": scores.count(Decimal(0)), "clipped_at_10": scores.count(Decimal(10)),
            "monotonicity_violations": monotonicity, "rank_inversions": inversions,
            "score_at_exact_reference": preview_score(scored[0]["benchmark_raw_value"],
                scored[0]["benchmark_raw_value"],
                approved_calibrations({m: next(r["source_model_version"] for r in rows
                    if r["entity_type"] == "set" and r["metric_key"] == m) for m in
                    ("financial", "chase", "collector", "overall")})[metric])}
    return result


def assert_source_coherence(*, pointer_before: Mapping[str, Any], pointer_after: Mapping[str, Any],
                            rankings_updated_before: Any, rankings_updated_after: Any,
                            opening_before: Mapping[str, Any], opening_after: Mapping[str, Any]) -> None:
    if (dict(pointer_before) != dict(pointer_after)
            or rankings_updated_before != rankings_updated_after
            or opening_before.get("source_run_fingerprint") != opening_after.get("source_run_fingerprint")
            or opening_before.get("published_at") != opening_after.get("published_at")):
        raise BenchmarkError("source authority changed during assembly")


def assemble_dry_run(client: Any, *, market_date: str | None = None,
                     after_source_read: Callable[[], None] | None = None) -> dict[str, Any]:
    """Assemble and validate the exact DB request without invoking its RPC."""
    production_before = _counts(client)
    pointer_before = _pointer(client)
    release = _one(client.table("pokemon_overall_rip_publication_runs")
        .select("id,model_version,status,market_date,financial_version,chase_version,collector_version,collector_run_id")
        .eq("id", pointer_before["publication_run_id"]), "active release")
    bundle = bundle_for_model(release["model_version"])
    rankings = _one(client.table("pokemon_explore_rankings_snapshot_latest")
        .select("ranking_payload_json,updated_at").eq("tcg", "pokemon").eq("scope", "rip-statistics"),
        "Rankings snapshot")
    certified = certify_set_cohort(rankings, {**release, "overall_version": release["model_version"],
        "score_source_policy": bundle.overall_source})
    target_day = day(market_date or certified.market_date).isoformat()
    if target_day != certified.market_date:
        raise BenchmarkError("requested market date does not match certified model cohort")
    model_versions = {metric: next(r["source_model_version"] for r in certified.rows
        if r["metric_key"] == metric) for metric in ("financial", "chase", "collector", "overall")}
    calibrations = approved_calibrations(model_versions)
    references = _references(certified.rows)
    set_rows = [_score_row(r, references[r["metric_key"]], calibrations[r["metric_key"]])
                for r in certified.rows]

    payload = rankings["ranking_payload_json"]
    products = _flatten_products(payload)
    run_by_set = {str(t["set_id"]): str(t["calculation_run_id"])
                  for t in payload.get("targets") or [] if t.get("set_id") and t.get("calculation_run_id")}
    result_rows = _result_rows(client, products)
    price_forensics = _price_date_forensics(client, products, result_rows, target_day)
    product_rows = certify_product_rows(products, result_rows, run_by_set=run_by_set,
        set_rows=set_rows, market_date=target_day, financial_version=model_versions["financial"],
        overall_version=model_versions["overall"], publication_id=certified.publication_id)
    product_policy = certify_product_family_policy(products, product_rows)
    product_study = product_calibration_study(products, product_rows, product_policy)
    family_by_product = {str(p["sealedProductId"]): str(p["productFamily"]) for p in products}
    # Inherited Set pillars use reviewed Set references. Product-native family
    # references are certified, but their calibration remains shadow-only.
    product_rows = [_score_row(r, references[r["metric_key"]], calibrations[r["metric_key"]])
                    if r["metric_key"] in ("chase", "collector") else
                    {**r, "benchmark_reason": "product_calibration_not_approved",
                     "benchmark_raw_value": product_policy["references"][(family_by_product[r["entity_id"]], r["metric_key"])].raw_value,
                     "benchmark_source_fingerprint": product_policy["references"][(family_by_product[r["entity_id"]], r["metric_key"])].source_fingerprint,
                     "source_lineage": {**dict(r.get("source_lineage") or {}),
                         "product_benchmark_policy": {"benchmark_key": product_policy["benchmark_key"],
                             "family": family_by_product[r["entity_id"]], "weighting": "equal_product_v1"}}}
                    for r in product_rows]

    opening = _opening_snapshot(client, target_day)
    economics = (opening.get("payload_json") or {}).get("openingEconomics") or {}
    if (economics.get("status") != "available" or economics.get("contractVersion") != V3_CONTRACT
            or economics.get("basis") != V3_BASIS or economics.get("marketDate") != target_day):
        raise BenchmarkError("same-day global Opening Economics contract is incompatible")
    era_ids = map_era_identities(economics.get("sets") or [], economics.get("eras") or [])
    era_rows, era_study = aggregate_era_rows(set_rows, economics.get("sets") or [],
        market_date=target_day, references=references, calibrations=calibrations)
    rows = _attach_financial_evidence(set_rows + product_rows + era_rows, opening, result_rows)
    rows = sorted(rows, key=lambda r: (r["entity_type"], r["entity_id"], r["metric_key"]))

    if after_source_read:
        after_source_read()
    pointer_after = _pointer(client)
    rankings_after = _one(client.table("pokemon_explore_rankings_snapshot_latest")
        .select("updated_at").eq("tcg", "pokemon").eq("scope", "rip-statistics"), "Rankings recheck")
    opening_after = _one(client.table("pokemon_rip_stats_snapshots")
        .select("source_run_fingerprint,published_at").eq("id", opening["id"]), "Opening Economics recheck")
    assert_source_coherence(pointer_before=pointer_before, pointer_after=pointer_after,
        rankings_updated_before=rankings["updated_at"], rankings_updated_after=rankings_after["updated_at"],
        opening_before=opening, opening_after=opening_after)

    entities = {(r["entity_type"], r["entity_id"]) for r in rows}
    source_manifest = {"rankings_publication_id": certified.publication_id,
        "rankings_updated_at": rankings["updated_at"], "model_source_date": target_day,
        "opening_economics_snapshot_id": opening["id"],
        "opening_economics_source_fingerprint": opening["source_run_fingerprint"],
        "set_count": 22, "product_count": 138, "era_count": len(era_ids),
        "production_counts_before": production_before}
    cohort_fp = fingerprint([(r["entity_type"], r["entity_id"], r["metric_key"], r["source_fingerprint"])
                             for r in rows])
    source_fp = fingerprint({"pointer": pointer_before, "manifest": source_manifest,
                             "references": {k: str(v.raw_value) for k, v in references.items()}})
    publication_id = str(uuid5(NAMESPACE_URL, f"rip-benchmark-v1/{target_day}/{cohort_fp}/{source_fp}"))
    header = {"id": publication_id, "market_date": target_day, "benchmark_key": BENCHMARK_KEY,
        "calibration_version": APPROVED_CALIBRATION_VERSION, "expected_entity_count": len(entities),
        "expected_row_count": len(rows), "cohort_fingerprint": cohort_fp, "source_fingerprint": source_fp,
        "overall_model_version": model_versions["overall"], "financial_model_version": model_versions["financial"],
        "chase_model_version": model_versions["chase"], "collector_model_version": model_versions["collector"],
        "collector_run_id": None, "collector_lineage_status": "embedded_source",
        "active_overall_publication_id": release["id"], "opening_economics_snapshot_id": opening["id"],
        "opening_economics_contract_version": V3_CONTRACT, "opening_economics_basis": V3_BASIS,
        "source_manifest": source_manifest}
    request = candidate_request(header, rows)
    production_after = _counts(client)
    if production_after != production_before:
        raise BenchmarkError("production benchmark state changed independently during dry run")
    unavailable = Counter(r.get("model_reason") for r in rows if r["model_status"] == "unavailable")
    benchmark_unavailable = Counter(r.get("benchmark_reason") for r in rows
                                    if r["benchmark_status"] == "unavailable")
    evidence_unavailable = Counter(r.get("financial_evidence_reason") for r in rows
                                   if r["metric_key"] == "financial"
                                   and r["financial_evidence_status"] == "unavailable")
    evidence_global = economics.get("global") or {}
    return wire({"status": "dry_run_validated_not_published", "production_publish_enabled": False,
        "calibration_version": APPROVED_CALIBRATION_VERSION, "benchmark_key": BENCHMARK_KEY,
        "market_date": target_day, "model_source_date": certified.market_date,
        "evidence_date": opening["market_date"], "active_release": release,
        "model_versions": model_versions, "source_coherence": "passed",
        "expected_entity_count": len(entities), "expected_row_count": len(rows),
        "cohort_fingerprint": cohort_fp, "publication_fingerprint": request["candidate_fingerprint"],
        "references": {k: v.raw_value for k, v in references.items()}, "score_distributions": _statistics(rows),
        "unavailable_counts": dict(unavailable),
        "benchmark_unavailable_counts": dict(benchmark_unavailable),
        "financial_evidence_unavailable_counts": dict(evidence_unavailable),
        "product_inheritance_counts": {m: sum(r["entity_type"] == "sealed_product" and
            r["metric_key"] == m and r["model_status"] == "inherited" for r in rows)
            for m in ("chase", "collector")},
        "era_unavailable_count": sum(r["entity_type"] == "era" and r["model_status"] == "unavailable" for r in rows),
        "product_family_policy": {k: v for k, v in product_policy.items() if k != "references"},
        "product_calibration_study": product_study, "era_aggregation_study": era_study,
        "product_financial_evidence_date_forensics": price_forensics,
        "opening_economics_reference": {"snapshot_id": opening["id"], "market_date": opening["market_date"],
            "contract_version": V3_CONTRACT, "basis": V3_BASIS,
            "cost_per_pack": evidence_global.get("averageCostPerPack"),
            "expected_value_per_pack": evidence_global.get("averageModelBreakEvenPerPack"),
            "modeled_return_on_spend": evidence_global.get("modeledReturnOnSpend"),
            "mean_outcome_retention": evidence_global.get("meanOutcomeRetention"),
            "source_fingerprint": opening["source_run_fingerprint"]},
        "source_manifest": source_manifest, "production_counts_before": production_before,
        "production_counts_after": production_after, "publish_rpc_request": request})
