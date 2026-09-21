"""Inactive Overall RIP V14 candidate generation for the generic versioned Overall ledger.

Reuses the existing ledger (``pokemon_overall_rip_publication_runs/_rows/_generations/
_generation_rows``) and the generic ``rank_and_tier`` / ``validate_generation`` authority; there
is no second publication system and no V14-specific table or column.

THIS MODULE CANNOT ACTIVATE ANYTHING. It never writes ``pokemon_overall_rip_current_publication``
and never calls ``promote_pokemon_overall_rip_publication``; a candidate is only ever ``staged`` or
``validated``. The current pointer stays on V12 until an explicitly authorized activation step.

A candidate passes validation only when EVERY row is ready (a partially V14-ranked cohort must not
look complete) and the rankings generation is coherent. The run itself is marked passed only when a
set-page generation has also been built; until then it is not promotable (the promote RPC requires
both generations validated).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from backend.db.services.sealed_product_financial_v5_finalization_service import (
    overall_rip_v14_for,
    required_input_versions,
    v14_component_lineage,
)
from backend.desirability.overall_versioned_publication import (
    OverallAuthority,
    project_active,
    rank_and_tier,
    validate_generation,
)
from backend.desirability.scoring_config import (
    OVERALL_RIP_V14_EFFECTIVE_WEIGHTS,
    OVERALL_RIP_V14_VERSION,
    OVERALL_RIP_V14_WEIGHTS,
)

RUNS = "pokemon_overall_rip_publication_runs"
ROWS = "pokemon_overall_rip_publication_rows"
GENERATIONS = "pokemon_overall_rip_publication_generations"
GENERATION_ROWS = "pokemon_overall_rip_publication_generation_rows"
CURRENT_POINTER = "pokemon_overall_rip_current_publication"  # NEVER written by this module

STATUS_STAGED = "staged"
STATUS_VALIDATED = "validated"


def v14_formula_fingerprint() -> str:
    material = json.dumps({"model": OVERALL_RIP_V14_VERSION, "weights": OVERALL_RIP_V14_WEIGHTS,
                           "effective": OVERALL_RIP_V14_EFFECTIVE_WEIGHTS,
                           "inputs": required_input_versions()}, sort_keys=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def cohort_fingerprint(rows: Iterable[Mapping[str, Any]]) -> str:
    ids = sorted(str(r["sealed_product_id"]) for r in rows)
    return hashlib.sha256(",".join(ids).encode("utf-8")).hexdigest()


def build_v14_candidate(
    rows: Sequence[Mapping[str, Any]], *, market_date: str,
    collector_by_set_id: Mapping[str, Mapping[str, Any]],
    accessibility_by_set_id: Mapping[str, Mapping[str, Any]],
    run_id_by_set_id: Mapping[str, str],
    collector_run_id: Optional[str] = None,
    previous_publication_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Pure: publication run + rows + rankings-generation projection for a V14 candidate."""
    versions = required_input_versions()
    material: List[Dict[str, Any]] = []
    for row in rows:
        set_id = str(row.get("set_id") or "")
        expected_run = run_id_by_set_id.get(set_id)
        collector = collector_by_set_id.get(set_id) or {}
        accessibility = accessibility_by_set_id.get(set_id)
        v14 = overall_rip_v14_for(row, collector.get("score"), collector.get("version"), accessibility,
                                  expected_run_id=expected_run)
        ready = v14.get("score") is not None and bool(v14.get("rankable"))
        lineage = (v14_component_lineage(row, accessibility, collector.get("version"))
                   if ready and accessibility else {"financialVersion": row.get("financial_rip_v5_version"),
                                                    "collectorVersion": collector.get("version")})
        material.append({
            "source_result_id": str(row["id"]), "sealed_product_id": str(row["sealed_product_id"]),
            "set_id": set_id, "calculation_run_id": str(row["calculation_run_id"]),
            "score": v14.get("score") if ready else None,
            "eligibility_state": "ready" if ready else str(v14.get("status") or "unavailable_missing_input"),
            "financial_run_id": str(row["calculation_run_id"]),
            "chase_run_id": str(accessibility.get("calculation_run_id")) if ready and accessibility else None,
            "collector_run_id": collector_run_id, "component_lineage": lineage, "authority_json": v14,
        })
    ranked = rank_and_tier(material)
    ready_count = sum(1 for r in ranked if r["eligibility_state"] == "ready")
    run = {
        "model_version": OVERALL_RIP_V14_VERSION, "market_date": market_date, "status": STATUS_STAGED,
        "financial_version": versions["financial"], "chase_version": versions["chase"],
        "collector_version": versions["collector"], "collector_run_id": collector_run_id,
        "formula_fingerprint": v14_formula_fingerprint(), "cohort_fingerprint": cohort_fingerprint(ranked),
        "expected_row_count": len(ranked), "previous_publication_run_id": previous_publication_run_id,
    }
    problems: List[str] = []
    if len(ranked) == 0:
        problems.append("empty_cohort")
    if ready_count != len(ranked):
        problems.append(f"incomplete_v14_cohort: ready={ready_count} of {len(ranked)}")
    return {"run": run, "rows": ranked, "readyCount": ready_count, "problems": problems,
            "cohortComplete": not problems}


def validate_v14_candidate(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    """Coherence validation of the rankings generation (no I/O). Never activates."""
    problems = list(candidate["problems"])
    run, rows = candidate["run"], candidate["rows"]
    authority = OverallAuthority(
        model_version=run["model_version"], publication_run_id="candidate", rankings_generation_id="candidate",
        set_page_generation_id="candidate", market_date=str(run["market_date"]),
        formula_fingerprint=run["formula_fingerprint"], cohort_fingerprint=run["cohort_fingerprint"])
    try:
        validate_generation(authority, rows)
    except ValueError as exc:
        problems.append(str(exc))
    ranks = sorted(r["rank"] for r in rows if r["rank"] is not None)
    if ranks != list(range(1, len(ranks) + 1)):
        problems.append("rank_contiguity")
    if run["model_version"] != OVERALL_RIP_V14_VERSION:
        problems.append("mixed_model_version")
    return {"passed": not problems, "problems": problems, "readyCount": candidate["readyCount"],
            "expectedRowCount": run["expected_row_count"], "modelVersion": run["model_version"]}


def _db_row(row: Mapping[str, Any], run_id: str) -> Dict[str, Any]:
    keys = ("source_result_id", "sealed_product_id", "set_id", "calculation_run_id", "score", "rank", "tier",
            "eligibility_state", "financial_run_id", "chase_run_id", "collector_run_id", "component_lineage",
            "authority_json")
    return {"publication_run_id": run_id, **{k: row.get(k) for k in keys}}


def write_v14_candidate(
    client: Any, candidate: Mapping[str, Any], *,
    set_page_projection_fn: Optional[Callable[[Sequence[Mapping[str, Any]]], Sequence[Mapping[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Persist an INACTIVE candidate. Idempotent per (model, market_date, cohort_fingerprint).

    Statuses only ever reach ``staged``/``validated``. There is no code path here that writes the
    current pointer or calls the promote RPC.
    """
    run = dict(candidate["run"])
    validation = validate_v14_candidate(candidate)
    existing = list(client.table(RUNS).select("id,status").eq("model_version", run["model_version"])
                    .eq("market_date", str(run["market_date"])).eq("cohort_fingerprint", run["cohort_fingerprint"])
                    .execute().data or [])
    if existing:
        if existing[0]["status"] == "published":
            raise ValueError("refusing to rewrite an already-published Overall publication run")
        return {"publicationRunId": existing[0]["id"], "created": False, "status": existing[0]["status"],
                "activated": False, "validation": validation}

    inserted = client.table(RUNS).insert({**run, "status": STATUS_STAGED,
                                          "validation_json": {"passed": False, "phase": "staging"}}).execute()
    run_id = str(inserted.data[0]["id"])
    rows = [_db_row(r, run_id) for r in candidate["rows"]]
    client.table(ROWS).insert(rows).execute()

    authority = OverallAuthority(
        model_version=run["model_version"], publication_run_id=run_id, rankings_generation_id="pending",
        set_page_generation_id="pending", market_date=str(run["market_date"]),
        formula_fingerprint=run["formula_fingerprint"], cohort_fingerprint=run["cohort_fingerprint"])
    rankings_status = STATUS_VALIDATED if validation["passed"] else "building"
    rg = client.table(GENERATIONS).insert({
        "publication_run_id": run_id, "generation_kind": "rankings", "status": rankings_status,
        "expected_row_count": len(rows), "validation_json": validation}).execute()
    rg_id = str(rg.data[0]["id"])
    client.table(GENERATION_ROWS).insert([
        {"generation_id": rg_id, "entity_id": r["source_result_id"],
         "projection_json": {**project_active(authority, r), "authority": r["authority_json"]}}
        for r in candidate["rows"]]).execute()

    set_page = "not_built"
    set_page_ok = False
    if set_page_projection_fn is not None:
        projections = list(set_page_projection_fn(candidate["rows"]))
        sp = client.table(GENERATIONS).insert({
            "publication_run_id": run_id, "generation_kind": "set_page",
            "status": STATUS_VALIDATED if projections else "building",
            "expected_row_count": len(projections), "validation_json": {"passed": bool(projections)}}).execute()
        client.table(GENERATION_ROWS).insert([
            {"generation_id": str(sp.data[0]["id"]), "entity_id": p["entity_id"], "projection_json": p["projection_json"]}
            for p in projections]).execute() if projections else None
        set_page, set_page_ok = "validated" if projections else "building", bool(projections)

    run_passed = validation["passed"] and set_page_ok
    run_validation = {**validation, "passed": run_passed, "setPageGeneration": set_page,
                      "promotable": run_passed}
    if not run_passed and validation["passed"]:
        run_validation["problems"] = list(validation["problems"]) + ["set_page_generation_not_built"]
    client.table(RUNS).update({
        "status": STATUS_VALIDATED if run_passed else STATUS_STAGED, "validation_json": run_validation,
    }).eq("id", run_id).execute()
    return {"publicationRunId": run_id, "created": True, "status": STATUS_VALIDATED if run_passed else STATUS_STAGED,
            "activated": False, "validation": run_validation, "rankingsGenerationId": rg_id}
