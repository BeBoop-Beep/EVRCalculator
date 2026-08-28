from __future__ import annotations

import hashlib
import json
import math
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from backend.calculations.evr.sealed_product_distribution import build_stage1_product_distributions
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.domain.pokemon.opening_economics_v3 import (
    CONTRACT_VERSION, METHODOLOGY_VERSION, WEIGHTING_VERSION,
    OpeningEconomicsV3Error, WeightedEmpiricalMixture, build_scope,
)

PRODUCT_FIELDS = (
    "calculation_run_id,sealed_product_id,set_id,product_family,product_name,pack_count,"
    "composition_version,composition_id,distribution_model_version,random_pack_count,"
    "guaranteed_component_market_value,accessory_value_included,product_market_cost,price_as_of,"
    "expected_value,median_value,p05_value,p95_value,p99_value,chance_to_recover_cost,simulation_count"
)
COMPACT_QUANTILES = (.01, .05, .10, .25, .50, .75, .90, .95, .99)


def _all(query, page_size=1000):
    rows, start = [], 0
    while True:
        page = list(query.range(start, start + page_size - 1).execute().data or [])
        rows.extend(page)
        if len(page) < page_size: return rows
        start += page_size


def _fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
    fields = ("calculation_run_id", "sealed_product_id", "product_family", "product_market_cost", "pack_count",
              "random_pack_count", "composition_id", "composition_version", "distribution_model_version",
              "guaranteed_component_market_value", "expected_value", "price_as_of")
    payload = [{key: row.get(key) for key in fields} for row in sorted(rows, key=lambda r: (str(r.get("calculation_run_id")), str(r.get("sealed_product_id"))))]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _verify(row: Mapping[str, Any], vector: np.ndarray, tolerance=1e-6) -> None:
    price = float(row["product_market_cost"])
    checks = {"expected_value": float(vector.mean()), "median_value": float(np.median(vector)),
              "p05_value": float(np.percentile(vector, 5)), "p95_value": float(np.percentile(vector, 95)),
              "p99_value": float(np.percentile(vector, 99)),
              "chance_to_recover_cost": float(np.mean(vector >= price))}
    for field, actual in checks.items():
        expected = row.get(field)
        if expected is None or not math.isclose(float(expected), actual, rel_tol=tolerance, abs_tol=tolerance):
            raise OpeningEconomicsV3Error(
                f"regenerated distribution mismatch for {row.get('sealed_product_id')}: {field} stored={expected} actual={actual}"
            )


def _identity(scope: dict[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    families = sorted({str(row["product_family"]) for row in rows})
    return {**scope, "setCount": len({str(row["set_id"]) for row in rows}), "productSkuCount": len(rows), "productFamilyCount": len(families),
            "representedFamilies": families, "coverageStatus": "complete",
            "methodologyVersion": METHODOLOGY_VERSION, "weightingVersion": WEIGHTING_VERSION}


def build_opening_economics_v3(client: Any, *, market_date: str, statuses: Sequence[Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.perf_counter()
    run_ids = [str(status.calculation_run_id) for status in statuses]
    products = _all(client.table("simulation_sealed_product_results").select(PRODUCT_FIELDS).in_("calculation_run_id", run_ids))
    if not products:
        raise OpeningEconomicsV3Error("canonical runs have no sealed-product results")
    if {str(row.get("calculation_run_id")) for row in products} - set(run_ids):
        raise OpeningEconomicsV3Error("product cohort contains a non-canonical run")
    set_ids = [str(status.set_id) for status in statuses]
    set_rows = _all(client.table("sets").select("id,name,canonical_key,era_id").in_("id", set_ids))
    eras = _all(client.table("eras").select("id,name"))
    era_names = {str(row["id"]): str(row["name"]) for row in eras}
    set_meta = {str(row["id"]): row for row in set_rows}
    run_rows = _all(client.table("calculation_runs").select("id,calculation_config_id").in_("id", run_ids))
    config_ids = [str(row["calculation_config_id"]) for row in run_rows]
    configs = _all(client.table("calculation_configs").select("id,config_hash").in_("id", config_ids))
    hashes = {str(row["id"]): str(row["config_hash"]) for row in configs}
    run_hash = {str(row["id"]): hashes.get(str(row["calculation_config_id"]), "") for row in run_rows}
    by_run = {run_id: [row for row in products if str(row.get("calculation_run_id")) == run_id] for run_id in run_ids}
    exclusions = []
    usable = []
    temp_bytes = 0
    with tempfile.TemporaryDirectory(prefix="pokemon-opening-v3-") as directory:
        owner = WeightedEmpiricalMixture(directory)
        paths = {}; distribution_cache = {}
        try:
            for status in statuses:
                run_id, set_id = str(status.calculation_run_id), str(status.set_id)
                rows = by_run.get(run_id, [])
                counts = sorted({int(row.get("random_pack_count") or row.get("pack_count") or 0) for row in rows if int(row.get("random_pack_count") or row.get("pack_count") or 0) > 0})
                artifact = load_pack_outcome_artifact(client, run_id)
                built = build_stage1_product_distributions(artifact.outcomes, pack_counts=counts,
                    canonical_set_key=set_meta[set_id]["canonical_key"], run_fingerprint=run_hash.get(run_id))
                for row in rows:
                    try:
                        pack_count = int(row.get("pack_count") or 0)
                        random_count = int(row.get("random_pack_count") or pack_count)
                        if pack_count < 1 or random_count != pack_count: raise OpeningEconomicsV3Error("invalid or mismatched pack count")
                        if row.get("accessory_value_included") is True: raise OpeningEconomicsV3Error("accessory value must be excluded")
                        vector = np.asarray(built["distributions"][random_count], dtype=np.float64)
                        guaranteed = float(row.get("guaranteed_component_market_value") or 0)
                        if guaranteed: vector = vector + guaranteed
                        _verify(row, vector)
                        cache_key = (run_id, pack_count, guaranteed)
                        if cache_key not in distribution_cache:
                            per_pack = vector / pack_count
                            owner.add(per_pack, weight=1, cost_per_pack=float(row["product_market_cost"]) / pack_count)
                            component = owner.components[-1]
                            distribution_cache[cache_key] = (component.path, component.count)
                            temp_bytes += component.path.stat().st_size
                        paths[str(row["sealed_product_id"])] = distribution_cache[cache_key]
                        usable.append(dict(row))
                    except (KeyError, TypeError, ValueError, OpeningEconomicsV3Error) as exc:
                        exclusions.append({"sealedProductId": row.get("sealed_product_id"), "reason": str(exc)})
                        raise
            if {row["set_id"] for row in usable} != set(set_ids):
                raise OpeningEconomicsV3Error("not every canonical set has eligible product economics")
            global_scope = _identity(build_scope(usable, paths), usable)
            set_scopes, era_groups = [], {}
            for set_id in sorted(set_ids):
                subset = [row for row in usable if str(row["set_id"]) == set_id]
                meta = set_meta[set_id]; era_name = era_names.get(str(meta.get("era_id")), "Unassigned")
                family_rows = []
                for family in sorted({row["product_family"] for row in subset}):
                    family_subset = [row for row in subset if row["product_family"] == family]
                    family_rows.append({"family": family, **_identity(build_scope(family_subset, paths, qs=COMPACT_QUANTILES), family_subset)})
                block = {"setId": set_id, "setName": meta.get("name"), "setCanonicalKey": meta.get("canonical_key"),
                         "eraId": meta.get("era_id"), "eraName": era_name,
                         **_identity(build_scope(subset, paths, qs=COMPACT_QUANTILES), subset), "familyEconomics": family_rows}
                set_scopes.append(block); era_groups.setdefault(era_name, []).extend(subset)
            era_scopes = []
            for era_name, subset in sorted(era_groups.items()):
                era_scopes.append({"eraName": era_name, "setCount": len({row["set_id"] for row in subset}), **_identity(build_scope(subset, paths, qs=COMPACT_QUANTILES), subset)})
        finally:
            owner.cleanup()
    payload = {"status": "available", "contractVersion": CONTRACT_VERSION, "marketDate": str(market_date)[:10],
               "population": {"setCount": len(set_ids), "productFamilyCount": len({row["product_family"] for row in usable}),
                              "productSkuCount": len(usable), "setFamilyCount": len({(row["set_id"], row["product_family"]) for row in usable})},
               "global": global_scope, "eras": era_scopes, "sets": set_scopes,
               "familyBenchmarks": [], "inputFingerprint": _fingerprint(usable),
               "methodology": {"version": METHODOLOGY_VERSION, "weightingVersion": WEIGHTING_VERSION,
                   "productNormalization": "complete_product_value_and_cost_divided_by_verified_random_booster_pack_count",
                   "hierarchy": "equal set, equal represented family within set, equal SKU within set-family",
                   "guaranteedComponents": "included exactly once before per-pack normalization", "accessories": "zero modeled value",
                   "distributionQuantileDefinition": "inf{x:F(x)>=q}"}}
    diagnostics = {"productDistributionsRegenerated": len(usable), "excludedProducts": exclusions,
                   "wallClockSeconds": time.perf_counter() - started, "temporaryDiskBytes": temp_bytes,
                   "payloadBytes": len(json.dumps(payload, separators=(",", ":")).encode())}
    return payload, diagnostics
