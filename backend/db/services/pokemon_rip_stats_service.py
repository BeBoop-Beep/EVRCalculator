from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any, Mapping

from backend.db.services.opening_simulation_gate import evaluate_opening_simulation_freshness
from backend.db.services.pack_outcome_artifact_service import (
    load_pack_outcome_artifact, load_pack_outcome_artifact_metadata,
)
from backend.db.services.pokemon_market_index_service import resolve_eligible_sets
from backend.db.services.publication_gate import MODE_REQUIRED, evaluate_publication_gate
from backend.domain.pokemon.rip_stats import (
    POKEMON_RIP_STATS_CONTRACT_VERSION, POKEMON_RIP_STATS_METHODOLOGY_VERSION,
    POKEMON_RIP_STATS_WEIGHTING_VERSION, calculate_pokemon_rip_stats_streaming, deterministic_fingerprint,
)

HISTORY_TABLE = "pokemon_rip_stats_snapshots"
LATEST_TABLE = "pokemon_rip_stats_snapshot_latest"
PUBLICATION_RPC = "publish_pokemon_rip_stats_snapshot"


class PokemonRipStatsUnavailable(RuntimeError):
    pass


#: Era rows live INSIDE payload_json rather than in their own table or a scope
#: column. An era is a partition of a cohort the snapshot already owns, not a
#: separate publication: giving it its own row would let an era be published,
#: refreshed or rolled back independently of the global figure it must always
#: reconcile with, and the atomic RPC would no longer be able to guarantee they
#: describe the same 22 runs on the same market date.
UNASSIGNED_ERA_NAME = "Unassigned"


def _resolve_era_names(client: Any, set_ids: list[str]) -> dict[str, str]:
    """``set_id -> era name`` for the canonical cohort.

    Two queries rather than one embedded select: PostgREST embedding silently
    drops rows whose foreign key is null, which would make a set with no era
    vanish from the cohort instead of being reported as unassigned.
    """
    rows = list(client.table("sets").select("id,era_id").in_("id", set_ids).execute().data or [])
    era_ids = sorted({str(row["era_id"]) for row in rows if row.get("era_id")})
    names: dict[str, str] = {}
    if era_ids:
        era_rows = list(client.table("eras").select("id,name").in_("id", era_ids).execute().data or [])
        names = {str(row["id"]): str(row["name"]) for row in era_rows}
    resolved = {}
    for row in rows:
        era_id = str(row["era_id"]) if row.get("era_id") else None
        resolved[str(row["id"])] = names.get(era_id, UNASSIGNED_ERA_NAME) if era_id else UNASSIGNED_ERA_NAME
    missing = set(set_ids) - set(resolved)
    if missing:
        raise PokemonRipStatsUnavailable(f"cohort sets missing from sets table: {sorted(missing)}")
    return resolved


def _distribution_block(metrics: Mapping[str, Any], suffix: str) -> dict[str, Any]:
    """The six-point exact-outcome ladder for one distribution."""
    return {"p05": metrics[f"p05{suffix}"], "p25": metrics[f"p25{suffix}"],
            "p50": metrics[f"typicalOpeningValue"] if suffix == "Value" else metrics["typicalRetention"],
            "p75": metrics[f"p75{suffix}"], "p95": metrics[f"p95{suffix}"], "p99": metrics[f"p99{suffix}"]}


def _scope_metrics_block(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """The metric surface shared by the global scope and every era scope.

    One shape for both so a reader never branches on scope to find a field.
    """
    return {
        "setCount": metrics["setCount"],
        "meanPackCost": metrics["meanPackCost"],
        "medianPackCost": metrics["medianPackCost"],
        "expectedValue": metrics["expectedValue"],
        "chanceToBeatCost": metrics["chanceToBeatCost"],
        "typicalOpening": {"value": metrics["typicalOpeningValue"], "retention": metrics["typicalRetention"], "quantile": .50},
        "modeledReturnOnSpend": metrics["modeledReturnOnSpend"],
        "entertainmentCostShare": metrics["entertainmentCostShare"],
        "expectedEntertainmentCost": metrics["expectedEntertainmentCost"],
        "rawDistribution": _distribution_block(metrics, "Value"),
        "normalizedReturnDistribution": _distribution_block(metrics, "Retention"),
        "onePackPerSet": metrics["onePackPerSet"],
    }


def _build_payload(metrics: Mapping[str, Any], *, market_date: str, cohort_fingerprint: str, source_fingerprint: str, eras: list[dict[str, Any]]) -> dict[str, Any]:
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
            "quantilesBuiltFromExactOutcomes": True, "score": False},
        # The read contract for the Overall and Eras lenses. Additive: every
        # legacy block above keeps its original fields and meanings, because
        # `expectedRetention` and `expectedCostRatio` are equal-weighted means of
        # per-set ratios and existing consumers read them as such. The
        # spend-weighted headline ratios live here instead of replacing them.
        "openingEconomics": {
            "status": "available",
            "marketDate": market_date,
            "methodologyVersion": POKEMON_RIP_STATS_METHODOLOGY_VERSION,
            "weightingMode": "equal_set_weight",
            "productFamily": "loose_booster_pack",
            "recoveryModel": "gross_market_value",
            "quantilesBuiltFromExactOutcomes": True,
            "global": _scope_metrics_block(metrics),
            "eras": eras}}


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
    derived_rows = list(client.table("simulation_derived_metrics").select("calculation_run_id").in_("calculation_run_id", run_ids).execute().data or [])
    derived_run_ids = {str(row.get("calculation_run_id")) for row in derived_rows}
    if derived_run_ids != set(run_ids):
        raise PokemonRipStatsUnavailable("authoritative cohort has missing simulation_derived_metrics rows")
    inputs, constituents, provenance = [], [], []
    common_count = None
    for status in statuses:
        run_id = str(status.calculation_run_id)
        summary = summary_by_run.get(run_id)
        cost = float(summary.get("pack_cost") or 0) if summary else 0
        if not summary or not math.isfinite(cost) or cost <= 0:
            raise PokemonRipStatsUnavailable(f"run {run_id} has no valid pack cost")
        metadata = load_pack_outcome_artifact_metadata(client, run_id)
        outcome_count = int(metadata["outcome_count"])
        if common_count is None:
            common_count = outcome_count
        elif outcome_count != common_count:
            raise PokemonRipStatsUnavailable("equal-set empirical v1 requires equal artifact outcome counts")
        item = {"set_id": str(status.set_id), "canonical_key": status.canonical_key,
                "calculation_run_id": run_id, "pack_cost": cost, "outcome_count": outcome_count,
                "artifact_sha256": metadata["raw_sha256"]}
        inputs.append(item)
        source = {"set_id": str(status.set_id), "calculation_run_id": run_id, "artifact_sha256": metadata["raw_sha256"],
            "artifact_outcome_count": outcome_count, "pack_cost": cost, "market_date": day}
        provenance.append(source)
        constituents.append({**source, "set_canonical_key": status.canonical_key, "set_weight": 1.0 / len(statuses), "source_market_date": day})
    cohort_fp = deterministic_fingerprint([{"set_id": item["set_id"]} for item in provenance])
    source_fp = deterministic_fingerprint(provenance)
    def load_validated_outcomes(item: Mapping[str, Any]):
        loaded = load_pack_outcome_artifact(client, item["calculation_run_id"])
        metadata = loaded.metadata
        if (int(metadata["outcome_count"]) != int(item["outcome_count"])
                or metadata["raw_sha256"] != item["artifact_sha256"]):
            raise PokemonRipStatsUnavailable(
                f"artifact changed between metadata and calculation passes for {item['set_id']}"
            )
        return loaded.outcomes

    metrics = calculate_pokemon_rip_stats_streaming(inputs, load_validated_outcomes)

    # Eras partition the SAME canonical cohort, computed with the SAME exact
    # outcome methodology and the same equal-set weighting - a set is simply
    # weighted 1/len(era) within its era instead of 1/22. Each set belongs to
    # exactly one era, so this reloads every artifact twice more (once per
    # streaming pass), not once per era.
    era_by_set = _resolve_era_names(client, [str(item["set_id"]) for item in inputs])
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for item in inputs:
        grouped.setdefault(era_by_set[str(item["set_id"])], []).append(item)
    eras: list[dict[str, Any]] = []
    for era_name in sorted(grouped):
        subset = grouped[era_name]
        era_metrics = calculate_pokemon_rip_stats_streaming(subset, load_validated_outcomes)
        eras.append({"eraName": era_name,
                     "cohortFingerprint": deterministic_fingerprint([{"set_id": item["set_id"]} for item in subset]),
                     **_scope_metrics_block(era_metrics)})
    # An era cohort that does not re-add to the global cohort means a set was
    # dropped or double-counted; publishing that would put two irreconcilable
    # populations in one payload.
    era_total = sum(int(block["setCount"]) for block in eras)
    if era_total != int(metrics["setCount"]):
        raise PokemonRipStatsUnavailable(
            f"era partition did not reconcile with the global cohort: eras={era_total} global={metrics['setCount']}"
        )

    payload = _build_payload(metrics, market_date=day, cohort_fingerprint=cohort_fp, source_fingerprint=source_fp, eras=eras)
    now = datetime.now(timezone.utc).isoformat()
    private = {"market_date": day, "built_at": now, "contract_version": POKEMON_RIP_STATS_CONTRACT_VERSION,
        "methodology_version": POKEMON_RIP_STATS_METHODOLOGY_VERSION, "weighting_version": POKEMON_RIP_STATS_WEIGHTING_VERSION,
        "eligible_cohort_count": len(statuses), "exact_outcome_set_count": len(constituents),
        "total_source_outcome_count": metrics["totalSourceOutcomeCount"], "cohort_fingerprint": cohort_fp,
        "source_run_fingerprint": source_fp, "payload_json": payload,
        "diagnostics_json": {"artifactRawBytes": sum(int(load.get("artifact_outcome_count")) * 8 for load in constituents)}}
    return {"snapshot": private, "constituents": constituents, "payload": payload, "metrics": metrics,
            "payloadSizeBytes": len(json.dumps(payload, separators=(",", ":")).encode())}


def _require_publication_authority(client: Any, market_date: str) -> None:
    """Fail closed unless the exact snapshot date owns a promoted, complete batch.

    Defense in depth. The CLI gate is not enough: any caller reaching the
    service directly (orchestrators, ad-hoc scripts, a REPL) would otherwise
    publish straight through to the RPC. The authority is re-evaluated here for
    the snapshot's OWN market_date so a caller cannot publish date A while a
    different date B happens to be promoted.

    ``mode`` is pinned to required on purpose: PUBLICATION_GATE_MODE=disabled
    must not be able to weaken the RIP Stats sequencing invariant, and no
    override is accepted at this layer.
    """
    decision = evaluate_publication_gate(client, market_date=market_date, mode=MODE_REQUIRED)
    if not decision.allowed:
        raise PokemonRipStatsUnavailable(
            f"RIP Stats publication authority denied for {market_date}: "
            f"{decision.reason} (reason_code={decision.reason_code}, "
            f"batch_status={decision.batch_status}, promoted_at={decision.promoted_at}, "
            f"missing_set_count={decision.missing_set_count}, "
            f"expected_set_count={decision.expected_set_count})"
        )


def publish_pokemon_rip_stats_snapshot(client: Any, built: Mapping[str, Any]) -> str:
    market_date = str((built.get("snapshot") or {}).get("market_date") or "")[:10]
    if not market_date:
        raise PokemonRipStatsUnavailable("built RIP Stats snapshot has no market_date to authorize")
    _require_publication_authority(client, market_date)
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


#: Returned when the canonical snapshot exists but predates the opening
#: economics methodology, or when no snapshot is published at all. The shape
#: matches the available case field-for-field except that the scopes are null,
#: so a reader never branches on shape - only on `status`.
def _unavailable_opening_economics(reason: str, *, market_date: str | None = None) -> dict[str, Any]:
    return {"status": "unavailable", "reason": reason, "marketDate": market_date,
            "methodologyVersion": POKEMON_RIP_STATS_METHODOLOGY_VERSION,
            "weightingMode": "equal_set_weight", "productFamily": "loose_booster_pack",
            "global": None, "eras": []}


def read_public_opening_economics(client: Any) -> dict[str, Any]:
    """The compact public read for the Overall and Eras lenses.

    Serves ONLY finalized aggregate scalars and the two six-point quantile
    ladders. No simulation artifact, no per-outcome array and no per-set row
    crosses this boundary: the pooled statistics are already final in the
    snapshot, and recomputing any of them downstream is exactly how a
    mean-of-medians reappears.

    An unpublished or pre-methodology snapshot is reported as explicitly
    unavailable rather than being back-filled from per-set scalars.
    """
    try:
        row = read_latest_pokemon_rip_stats(client)
    except PokemonRipStatsUnavailable:
        return _unavailable_opening_economics("snapshot_unavailable")
    payload = row.get("payload_json") or {}
    market_date = str(row.get("market_date") or "")[:10] or None
    economics = payload.get("openingEconomics")
    if not isinstance(economics, Mapping) or not economics.get("global"):
        return _unavailable_opening_economics("opening_economics_not_published", market_date=market_date)
    return {**dict(economics), "marketDate": market_date,
            "snapshotSourceRunFingerprint": row.get("source_run_fingerprint"),
            "updatedAt": row.get("updated_at")}
