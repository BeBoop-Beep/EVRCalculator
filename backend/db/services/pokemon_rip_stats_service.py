from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any, Mapping

from backend.db.services.opening_simulation_gate import evaluate_opening_simulation_freshness
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.db.services.pokemon_market_index_service import resolve_eligible_sets
from backend.domain.pokemon.rip_stats import (
    POKEMON_RIP_STATS_CONTRACT_VERSION, POKEMON_RIP_STATS_METHODOLOGY_VERSION,
    POKEMON_RIP_STATS_WEIGHTING_VERSION, calculate_pokemon_rip_stats, deterministic_fingerprint,
)

HISTORY_TABLE = "pokemon_rip_stats_snapshots"
LATEST_TABLE = "pokemon_rip_stats_snapshot_latest"
PUBLICATION_RPC = "publish_pokemon_rip_stats_snapshot"


class PokemonRipStatsUnavailable(RuntimeError):
    pass


def _build_payload(metrics: Mapping[str, Any], *, market_date: str, cohort_fingerprint: str, source_fingerprint: str) -> dict[str, Any]:
    return {"contractVersion": POKEMON_RIP_STATS_CONTRACT_VERSION, "marketDate": market_date,
        "population": {"definition": "uniform_random_supported_set_one_pack", "weighting": "equal_set",
            "setCount": metrics["setCount"], "outcomeCountPerSet": metrics["outcomeCountPerSet"],
            "totalSourceOutcomeCount": metrics["totalSourceOutcomeCount"], "cohortFingerprint": cohort_fingerprint,
            "sourceRunFingerprint": source_fingerprint},
        "packEconomics": {key: metrics[key] for key in ("meanPackCost", "medianPackCost", "expectedValue", "expectedRetention", "chanceToBeatCost", "expectedLossUnconditional")},
        "typicalOpening": {"value": metrics["typicalOpeningValue"], "retention": metrics["typicalRetention"], "quantile": .50},
        "upside": {key: metrics[key] for key in ("p95Value", "p95Retention", "p99Value", "p99Retention")},
        "downside": {"averageRetentionGivenLoss": metrics["averageRetentionGivenLoss"], "softLossShareGivenLoss": metrics["softLossShareGivenLoss"],
            "hardLossProbability": metrics["hardLossProbability"], "hardLossThreshold": .50},
        "entertainmentCost": {"expectedCost": metrics["expectedEntertainmentCost"], "expectedCostRatio": metrics["expectedEntertainmentCostRatio"],
            "recoveryModel": "gross_market_value", "accessoryValueIncluded": False, "contractVersion": "entertainment-cost-v1"},
        "onePackPerSet": metrics["onePackPerSet"],
        "methodology": {"version": POKEMON_RIP_STATS_METHODOLOGY_VERSION, "weightingVersion": POKEMON_RIP_STATS_WEIGHTING_VERSION,
            "quantilesBuiltFromExactOutcomes": True, "score": False}}


def build_pokemon_rip_stats_snapshot(client: Any, *, market_date: str) -> dict[str, Any]:
    day = str(market_date)[:10]
    gate = evaluate_opening_simulation_freshness(client, market_date=day)
    if not gate.ok:
        raise PokemonRipStatsUnavailable(gate.error or "; ".join(item.reason or item.status for item in gate.failures))
    statuses = sorted([item for item in gate.statuses if item.calculation_run_id], key=lambda item: str(item.set_id))
    public_ids = {str(row["id"]) for row in resolve_eligible_sets(client)
                  if not row.get("release_date") or str(row["release_date"])[:10] <= day}
    status_ids = {str(item.set_id) for item in statuses}
    if status_ids != public_ids:
        raise PokemonRipStatsUnavailable(
            f"opening freshness cohort disagrees with supported public cohort: gate={len(status_ids)} public={len(public_ids)}"
        )
    if len(statuses) != gate.eligible_count:
        raise PokemonRipStatsUnavailable("authoritative current simulation cohort did not reconcile")
    run_ids = [str(item.calculation_run_id) for item in statuses]
    summaries = list(client.table("simulation_run_summary").select("calculation_run_id,pack_cost,mean_value").in_("calculation_run_id", run_ids).execute().data or [])
    summary_by_run = {str(row["calculation_run_id"]): row for row in summaries}
    inputs, constituents, provenance = [], [], []
    common_count = None
    for status in statuses:
        run_id = str(status.calculation_run_id)
        summary = summary_by_run.get(run_id)
        cost = float(summary.get("pack_cost") or 0) if summary else 0
        if not summary or not math.isfinite(cost) or cost <= 0:
            raise PokemonRipStatsUnavailable(f"run {run_id} has no valid pack cost")
        loaded = load_pack_outcome_artifact(client, run_id)
        metadata = loaded.metadata
        outcome_count = int(metadata["outcome_count"])
        if common_count is None:
            common_count = outcome_count
        elif outcome_count != common_count:
            raise PokemonRipStatsUnavailable("equal-set empirical v1 requires equal artifact outcome counts")
        item = {"set_id": str(status.set_id), "canonical_key": status.canonical_key, "pack_cost": cost, "outcomes": loaded.outcomes}
        inputs.append(item)
        source = {"set_id": str(status.set_id), "calculation_run_id": run_id, "artifact_sha256": metadata["raw_sha256"],
            "artifact_outcome_count": outcome_count, "pack_cost": cost, "market_date": day}
        provenance.append(source)
        constituents.append({**source, "set_canonical_key": status.canonical_key, "set_weight": 1.0 / len(statuses), "source_market_date": day})
    cohort_fp = deterministic_fingerprint([{"set_id": item["set_id"]} for item in provenance])
    source_fp = deterministic_fingerprint(provenance)
    metrics = calculate_pokemon_rip_stats(inputs)
    payload = _build_payload(metrics, market_date=day, cohort_fingerprint=cohort_fp, source_fingerprint=source_fp)
    now = datetime.now(timezone.utc).isoformat()
    private = {"market_date": day, "built_at": now, "contract_version": POKEMON_RIP_STATS_CONTRACT_VERSION,
        "methodology_version": POKEMON_RIP_STATS_METHODOLOGY_VERSION, "weighting_version": POKEMON_RIP_STATS_WEIGHTING_VERSION,
        "eligible_cohort_count": len(statuses), "exact_outcome_set_count": len(constituents),
        "total_source_outcome_count": metrics["totalSourceOutcomeCount"], "cohort_fingerprint": cohort_fp,
        "source_run_fingerprint": source_fp, "payload_json": payload,
        "diagnostics_json": {"artifactRawBytes": sum(int(load.get("artifact_outcome_count")) * 8 for load in constituents)}}
    return {"snapshot": private, "constituents": constituents, "payload": payload, "metrics": metrics,
            "payloadSizeBytes": len(json.dumps(payload, separators=(",", ":")).encode())}


def publish_pokemon_rip_stats_snapshot(client: Any, built: Mapping[str, Any]) -> str:
    result = client.rpc(PUBLICATION_RPC, {"p_snapshot": built["snapshot"], "p_constituents": built["constituents"]}).execute()
    if not result or not result.data:
        raise PokemonRipStatsUnavailable("atomic RIP Stats publication returned no snapshot id")
    return str(result.data)


def read_latest_pokemon_rip_stats(client: Any) -> dict[str, Any]:
    rows = list(client.table(LATEST_TABLE).select("market_date,payload_json,source_run_fingerprint,updated_at").eq("tcg", "pokemon").eq("scope", "rip-stats").limit(1).execute().data or [])
    if not rows:
        raise PokemonRipStatsUnavailable("Pokemon RIP Stats snapshot is unavailable")
    return dict(rows[0])


def read_pokemon_rip_stats_history(client: Any) -> list[dict[str, Any]]:
    return list(client.table(HISTORY_TABLE).select("market_date,payload_json,source_run_fingerprint,published_at").order("market_date", desc=False).execute().data or [])
