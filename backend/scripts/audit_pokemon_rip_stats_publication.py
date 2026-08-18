from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.opening_simulation_gate import evaluate_opening_simulation_freshness
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.db.services.pokemon_rip_stats_service import read_latest_pokemon_rip_stats
from backend.domain.pokemon.rip_stats import (POKEMON_RIP_STATS_CONTRACT_VERSION,
    POKEMON_RIP_STATS_METHODOLOGY_VERSION, POKEMON_RIP_STATS_WEIGHTING_VERSION, deterministic_fingerprint)
from backend.scripts.pokemon_snapshot_builders import get_client


def _finite(value: Any) -> float | None:
    try: result = float(value)
    except (TypeError, ValueError): return None
    return result if math.isfinite(result) else None


def audit(client: Any, market_date: str) -> dict[str, Any]:
    failures: list[str] = []
    latest = read_latest_pokemon_rip_stats(client); payload = latest.get("payload_json") or {}
    population = payload.get("population") or {}; methodology = payload.get("methodology") or {}
    if str(latest.get("market_date"))[:10] != market_date: failures.append("latest public market date mismatch")
    gate = evaluate_opening_simulation_freshness(client, market_date=market_date)
    if not gate.ok: failures.append("authoritative simulation gate is not current")
    masters = list(client.table("pokemon_rip_stats_snapshots")
        .select("id,contract_version,methodology_version,weighting_version,eligible_cohort_count,total_source_outcome_count,source_run_fingerprint,payload_json")
        .eq("market_date", market_date).eq("contract_version", POKEMON_RIP_STATS_CONTRACT_VERSION)
        .eq("methodology_version", POKEMON_RIP_STATS_METHODOLOGY_VERSION)
        .eq("weighting_version", POKEMON_RIP_STATS_WEIGHTING_VERSION).limit(1).execute().data or [])
    if not masters:
        failures.append("canonical historical master missing"); return {"status": "failed", "marketDate": market_date, "failures": failures}
    master = masters[0]
    if master.get("payload_json") != payload: failures.append("historical/latest payload mismatch")
    if master.get("source_run_fingerprint") != latest.get("source_run_fingerprint"): failures.append("historical/latest source fingerprint mismatch")
    members = list(client.table("pokemon_rip_stats_snapshot_sets").select("*").eq("snapshot_id", master["id"]).execute().data or [])
    eligible_count = int(master["eligible_cohort_count"])
    if len(members) != eligible_count: failures.append("constituent count mismatch")
    if int(population.get("setCount") or -1) != eligible_count: failures.append("public population setCount mismatch")
    authoritative = {str(item.set_id): str(item.calculation_run_id) for item in gate.statuses if item.calculation_run_id}
    provenance = []; counts = []; weights = []; total = 0
    for row in members:
        set_id = str(row.get("set_id")); count = int(row.get("artifact_outcome_count") or 0); counts.append(count)
        weight = _finite(row.get("set_weight")); weights.append(weight if weight is not None else math.nan)
        if str(row.get("source_market_date"))[:10] != market_date: failures.append(f"{set_id} source date mismatch")
        if authoritative.get(set_id) != str(row.get("calculation_run_id")): failures.append(f"{set_id} run is not authoritative")
        try: artifact = load_pack_outcome_artifact(client, row["calculation_run_id"])
        except Exception as exc: failures.append(f"{set_id} artifact invalid: {exc}"); continue
        if artifact.metadata["raw_sha256"] != row.get("artifact_sha256") or int(artifact.metadata["outcome_count"]) != count:
            failures.append(f"{set_id} artifact provenance mismatch")
        total += count
        provenance.append({"set_id": set_id, "calculation_run_id": str(row["calculation_run_id"]),
            "artifact_sha256": row["artifact_sha256"], "artifact_outcome_count": count,
            "pack_cost": float(row["pack_cost"]), "market_date": market_date})
    if not counts or len(set(counts)) != 1: failures.append("equal-set artifact counts mismatch")
    expected_count = counts[0] if counts else 0
    if int(population.get("outcomeCountPerSet") or -1) != expected_count: failures.append("public outcomeCountPerSet mismatch")
    if int(population.get("totalSourceOutcomeCount") or -1) != int(master["total_source_outcome_count"]): failures.append("public totalSourceOutcomeCount mismatch")
    if total != int(master["total_source_outcome_count"]): failures.append("constituent total outcomes mismatch")
    expected_weight = 1.0 / eligible_count if eligible_count else math.nan
    if any(not math.isclose(weight, expected_weight, rel_tol=1e-12, abs_tol=1e-12) for weight in weights) or not math.isclose(sum(weights), 1.0, rel_tol=1e-12, abs_tol=1e-12):
        failures.append("constituent weights are not equal and normalized")
    fingerprint = deterministic_fingerprint(provenance)
    if fingerprint != master["source_run_fingerprint"] or fingerprint != latest["source_run_fingerprint"]: failures.append("source fingerprint mismatch")
    economics = payload.get("packEconomics") or {}; typical = payload.get("typicalOpening") or {}; upside = payload.get("upside") or {}; downside = payload.get("downside") or {}; one = payload.get("onePackPerSet") or {}; entertainment = payload.get("entertainmentCost") or {}
    retention = _finite(economics.get("expectedRetention")); chance = _finite(economics.get("chanceToBeatCost")); hard = _finite(downside.get("hardLossProbability")); soft = _finite(downside.get("softLossShareGivenLoss"))
    if retention is None or retention < 0: failures.append("expectedRetention invalid")
    if chance is None or not 0 <= chance <= 1: failures.append("chanceToBeatCost out of range")
    if hard is None or not 0 <= hard <= 1: failures.append("hardLossProbability out of range")
    if soft is None or not 0 <= soft <= 1: failures.append("softLossShareGivenLoss out of range")
    dollar = [_finite(typical.get("value")), _finite(upside.get("p95Value")), _finite(upside.get("p99Value"))]
    ratio = [_finite(typical.get("retention")), _finite(upside.get("p95Retention")), _finite(upside.get("p99Retention"))]
    if any(value is None for value in dollar) or not dollar[0] <= dollar[1] <= dollar[2]: failures.append("dollar quantiles unordered")
    if any(value is None for value in ratio) or not ratio[0] <= ratio[1] <= ratio[2]: failures.append("retention quantiles unordered")
    if int(one.get("setCount") or -1) != eligible_count: failures.append("onePackPerSet setCount mismatch")
    if abs(float(one.get("totalPackCost", 0)) - float(one.get("totalExpectedValue", 0)) - float(one.get("expectedEntertainmentCost", 0))) > .005: failures.append("onePackPerSet identity mismatch")
    if retention is not None and abs(float(entertainment.get("expectedCostRatio", 0)) - (1 - retention)) > 1e-9: failures.append("Entertainment Cost ratio mismatch")
    if payload.get("contractVersion") != POKEMON_RIP_STATS_CONTRACT_VERSION: failures.append("public contract version mismatch")
    if methodology.get("version") != POKEMON_RIP_STATS_METHODOLOGY_VERSION or methodology.get("weightingVersion") != POKEMON_RIP_STATS_WEIGHTING_VERSION: failures.append("public methodology/weighting version mismatch")
    return {"status": "passed" if not failures else "failed", "marketDate": market_date, "setCount": len(members),
            "totalOutcomes": total, "sourceRunFingerprint": fingerprint, "failures": failures}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--market-date", required=True); args = parser.parse_args()
    result = audit(get_client(), args.market_date); print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__": main()
