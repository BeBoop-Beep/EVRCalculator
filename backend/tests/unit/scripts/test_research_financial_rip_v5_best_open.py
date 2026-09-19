import numpy as np
import pytest

from backend.calculations.evr.best_open_price import ExactBestOpenPriceSearch, PreparedCanonicalCandidate
from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.calculations.evr.financial_rip_v5_candidate import score_financial_rip_v5_candidate
from backend.scripts.research_financial_rip_v5_best_open import (
    FINANCIAL_V5, OVERALL_V5, PriceCollector, PreparedV5Candidate,
    atomic_json, control_complete_for_candidate, financial_v5_key,
    load_matching_checkpoint, overall_shadow,
    overall_v5_key,
)


def test_truthful_fields_and_shadow_isolated_from_v12():
    prepared = PreparedFinancialRipDistribution.prepare(np.array([.2, 1, 2, 5] * 2500))
    collector = PriceCollector()
    candidate = PreparedV5Candidate("p", 1, prepared, 70, .001, 10)
    candidate.collector = collector
    scored = candidate.score_candidate(100)
    assert scored["overallShadowVersion"] == "OVERALL_RIP_FINANCIAL_V5_SHADOW"
    assert scored["financialRipV4Score"] != scored["financialRipV5CandidateScore"]
    assert scored["overallRipV12Score"] != scored["overallRipFinancialV5ShadowScore"]
    assert scored["overallRipFinancialV5ShadowScore"] == overall_shadow(
        scored["financialRipV5CandidateScore"], .001, 70)
    assert collector.summary()["distinctCandidatePrices"] == 1
    assert candidate.score_candidate(100) == scored
    assert collector.summary()["distinctCandidatePrices"] == 1


def test_candidate_comparators_use_candidate_fields():
    a = {"sealedProductId": "a", "financialRipV4Score": 1,
         "financialRipV5CandidateScore": 60, "overallRipV12Score": 1,
         "overallRipFinancialV5ShadowScore": 70, "chanceToRecoverCapital": .2,
         "actualCommittedCapital": 8, "targetBudget": 10}
    b = {**a, "sealedProductId": "b", "financialRipV4Score": 100,
         "financialRipV5CandidateScore": 59, "overallRipV12Score": 100,
         "overallRipFinancialV5ShadowScore": 69}
    assert financial_v5_key(a) < financial_v5_key(b)
    assert overall_v5_key(a) < overall_v5_key(b)
    prepared = PreparedFinancialRipDistribution.prepare(np.array([.2, 1, 2, 5] * 2500))
    candidate = PreparedV5Candidate("a", 1, prepared, 70, .001, 10)
    assert candidate.compare(a, b, authority=FINANCIAL_V5)
    assert candidate.compare(a, b, authority=OVERALL_V5)


@pytest.mark.parametrize("price_cents", [25, 100, 275, 1000])
def test_one_pass_candidate_matches_frozen_three_pass_numeric_record(price_cents):
    values = np.random.default_rng(704).choice([0, .2, .6, 1, 3, 15], 10001)
    prepared = PreparedFinancialRipDistribution.prepare(values)
    candidate = PreparedV5Candidate("p", 1, prepared, 70, .001, 10)
    new = candidate.score_candidate(price_cents)
    old_control = PreparedCanonicalCandidate.score_candidate(candidate, price_cents)
    cost = old_control["actualCommittedCapital"]
    old_v5 = score_financial_rip_v5_candidate(prepared, cost)
    old_v3 = prepared.score(cost)
    expected = {
        **{key: value for key, value in old_control.items() if key != "scoringSeconds"},
        "financialRipV5CandidateScore": old_v5["score"],
        "overallRipFinancialV5ShadowScore": overall_shadow(old_v5["score"], .001, 70),
        "typicalRetentionScore": old_v5["components"]["typical_retention"]["score"],
        "trueWinFrequencyScore": old_v5["components"]["true_win_frequency"]["score"],
        "lossResilienceScore": old_v3["components"]["loss_resilience"]["score"],
        "shortfallResilienceScore": old_v5["components"]["shortfall_resilience"]["score"],
        "baseEconomicEfficiencyScore": old_v5["components"]["base_economic_efficiency"]["score"],
        "cappedRecovery": old_v5["components"]["shortfall_resilience"]["raw"]["cappedRecovery"],
        "p95Value": old_v5["components"]["realistic_upside"]["raw"].get("p95ThresholdValue"),
        "p50Value": old_v3["distributionDisclosures"]["medianValue"],
        "overallShadowVersion": "OVERALL_RIP_FINANCIAL_V5_SHADOW",
    }
    assert {key: value for key, value in new.items() if key != "scoringSeconds"} == expected


def test_projected_control_uses_frozen_four_decimal_cost_identity():
    prepared = PreparedFinancialRipDistribution.prepare(np.array([.2, 1, 2, 5] * 2500))
    candidate = PreparedV5Candidate("p", 254, prepared, 70, .001, 1300)
    scored = candidate.score_candidate(511)
    control = PreparedCanonicalCandidate.score_candidate(candidate, 511)
    assert scored["actualCommittedCapital"] == control["actualCommittedCapital"]
    assert scored["financialRipV4Score"] == control["financialRipV4Score"]


def test_candidate_authority_reuses_exact_cent_boundary():
    prepared = PreparedFinancialRipDistribution.prepare(np.array([.2, 1, 2, 5] * 2500))
    factory = lambda q: PreparedV5Candidate("a", q, prepared, 70, .001, 1.2)
    at_current = factory(1).score_candidate(100)
    benchmark = {**at_current, "sealedProductId": "b",
                 "financialRipV5CandidateScore": at_current["financialRipV5CandidateScore"] - .1}
    search = ExactBestOpenPriceSearch(
        product_id="a", budget_cents=120, current_price_cents=100, current_quantity=1,
        current_rank=1, benchmark=benchmark, prepare_quantity=factory,
        source_authority_fingerprint="same", expected_source_authority_fingerprint="same",
        comparison_authority=FINANCIAL_V5,
    )
    result = search.search()
    assert result["status"] == "exact"
    assert result["threshold"]["priceCents"] == 101
    assert result["exactness"]["thresholdWins"] is True
    assert result["exactness"]["nextPriceWins"] is False


def test_checkpoint_preserves_completed_evidence_and_refuses_authority_drift(tmp_path):
    path = tmp_path / "checkpoint.json"
    authority = {
        "sourceSnapshotId": "snapshot", "sourceFingerprint": "cohort",
        "sourceAuthorityFingerprint": "source", "candidateVersion": "v5",
        "overallShadowVersion": "shadow", "searchMethodIdentity": "exact",
    }
    completed = {**authority, "products": [{"sealedProductId": "first", "threshold": 123}]}
    atomic_json(path, completed)
    assert load_matching_checkpoint(path, authority)["products"] == completed["products"]
    with pytest.raises(TypeError):
        atomic_json(path, {**completed, "bad": {1}})
    assert load_matching_checkpoint(path, authority)["products"] == completed["products"]
    with pytest.raises(RuntimeError, match="sourceAuthorityFingerprint"):
        load_matching_checkpoint(path, {**authority, "sourceAuthorityFingerprint": "changed"})


def test_completed_candidate_waits_for_same_authority_full_control():
    candidate = {"sourceSnapshotId": "snapshot", "sourceFingerprint": "cohort",
                 "sourceAuthorityFingerprint": "fingerprint"}
    control = {**candidate, "status": "complete", "products": [{"id": 1}]}
    assert not control_complete_for_candidate(None, candidate, 1)
    assert not control_complete_for_candidate({**control, "status": "incomplete"}, candidate, 1)
    assert not control_complete_for_candidate(control, candidate, 138)
    assert control_complete_for_candidate(control, candidate, 1)
    with pytest.raises(RuntimeError, match="sourceSnapshotId"):
        control_complete_for_candidate({**control, "sourceSnapshotId": "changed"}, candidate, 1)
    with pytest.raises(RuntimeError, match="sourceFingerprint"):
        control_complete_for_candidate({**control, "sourceFingerprint": "changed"}, candidate, 1)
