"""Production infrastructure for Treatment Market Prestige V3.

Builders create candidates only. Approval is a separate explicit database RPC.
Request-time resolution performs no score calculation and fails closed.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from backend.db.clients.supabase_client import supabase
from backend.desirability.treatment_market_prestige_v3 import normalize_label, stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round7 import load_freeze
from backend.scripts.build_treatment_market_prestige_v3_round8 import matrices, rerun, verify_inputs

ROOT = Path("docs/research")
R4 = ROOT / "treatment_market_prestige_v3_round4_study.json"
R5 = ROOT / "treatment_market_prestige_v3_round5_study.json"
R6 = ROOT / "treatment_market_prestige_v3_round6_study.json"
R7 = ROOT / "treatment_market_prestige_v3_round7_study.json"
R8 = ROOT / "treatment_market_prestige_v3_round8_study.json"

MODEL_VERSION = "treatment_market_prestige_v3_hierarchical_eb_v1"
METHODOLOGY_VERSION = "treatment_market_prestige_v3_round8"
SCORE_TRANSFORM_VERSION = "frozen_baseline_robust_logistic_v1"
PRODUCTION_CONTRACT_HASH = "fd7cdfb3e8dcba9d18e18390e482542be6d68cd11927ec3998e2412e4e2b0862"
BASELINE_VERSION = "6c1ae19217ee8758057bf251aa60d26a397f66319729f1abbff51e21424cdbf4"
STALE_MARKET_DAYS = 45
STALE_PUBLICATION_DAYS = 62


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(query: Any) -> list[dict[str, Any]]:
    return list(query.execute().data or [])


def build_candidate_payload(*, bootstrap_draws: int = 399) -> dict[str, Any]:
    """Recompute one deterministic candidate from the validated frozen inputs."""
    if bootstrap_draws != 399:
        raise ValueError("the validated production contract requires exactly 399 bootstrap draws")
    r4, r5, r6, r7, r8 = (_json(p) for p in (R4, R5, R6, R7, R8))
    manifest, data, verified = verify_inputs(r4, r5, r6, r7)
    _series, audits, readiness = rerun(data, r4, bootstrap_draws)
    treatment_matrix, universe_matrix = matrices(readiness)
    reference_date = max(x["manifest"]["reference_date"] for snapshots in data.values() for x in snapshots)
    era_ids: dict[str, str] = {}
    for snapshots in data.values():
        for row in snapshots[-1]["rows"]:
            era_ids.setdefault(str(row["era_name"]), str(row["era_id"]))
    universes = []
    for item in universe_matrix:
        era_id = era_ids.get(item["era"])
        if not era_id:
            raise RuntimeError(f"missing canonical era identity for {item['era']}")
        universes.append({
            "universe_key": item["universeId"], "era_id": era_id, "era_name": item["era"],
            "comparison_universe_type": item["universeType"],
            "treatment_regime_id": item["universeId"] if item["universeType"] == "TREATMENT_REGIME_RELATIVE" else None,
            "treatment_count": item["treatmentCount"], "eligible_treatment_count": item["eligibleTreatmentCount"],
            "final_availability_status": item["publicationStatus"], "failure_reason": item["failureReason"],
        })
    results = []
    for item in treatment_matrix:
        current = readiness[item["universeId"]]["current_model"]["effects"][item["treatmentKey"]]
        results.append({
            "universe_key": item["universeId"], "era_id": era_ids[item["era"]], "era_name": item["era"],
            "comparison_universe_type": "TREATMENT_REGIME_RELATIVE" if item["regimeId"] else "ERA_RELATIVE",
            "treatment_regime_id": item["regimeId"], "treatment_key": item["treatmentKey"],
            "treatment_label": item["treatmentLabel"], "treatment_effect": current["population_effect"],
            "magnitude_score": item["score"],
            "score_interval_low": item["scoreInterval"][0] if item["scoreInterval"] else None,
            "score_interval_high": item["scoreInterval"][1] if item["scoreInterval"] else None,
            "confidence_status": "HIGH_UNCERTAINTY" if item["heterogeneityStatus"] == "HIGH_HETEROGENEITY" else "STANDARD",
            "evidence_status": item["evidenceStatus"],
            "ordering_metadata": readiness[item["universeId"]]["current_model"].get("ordering_probabilities", {}),
            "card_count": item["cardCount"], "species_count": item["speciesCount"], "set_count": item["setCount"],
            "temporal_checkpoint_count": item["temporalCheckpointCount"], "temporal_span_days": item["temporalSpanDays"],
            "between_set_variance": current["between_set_variance"], "heterogeneity_status": item["heterogeneityStatus"],
            "temporal_status": item["temporalStatus"], "final_availability_status": item["finalAvailabilityStatus"],
            "market_reference_date": reference_date,
            "provenance": {"round8StudyId": r8["study_id"], "round7StudyId": r7["study_id"], "frozenInputHash": manifest["study_hash"]},
        })
    regime_sets = []
    for universe in universes:
        if universe["comparison_universe_type"] != "TREATMENT_REGIME_RELATIVE":
            continue
        definition = readiness.get(universe["universe_key"], {}).get("definition")
        for set_id in (definition or {}).get("set_ids") or []:
            regime_sets.append({"universe_key": universe["universe_key"], "treatment_regime_id": universe["treatment_regime_id"], "set_id": set_id})
    available_results = sum(x["final_availability_status"] == "AVAILABLE" for x in results)
    available_universes = sum(x["final_availability_status"] == "AVAILABLE" for x in universes)
    run = {
        "model_version": MODEL_VERSION, "methodology_version": METHODOLOGY_VERSION,
        "score_transform_version": SCORE_TRANSFORM_VERSION, "baseline_version": BASELINE_VERSION,
        "market_reference_date": reference_date, "built_at": f"{reference_date}T23:59:59+00:00",
        "approval_status": "candidate", "approved": False,
        "cohort_source_hash": manifest["study_hash"], "taxonomy_hash": verified["taxonomy_hash"],
        "comparison_universe_hash": verified["definition_hash"], "production_contract_hash": PRODUCTION_CONTRACT_HASH,
        "canonical_mapping_hash": verified["canonical_mapping_hash"], "candidate_validation_status": "passed",
        "expected_treatment_count": len(results), "expected_universe_count": len(universes),
        "expected_available_treatment_count": available_results, "expected_available_universe_count": available_universes,
        "temporal_validation_metadata": audits,
        "validation_metadata": {"frozenInputs": verified, "round8Coverage": r8["catalog_coverage"]},
        "failure_reason": None, "source_study_id": r8["study_id"],
    }
    payload = {"run": run, "universes": universes, "results": results, "regimeSets": regime_sets}
    payload["candidateHash"] = stable_json_hash(payload)
    return payload


def stage_candidate(payload: Mapping[str, Any], *, client: Any = None) -> str:
    active = client or supabase
    expected = stable_json_hash({k: payload[k] for k in ("run", "universes", "results", "regimeSets")})
    if payload.get("candidateHash") != expected:
        raise RuntimeError("candidate hash mismatch")
    response = active.rpc("stage_treatment_market_prestige_v3_candidate", {
        "p_run": payload["run"], "p_universes": payload["universes"],
        "p_results": payload["results"], "p_regime_sets": payload["regimeSets"],
    }).execute()
    value = response.data
    return str(value[0] if isinstance(value, list) else value)


def approve_candidate(run_id: str, *, approval_actor: str, approval_metadata: Optional[Mapping[str, Any]] = None,
                      client: Any = None) -> str:
    if not approval_actor.strip():
        raise ValueError("approval_actor is required")
    active = client or supabase
    response = active.rpc("approve_treatment_market_prestige_v3_candidate", {
        "p_run_id": run_id, "p_production_contract_hash": PRODUCTION_CONTRACT_HASH,
        "p_approval_actor": approval_actor, "p_approval_metadata": dict(approval_metadata or {}),
    }).execute()
    value = response.data
    return str(value[0] if isinstance(value, list) else value)


def _unavailable(status: str, *, treatment_key: Optional[str] = None) -> dict[str, Any]:
    return {"status": status, "modelVersion": None, "methodologyVersion": METHODOLOGY_VERSION,
            "asOfDate": None, "eraId": None, "eraName": None, "comparisonUniverseType": None,
            "treatmentRegimeId": None, "treatmentKey": treatment_key, "treatmentLabel": None,
            "score": None, "scoreDisplay": None, "scoreInterval": None, "confidence": None,
            "evidenceStatus": status, "cardCount": None, "setCount": None, "comparisonUniverseSize": None}


def _approved_run_state(client: Any, today: date) -> str:
    try:
        rows = _rows(client.table("treatment_market_prestige_publication_runs")
                     .select("production_contract_hash,baseline_version,market_reference_date,approved_at")
                     .eq("approval_status", "approved").order("market_reference_date", desc=True)
                     .order("approved_at", desc=True).limit(1))
    except Exception:
        return "NO_APPROVED_RUN"
    if not rows:
        return "NO_APPROVED_RUN"
    row = rows[0]
    if row.get("production_contract_hash") != PRODUCTION_CONTRACT_HASH or row.get("baseline_version") != BASELINE_VERSION:
        return "NO_APPROVED_RUN"
    market_date = date.fromisoformat(str(row["market_reference_date"])[:10])
    approved_date = datetime.fromisoformat(str(row["approved_at"]).replace("Z", "+00:00")).date()
    return "MODEL_STALE" if (today-market_date).days > STALE_MARKET_DAYS or (today-approved_date).days > STALE_PUBLICATION_DAYS else "AVAILABLE"


def resolve_card_treatment_market_prestige(*, set_id: str, era_id: Optional[str], rarity: Any,
                                            client: Any = None, today: Optional[date] = None) -> dict[str, Any]:
    active = client or supabase; treatment_key = normalize_label(rarity)
    if not treatment_key:
        return _unavailable("TAXONOMY_UNMAPPED")
    run_state = _approved_run_state(active, today or datetime.now(timezone.utc).date())
    if run_state != "AVAILABLE":
        return _unavailable(run_state, treatment_key=treatment_key)
    if not era_id:
        return _unavailable("TAXONOMY_UNMAPPED", treatment_key=treatment_key)
    try:
        rows = _rows(active.table("latest_approved_treatment_market_prestige").select("*").eq("era_id", era_id))
    except Exception:
        return _unavailable("NO_APPROVED_RUN", treatment_key=treatment_key)
    if not rows:
        return _unavailable("INSUFFICIENT_ERA_SUPPORT", treatment_key=treatment_key)
    candidates = [r for r in rows if r.get("treatment_key") == treatment_key]
    if not candidates:
        return _unavailable("NEW_TREATMENT_RESEARCHING", treatment_key=treatment_key)
    chosen = next((r for r in candidates if r.get("comparison_universe_type") == "ERA_RELATIVE"), None)
    if chosen is None:
        chosen = next((r for r in candidates if str(r.get("set_id")) == str(set_id)), None)
    if chosen is None:
        return _unavailable("INSUFFICIENT_REGIME_SUPPORT", treatment_key=treatment_key)
    final = str(chosen.get("final_availability_status") or "INSUFFICIENT_TREATMENT_SUPPORT")
    if final != "AVAILABLE" or chosen.get("universe_availability_status") != "AVAILABLE" or chosen.get("magnitude_score") is None:
        status = str(chosen.get("universe_availability_status") or final)
        return _unavailable(status, treatment_key=treatment_key)
    score = float(chosen["magnitude_score"]); low=float(chosen["score_interval_low"]); high=float(chosen["score_interval_high"])
    return {"status":"AVAILABLE","modelVersion":chosen.get("model_version"),"methodologyVersion":chosen.get("methodology_version"),
            "asOfDate":str(chosen.get("market_reference_date")),"eraId":str(chosen.get("era_id")),"eraName":chosen.get("era_name"),
            "comparisonUniverseType":chosen.get("comparison_universe_type"),"treatmentRegimeId":chosen.get("treatment_regime_id"),
            "treatmentKey":treatment_key,"treatmentLabel":chosen.get("treatment_label"),"score":score,"scoreDisplay":f"{score:.1f}",
            "scoreInterval":{"low":low,"high":high},"confidence":chosen.get("confidence_status"),"evidenceStatus":chosen.get("evidence_status"),
            "cardCount":chosen.get("card_count"),"setCount":chosen.get("set_count"),"comparisonUniverseSize":chosen.get("comparison_universe_size")}
