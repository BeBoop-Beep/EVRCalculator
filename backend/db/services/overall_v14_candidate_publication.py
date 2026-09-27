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


SET_PAGE_PROJECTION_VERSION = "overall_v14_set_page_projection_v1"


def build_v14_set_page_projections(
    candidate: Mapping[str, Any], *,
    contracts_by_product: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """One Set-page projection per set, built ONLY from the already-ranked candidate rows (no second ranking).

    Each carries the exact authority evidence of the run it belongs to (model, Financial V5 / Chase V1 /
    Collector V5 lineage, market date, cohort and formula fingerprints, Public Contract V12) plus the set's
    products with their V14 score / rank / tier. ``overallPublicationRunId`` is stamped by the writer, so a
    projection cannot be attached to a different run than the one it was built for.
    """
    from backend.desirability.public_rip_contract_v12 import PUBLIC_RIP_CONTRACT_V12_VERSION

    run = candidate["run"]
    by_set: Dict[str, List[Mapping[str, Any]]] = {}
    for row in candidate["rows"]:
        by_set.setdefault(str(row["set_id"]), []).append(row)
    out: List[Dict[str, Any]] = []
    for set_id in sorted(by_set):
        products = []
        for r in sorted(by_set[set_id], key=lambda x: (x["rank"] is None, x["rank"], x["sealed_product_id"])):
            item = {"sealedProductId": r["sealed_product_id"], "sourceResultId": r["source_result_id"],
                    "overallRip": {"score": r["score"], "rank": r["rank"], "tier": r["tier"],
                                   "version": run["model_version"], "eligibility": r["eligibility_state"]},
                    "componentLineage": dict(r.get("component_lineage") or {})}
            if contracts_by_product and r["sealed_product_id"] in contracts_by_product:
                item["publicRipContractV12"] = contracts_by_product[r["sealed_product_id"]]
            products.append(item)
        out.append({"entity_id": set_id, "projection_json": {
            "projectionVersion": SET_PAGE_PROJECTION_VERSION, "setId": set_id,
            "overallModelVersion": run["model_version"], "financialModelVersion": run["financial_version"],
            "chaseVersion": run["chase_version"], "collectorVersion": run["collector_version"],
            "marketDate": str(run["market_date"]), "cohortFingerprint": run["cohort_fingerprint"],
            "formulaFingerprint": run["formula_fingerprint"], "publicRipContractVersion": PUBLIC_RIP_CONTRACT_V12_VERSION,
            "productCount": len(products), "products": products}})
    return out


def validate_v14_set_page_projections(
    candidate: Mapping[str, Any], projections: Sequence[Mapping[str, Any]], *, run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Coherence of a Set-page generation with its candidate run. No I/O, never activates."""
    from backend.desirability.public_rip_contract_v12 import PUBLIC_RIP_CONTRACT_V12_VERSION

    run, rows = candidate["run"], candidate["rows"]
    problems: List[str] = []
    ids = [str(p["entity_id"]) for p in projections]
    if len(set(ids)) != len(ids):
        problems.append("duplicate_entity_ids")
    expected = {str(r["set_id"]) for r in rows}
    if set(ids) != expected:
        problems.append("entity_set_mismatch: missing=%s extra=%s" % (sorted(expected - set(ids))[:3], sorted(set(ids) - expected)[:3]))
    seen_products = []
    for p in projections:
        j = p["projection_json"]
        for key, want in (("overallModelVersion", run["model_version"]), ("financialModelVersion", run["financial_version"]),
                          ("chaseVersion", run["chase_version"]), ("collectorVersion", run["collector_version"]),
                          ("cohortFingerprint", run["cohort_fingerprint"]), ("formulaFingerprint", run["formula_fingerprint"]),
                          ("marketDate", str(run["market_date"])), ("publicRipContractVersion", PUBLIC_RIP_CONTRACT_V12_VERSION)):
            if j.get(key) != want:
                problems.append(f"{p['entity_id']}: {key}={j.get(key)!r}")
        if run_id is not None and j.get("overallPublicationRunId") != run_id:
            problems.append(f"{p['entity_id']}: mixed publication-run authority")
        for item in j.get("products") or []:
            seen_products.append(item["sealedProductId"])
            o = item["overallRip"]
            if o["version"] != run["model_version"]:
                problems.append(f"{item['sealedProductId']}: mixed Overall model")
            if o["eligibility"] == "ready" and (o["score"] is None or o["rank"] is None or o["tier"] is None):
                problems.append(f"{item['sealedProductId']}: ready without score/rank/tier")
            contract = item.get("publicRipContractV12")
            if contract is not None and (contract.get("contractVersion") != PUBLIC_RIP_CONTRACT_V12_VERSION
                                         or (contract.get("overallRipV14") or {}).get("status") != "ready"
                                         or (contract.get("financialRipV5") or {}).get("status") != "ready"):
                problems.append(f"{item['sealedProductId']}: contract V12 not valid/ready")
    if sorted(seen_products) != sorted(str(r["sealed_product_id"]) for r in rows):
        problems.append("products_do_not_cover_the_candidate_cohort_exactly_once")
    return {"passed": not problems, "problems": problems, "entityCount": len(ids), "expectedEntityCount": len(expected)}


def write_v14_candidate(
    client: Any, candidate: Mapping[str, Any], *,
    set_page_projection_fn: Optional[Callable[[Sequence[Mapping[str, Any]]], Sequence[Mapping[str, Any]]]] = None,
    set_page_validator_fn: Optional[Callable[..., Mapping[str, Any]]] = None,
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
        # Bind every projection to THIS run: a projection cannot be attached to another run's authority.
        projections = [{"entity_id": p["entity_id"],
                        "projection_json": {**p["projection_json"], "overallPublicationRunId": run_id}}
                       for p in set_page_projection_fn(candidate["rows"])]
        sp_validation: Mapping[str, Any] = {"passed": bool(projections)}
        if set_page_validator_fn is not None:
            sp_validation = set_page_validator_fn(candidate, projections, run_id=run_id)
        sp_ok = bool(projections) and bool(sp_validation.get("passed"))
        sp = client.table(GENERATIONS).insert({
            "publication_run_id": run_id, "generation_kind": "set_page",
            "status": STATUS_VALIDATED if sp_ok else "building",
            "expected_row_count": len(projections), "validation_json": dict(sp_validation)}).execute()
        if projections:
            client.table(GENERATION_ROWS).insert([
                {"generation_id": str(sp.data[0]["id"]), "entity_id": p["entity_id"], "projection_json": p["projection_json"]}
                for p in projections]).execute()
        set_page, set_page_ok = ("validated" if sp_ok else "building"), sp_ok

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
