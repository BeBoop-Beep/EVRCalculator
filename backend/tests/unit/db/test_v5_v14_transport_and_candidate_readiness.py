"""Identity transport (V14 / contract V12 registered, not selected) and candidate readiness."""
import copy

import pytest

from backend.calculations.evr.best_open_price_v3 import BEST_OPEN_PRICE_V3_METHOD_VERSION
from backend.db.services import public_rip_publication_contract as pubc
from backend.db.services import rankings_publication_lifecycle as lifecycle
from backend.db.services import v5_v14_candidate_readiness as ready
from backend.desirability import scoring_config as sc
from backend.desirability.public_rip_contract_v11 import PUBLIC_RIP_CONTRACT_V11_KEY
from backend.desirability.public_rip_contract_v12 import PUBLIC_RIP_CONTRACT_V12_KEY, PUBLIC_RIP_CONTRACT_V12_VERSION
from backend.scripts import pokemon_explore_rankings_publisher as publisher

N = 138


# ------------------------------------------------------------------ transport

def test_runtime_still_resolves_the_current_v12_v11_lineage():
    assert pubc.canonical_overall_rip_target_key() == "overallRipV12"
    assert publisher._canonical_public_rip_contract_target_key() == PUBLIC_RIP_CONTRACT_V11_KEY
    ident = pubc.canonical_publication_identity()
    assert ident["financialRipVersion"] == sc.FINANCIAL_RIP_V4_VERSION
    assert ident["overallRipVersion"] == sc.OVERALL_RIP_V12_VERSION
    assert ident["publicRipContractVersion"] == "public_rip_contract_v11"


def test_candidate_lineage_is_registered_and_distinct_from_canonical():
    assert pubc.candidate_overall_rip_target_key() == "overallRipV14"
    cand = pubc.candidate_publication_identity()
    assert cand["overallRipVersion"] == sc.OVERALL_RIP_V14_VERSION
    assert cand["publicRipContractVersion"] == PUBLIC_RIP_CONTRACT_V12_VERSION
    assert cand["financialRipVersion"] != pubc.canonical_publication_identity()["financialRipVersion"]
    assert publisher._CANONICAL_PUBLIC_RIP_CONTRACT_TARGET_KEYS[sc.OVERALL_RIP_V14_VERSION] == PUBLIC_RIP_CONTRACT_V12_KEY


def test_a_controlled_canonical_flip_resolves_one_source_of_truth_and_unregistered_versions_fail_closed(monkeypatch):
    monkeypatch.setattr(pubc, "CANONICAL_OVERALL_RIP_VERSION", sc.OVERALL_RIP_V14_VERSION)
    monkeypatch.setattr(publisher, "CANONICAL_OVERALL_RIP_VERSION", sc.OVERALL_RIP_V14_VERSION)
    assert pubc.canonical_overall_rip_target_key() == "overallRipV14"
    assert publisher._canonical_public_rip_contract_target_key() == PUBLIC_RIP_CONTRACT_V12_KEY
    monkeypatch.setattr(pubc, "CANONICAL_OVERALL_RIP_VERSION", "overall_rip_v99_unregistered")
    with pytest.raises(RuntimeError, match="No registered publisher target key"):
        pubc.canonical_overall_rip_target_key()


def _row(identity, fingerprint="fp"):
    return {"financial_rip_version": identity["financialRipVersion"], "overall_rip_version": identity["overallRipVersion"],
            "publication_status": "complete", "published_at": "2026-09-20T00:00:00+00:00", "eligible_cohort_count": N,
            "diagnostics_json": {"public_rip_contract_version": identity["publicRipContractVersion"],
                                 "collector_appeal_version": identity["collectorAppealVersion"],
                                 "supported_cohort_fingerprint": fingerprint}}


def _stale(row, **kw):
    return pubc.evaluate_leaderboard_staleness(row, ranked_row_count=N, cohort={"fingerprint": "fp", "count": N}, **kw)


def test_semantic_staleness_is_model_identity_not_timestamps_for_both_lineages():
    canonical, candidate = pubc.canonical_publication_identity(), pubc.candidate_publication_identity()
    assert _stale(_row(canonical)) == []                                              # default: unchanged behavior
    assert _stale(_row(candidate), expected_identity=candidate) == []                 # candidate is current for itself
    codes = {r["code"] for r in _stale(_row(canonical), expected_identity=candidate)}
    assert {pubc.REASON_FINANCIAL_VERSION, pubc.REASON_OVERALL_VERSION, pubc.REASON_CONTRACT_VERSION} <= codes
    assert _stale(_row(candidate))  # a candidate-identity row is NOT current for the canonical check


# ------------------------------------------------------------------ candidate readiness

def _good():
    ident = pubc.candidate_publication_identity()
    v5 = {"cohortComplete": True, "financialVersion": ident["financialRipVersion"], "rowsReady": N,
          "rowsUnavailable": 0, "rowsSkipped": 0}
    run = {"model_version": sc.OVERALL_RIP_V14_VERSION, "financial_version": ident["financialRipVersion"],
           "collector_version": ident["collectorAppealVersion"], "expected_row_count": N}
    v14 = {"run": run, "readyCount": N, "problems": [], "cohortComplete": True}
    ranking = {"id": "r2", "ranking_method_version": "budget_product_ranking_v2", "published_at": "t", "cohort_fingerprint": "f",
               "overall_rip_v14_version": sc.OVERALL_RIP_V14_VERSION, "financial_rip_v5_version": ident["financialRipVersion"],
               "ranked_under_v14_authority": True, "eligible_cohort_count": N}
    bo = {"best_open_price_method_version": BEST_OPEN_PRICE_V3_METHOD_VERSION, "overall_rip_v14_version": sc.OVERALL_RIP_V14_VERSION,
          "source_budget_snapshot_id": "r2", "source_budget_published_at": "t", "source_cohort_fingerprint": "f",
          "resolved_count": N, "unresolved_count": 0}
    contract = {"contractVersion": PUBLIC_RIP_CONTRACT_V12_VERSION,
                "overallRipV14": {"status": "ready", "score": 70.0, "rank": 1},
                "financialRipV5": {"status": "ready", "score": 50.0, "rank": 1}}
    return dict(expected_row_count=N, v5_finalization_report=v5, v14_candidate=v14, v14_validation={"passed": True},
                ranking_v2=ranking, best_open_v3=bo, contract_v12_samples=[contract])


def test_a_complete_coherent_candidate_is_ready_without_activating_anything():
    r = ready.evaluate_v5_v14_candidate_readiness(**_good())
    assert r["candidateReady"] is True and r["reasons"] == [] and r["activated"] is False
    assert r["canonicalImpact"] == "none" and r["canonicalIdentity"] == pubc.canonical_publication_identity()
    assert sc.CANONICAL_OVERALL_RIP_VERSION == sc.OVERALL_RIP_V12_VERSION


@pytest.mark.parametrize("mutate,check", [
    (lambda k: k["v5_finalization_report"].update(cohortComplete=False, rowsUnavailable=1, rowsReady=N - 1), "financialV5Complete"),
    (lambda k: k.update(v5_finalization_report=None), "financialV5Complete"),
    (lambda k: k["v14_candidate"].update(readyCount=N - 1, problems=["incomplete_v14_cohort"]), "overallV14Complete"),
    (lambda k: k["v14_candidate"]["run"].update(financial_version=sc.FINANCIAL_RIP_V4_VERSION), "overallV14Complete"),
    (lambda k: k.update(v14_candidate=None), "overallV14Complete"),
    (lambda k: k["ranking_v2"].update(ranking_method_version="budget_product_ranking_v1"), "rankingV2Complete"),
    (lambda k: k["ranking_v2"].update(eligible_cohort_count=N - 1), "rankingV2Complete"),
    (lambda k: k.update(ranking_v2=None), "rankingV2Complete"),
    (lambda k: k["best_open_v3"].update(source_budget_snapshot_id="old"), "bestOpenV3Complete"),
    (lambda k: k["best_open_v3"].update(source_cohort_fingerprint="other"), "bestOpenV3Complete"),
    (lambda k: k["best_open_v3"].update(best_open_price_method_version="budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12"), "bestOpenV3Complete"),
    (lambda k: k["best_open_v3"].update(unresolved_count=1), "bestOpenV3Complete"),
    (lambda k: k.update(best_open_v3=None), "bestOpenV3Complete"),
    (lambda k: k["contract_v12_samples"][0].update(contractVersion="public_rip_contract_v11"), "publicContractV12Valid"),
    (lambda k: k["contract_v12_samples"][0]["overallRipV14"].update(status="unavailable_inconsistent_lineage", score=None), "publicContractV12Valid"),
    (lambda k: k.update(contract_v12_samples=[]), "publicContractV12Valid")])
def test_each_missing_or_incoherent_piece_blocks_readiness(mutate, check):
    kw = copy.deepcopy(_good())
    mutate(kw)
    r = ready.evaluate_v5_v14_candidate_readiness(**kw)
    assert r["candidateReady"] is False and r["checks"][check]["ok"] is False
    assert r["canonicalImpact"] == "none"


def test_best_open_v3_can_be_explicitly_waived_but_a_wrong_one_still_fails():
    kw = _good()
    kw["best_open_v3"] = None
    assert ready.evaluate_v5_v14_candidate_readiness(**kw, require_best_open_v3=False)["candidateReady"] is True
    kw["best_open_v3"] = dict(_good()["best_open_v3"], source_budget_snapshot_id="stale")
    assert ready.evaluate_v5_v14_candidate_readiness(**kw, require_best_open_v3=False)["candidateReady"] is False


def test_candidate_and_canonical_readiness_coexist_independently():
    absent = ready.evaluate_v5_v14_candidate_readiness(expected_row_count=N)
    assert absent["candidateReady"] is False and absent["canonicalImpact"] == "none"
    # the canonical lineage is asked separately and is unaffected by the candidate's absence
    assert _stale(_row(pubc.canonical_publication_identity())) == []
    delegated = lifecycle.evaluate_candidate_generation_readiness(**_good())
    assert delegated["candidateReady"] is True and delegated["readinessVersion"] == ready.READINESS_VERSION
