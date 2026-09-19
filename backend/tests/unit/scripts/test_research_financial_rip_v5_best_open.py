import numpy as np

from backend.calculations.evr.best_open_price import ExactBestOpenPriceSearch
from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.scripts.research_financial_rip_v5_best_open import (
    FINANCIAL_V5, OVERALL_V5, PriceCollector, PreparedV5Candidate,
    financial_v5_key, overall_shadow, overall_v5_key,
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
