"""V14 Set-page generation: bound to one run, complete, validated, and still inactive."""
import copy

from backend.db.services import overall_v14_candidate_publication as cand
from backend.desirability import scoring_config as sc
from backend.tests.unit.db.test_overall_v14_finalization_and_candidate import ACC, COLLECTOR_V5, FakeClient, _row


def _candidate(sets=("set-a", "set-b"), per_set=2, break_row=None):
    rows, i = [], 1
    for s in sets:
        for _ in range(per_set):
            rows.append(dict(_row(i, score=70.0 - i), set_id=s, calculation_run_id=f"run-{s}"))
            i += 1
    if break_row is not None:
        rows[break_row]["financial_rip_v5_score"] = None
    coll = {s: {"score": 60.0, "version": COLLECTOR_V5} for s in sets}
    acc = {s: dict(ACC, calculation_run_id=f"run-{s}") for s in sets}
    runs = {s: f"run-{s}" for s in sets}
    return cand.build_v14_candidate(rows, market_date="2026-09-15", collector_by_set_id=coll,
                                    accessibility_by_set_id=acc, run_id_by_set_id=runs)


def _contract_ok():
    return {"contractVersion": "public_rip_contract_v12", "overallRipV14": {"status": "ready"},
            "financialRipV5": {"status": "ready"}}


def test_projection_is_built_only_from_ranked_rows_and_carries_the_full_authority_evidence():
    c = _candidate()
    proj = cand.build_v14_set_page_projections(c)
    assert [p["entity_id"] for p in proj] == ["set-a", "set-b"]
    j = proj[0]["projection_json"]
    run = c["run"]
    assert (j["overallModelVersion"], j["financialModelVersion"], j["chaseVersion"], j["collectorVersion"]) == (
        sc.OVERALL_RIP_V14_VERSION, run["financial_version"], run["chase_version"], run["collector_version"])
    assert j["cohortFingerprint"] == run["cohort_fingerprint"] and j["publicRipContractVersion"] == "public_rip_contract_v12"
    ledger = {r["sealed_product_id"]: r for r in c["rows"]}
    for item in j["products"]:  # values are the candidate's own ranking, not recomputed
        r = ledger[item["sealedProductId"]]
        assert (item["overallRip"]["score"], item["overallRip"]["rank"], item["overallRip"]["tier"]) == (r["score"], r["rank"], r["tier"])
    assert "overallPublicationRunId" not in j  # stamped by the writer, never guessed here


def test_a_complete_generation_validates_and_lets_the_run_reach_validated_but_never_active():
    c = _candidate()
    client = FakeClient()
    out = cand.write_v14_candidate(
        client, c, set_page_projection_fn=lambda rows: cand.build_v14_set_page_projections(c),
        set_page_validator_fn=cand.validate_v14_set_page_projections)
    assert out["status"] == "validated" and out["validation"]["promotable"] is True and out["activated"] is False
    assert cand.CURRENT_POINTER not in {t for t, *_ in client.calls} and not client.rpcs
    sets = [p for t, op, p, _ in client.calls if t == cand.GENERATIONS and op == "insert"]
    assert {g["generation_kind"] for g in sets} == {"rankings", "set_page"} and all(g["status"] == "validated" for g in sets)
    written = [row for t, op, rows, _ in client.calls if t == cand.GENERATION_ROWS and op == "insert" for row in rows]
    run_ids = {r["projection_json"].get("overallPublicationRunId") for r in written if "projectionVersion" in r["projection_json"]}
    assert len(run_ids) == 1 and None not in run_ids  # every set page bound to the SAME run


def test_validation_catches_each_authority_defect():
    c = _candidate()
    good = cand.build_v14_set_page_projections(c)
    assert cand.validate_v14_set_page_projections(c, good)["passed"] is True

    def bad(mutate, expect):
        p = copy.deepcopy(good)
        mutate(p)
        r = cand.validate_v14_set_page_projections(c, p, run_id="R")
        assert r["passed"] is False and any(expect in x for x in r["problems"]), (expect, r["problems"])
    bad(lambda p: p.append(copy.deepcopy(p[0])), "duplicate_entity_ids")
    bad(lambda p: p.pop(), "entity_set_mismatch")
    bad(lambda p: p[0]["projection_json"].update(overallModelVersion=sc.OVERALL_RIP_V12_VERSION), "overallModelVersion")
    bad(lambda p: p[0]["projection_json"].update(financialModelVersion=sc.FINANCIAL_RIP_V4_VERSION), "financialModelVersion")
    bad(lambda p: p[0]["projection_json"].update(publicRipContractVersion="public_rip_contract_v11"), "publicRipContractVersion")
    bad(lambda p: p[0]["projection_json"].update(cohortFingerprint="other"), "cohortFingerprint")
    bad(lambda p: p[0]["projection_json"].update(overallPublicationRunId="other-run"), "mixed publication-run authority")
    bad(lambda p: p[0]["projection_json"]["products"].pop(), "products_do_not_cover")
    bad(lambda p: p[0]["projection_json"]["products"][0]["overallRip"].update(version=sc.OVERALL_RIP_V12_VERSION), "mixed Overall model")
    bad(lambda p: p[0]["projection_json"]["products"][0]["overallRip"].update(rank=None), "ready without score/rank/tier")


def test_contract_v12_blocks_are_validated_when_present():
    c = _candidate()
    pid = c["rows"][0]["sealed_product_id"]
    ok = cand.build_v14_set_page_projections(c, contracts_by_product={pid: _contract_ok()})
    assert cand.validate_v14_set_page_projections(c, ok)["passed"] is True
    broken = dict(_contract_ok(), contractVersion="public_rip_contract_v11")
    bad = cand.build_v14_set_page_projections(c, contracts_by_product={pid: broken})
    assert cand.validate_v14_set_page_projections(c, bad)["passed"] is False


def test_partial_cohort_or_failed_set_page_validation_keeps_the_run_staged():
    partial = _candidate(break_row=0)
    out = cand.write_v14_candidate(FakeClient(), partial, set_page_projection_fn=lambda r: cand.build_v14_set_page_projections(partial),
                                   set_page_validator_fn=cand.validate_v14_set_page_projections)
    assert out["status"] == "staged" and out["validation"]["promotable"] is False
    c = _candidate()
    client = FakeClient()
    out2 = cand.write_v14_candidate(client, c, set_page_projection_fn=lambda r: cand.build_v14_set_page_projections(c)[:1],
                                    set_page_validator_fn=cand.validate_v14_set_page_projections)
    assert out2["status"] == "staged" and out2["validation"]["setPageGeneration"] == "building"
    assert cand.CURRENT_POINTER not in {t for t, *_ in client.calls}
