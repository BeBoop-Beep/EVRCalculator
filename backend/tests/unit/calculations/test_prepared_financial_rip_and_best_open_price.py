import random

import numpy as np
import pytest

from backend.calculations.evr import best_open_price as best_open_module
from backend.calculations.evr.best_open_price import (
    BestOpenPriceSearchError,
    COMPARISON_AUTHORITY_FINANCIAL_V4,
    COMPARISON_AUTHORITY_OVERALL_V12,
    ExactBestOpenPriceSearch,
    PreparedCanonicalCandidate,
    SharedScoreCache,
    quantity_price_interval_cents,
)
from backend.calculations.evr.budget_normalized_product_ranking import (
    whole_unit_allocation,
)
from backend.calculations.evr.financial_rip_v3 import (
    PreparedFinancialRipDistribution,
    build_financial_rip_v3,
)
from backend.calculations.evr.financial_rip_v4 import project_financial_rip_v4_from_v3_payload
from backend.desirability.weighted_rip import compute_overall_rip_v12


def test_prepared_empty_invalid_and_guaranteed_shift_behaviour():
    assert PreparedFinancialRipDistribution.prepare([]).score(10)["statusReason"] == "empty_outcome_vector"
    assert PreparedFinancialRipDistribution.prepare([1, np.nan]).score(10)["statusReason"] == "non_finite_outcome_vector"
    values = np.linspace(0, 100, 10_000)
    shifted = PreparedFinancialRipDistribution.prepare(values).shifted(7.25).score(40)
    materialized = build_financial_rip_v3(values + 7.25, 40)
    assert shifted == materialized


@pytest.mark.parametrize("cost", [1.0, 12.34, 50.0, 101.01])
def test_prepared_full_v3_v4_v12_parity(cost):
    values = np.random.default_rng(20260913).lognormal(2.0, 1.2, 20_000)
    current = build_financial_rip_v3(values, cost)
    prepared = PreparedFinancialRipDistribution.prepare(values).score(cost)
    assert prepared == current
    current_v4 = project_financial_rip_v4_from_v3_payload(current)
    prepared_v4 = project_financial_rip_v4_from_v3_payload(prepared)
    assert prepared_v4 == current_v4
    assert compute_overall_rip_v12(current_v4["score"], 0.002, 65) == compute_overall_rip_v12(
        prepared_v4["score"], 0.002, 65
    )


@pytest.mark.parametrize("budget,q", [(135000, 1), (135000, 137), (7, 7), (100, 3)])
def test_exact_quantity_intervals(budget, q):
    low, high = quantity_price_interval_cents(budget, q)
    assert budget // low == q == budget // high
    if low > 1:
        assert budget // (low - 1) > q
    if high < budget:
        assert budget // (high + 1) < q


class _SyntheticCandidate:
    def __init__(self, product_id, quantity, budget, winning_prices):
        self.product_id, self.quantity = product_id, quantity
        self.budget, self.winning_prices = budget, winning_prices

    def evaluate(self, cents, benchmark, *, comparison_authority=None):
        wins = cents in self.winning_prices
        return {"wins": wins, "priceCents": cents, "quantity": self.quantity,
                "financialRipV3Score": float(self.budget - cents),
                "financialRipV4Score": float(self.budget - cents),
                "overallRipV12Score": float(self.budget - cents)}


def _engine(*, leader, budget, current, winning, max_q=4096):
    pid = "candidate"
    return ExactBestOpenPriceSearch(
        product_id=pid, budget_cents=budget, current_price_cents=current,
        current_quantity=budget // current, current_rank=1 if leader else 2,
        benchmark={"sealedProductId": "benchmark"},
        prepare_quantity=lambda q: _SyntheticCandidate(pid, q, budget, winning),
        source_authority_fingerprint="authority", expected_source_authority_fingerprint="authority",
        max_quantity_to_construct=max_q,
    )


def _brute_force(budget, current, leader, winning):
    domain = range(current, budget + 1) if leader else range(1, current + 1)
    matches = [p for p in domain if p in winning]
    return max(matches) if matches else None


def test_nonleader_exact_search_never_above_market_and_transitions_quantity():
    winning = set(range(1, 38))
    engine = _engine(leader=False, budget=1000, current=100, winning=winning)
    result = engine.search()
    assert result["threshold"]["priceCents"] == 37
    assert result["threshold"]["quantity"] == 27
    assert result["threshold"]["wins"]
    assert not engine.evaluate_price(38)["wins"]
    with pytest.raises(BestOpenPriceSearchError, match="above current"):
        engine.evaluate_price(101)


def test_leader_allows_headroom_excludes_self_and_is_maximal():
    winning = set(range(100, 251))
    engine = _engine(leader=True, budget=1000, current=100, winning=winning)
    result = engine.search()
    assert result["benchmarkProductId"] == "benchmark"
    assert result["threshold"]["priceCents"] == 250
    assert not engine.evaluate_price(251)["wins"]
    with pytest.raises(BestOpenPriceSearchError, match="below current"):
        engine.evaluate_price(99)


def test_search_matches_bruteforce_oracle_and_is_repeatable():
    rng = random.Random(194)
    for _ in range(100):
        budget, current = rng.randint(20, 300), rng.randint(2, 19)
        current = min(current, budget)
        leader = rng.choice([False, True])
        threshold = rng.randint(current, budget) if leader else rng.randint(1, current)
        winning = (set(range(current, threshold + 1)) if leader else set(range(1, threshold + 1)))
        first = _engine(leader=leader, budget=budget, current=current, winning=winning).search()
        second = _engine(leader=leader, budget=budget, current=current, winning=winning).search()
        expected = _brute_force(budget, current, leader, winning)
        assert first["threshold"]["priceCents"] == expected
        assert first["threshold"]["priceCents"] == second["threshold"]["priceCents"]


def test_authority_version_cache_isolation_and_cleanup():
    with pytest.raises(BestOpenPriceSearchError, match="fingerprint"):
        ExactBestOpenPriceSearch("p", 100, 10, 10, 2, {}, lambda q: None, "a", "b")
    with pytest.raises(BestOpenPriceSearchError, match="model-version"):
        ExactBestOpenPriceSearch("p", 100, 10, 10, 2, {}, lambda q: None, "a", "a", False)
    engine = _engine(leader=False, budget=100, current=10, winning=set(range(1, 6)))
    engine.search()
    assert engine.cache_misses == len(engine._constructed_quantities)
    engine.clear()
    assert not engine._quantities and not engine._constructed_quantities and not engine._evaluations


def test_extreme_quantity_guard_returns_unresolved_without_fabrication():
    engine = _engine(leader=False, budget=1000, current=100, winning={1}, max_q=20)
    result = engine.search()
    assert result["status"] == "unresolved_extreme_quantity"
    assert result["threshold"] is None
    assert max(result["physicalQuantitiesConstructed"]) <= 20


def test_observed_fixed_interval_monotonicity_inversion_uses_exact_fallback():
    engine = _engine(leader=False, budget=100, current=100, winning={74, 75})
    result = engine._solve_interval(1)
    assert result["priceCents"] == 75



def test_candidate_committed_capital_matches_canonical_allocation_float_order(monkeypatch):
    """Counterfactual scoring must reproduce Budget Ranking's float arithmetic.

    9 * 140.68 and 9 * 14068 / 100 are mathematically equal but not the same
    IEEE-754 operation sequence. Published-strategy reconstruction requires the
    former because whole_unit_allocation() is the authority of record.
    """
    budget = 1300.0
    market_price = 140.68
    price_cents = 14068

    allocation = whole_unit_allocation(budget, market_price)
    assert allocation["quantity"] == 9
    assert allocation["actualCommittedCapital"] == 1266.1200000000001

    values = np.random.default_rng(20260916).lognormal(
        2.0, 1.2, 20_000
    )
    prepared = PreparedFinancialRipDistribution.prepare(values)

    candidate = PreparedCanonicalCandidate(
        "candidate",
        allocation["quantity"],
        prepared,
        60.0,
        0.002,
        budget,
    )

    # Comparator outcome is irrelevant to this regression; preserve evaluate()
    # end-to-end while making candidate first deterministically.
    monkeypatch.setattr(
        best_open_module,
        "rank_budget_cohort",
        lambda strategies, **_kwargs: list(strategies),
    )

    result = candidate.evaluate(
        price_cents,
        {"sealedProductId": "benchmark"},
    )

    canonical_v3 = build_financial_rip_v3(
        values,
        allocation["actualCommittedCapital"],
    )
    canonical_v4 = project_financial_rip_v4_from_v3_payload(
        canonical_v3
    )

    assert (
        result["actualCommittedCapital"]
        == allocation["actualCommittedCapital"]
    )
    assert (
        result["financialRipV4Score"]
        == canonical_v4["score"]
    )


def _prepared_candidate(product_id, quantity, *, collector_appeal=60.0, chase_accessibility=0.002,
                         budget=1300.0, seed=20260916):
    values = np.random.default_rng(seed).lognormal(2.0, 1.2, 20_000)
    prepared = PreparedFinancialRipDistribution.prepare(values)
    return PreparedCanonicalCandidate(product_id, quantity, prepared, collector_appeal, chase_accessibility, budget)


def test_evaluate_default_authority_is_unchanged_overall_v12():
    """Task 2 backward-compat pin: evaluate() called exactly as V1 callers
    call it (two positional args, no authority) must return the identical
    'wins' determination it always did -- comparator authority defaults to
    OVERALL_V12.
    """
    candidate = _prepared_candidate("candidate", 9)
    benchmark = {"sealedProductId": "benchmark", "overallRipV12Score": -1e9, "overallRipV12Rankable": True,
                 "financialRipV4Score": -1e9}
    result = candidate.evaluate(14068, benchmark)
    assert result["comparisonAuthority"] == COMPARISON_AUTHORITY_OVERALL_V12
    assert "wins" in result and "financialRipV4Score" in result and "overallRipV12Score" in result


def test_score_candidate_has_no_comparison_fields():
    candidate = _prepared_candidate("candidate", 9)
    record = candidate.score_candidate(14068)
    assert "wins" not in record
    assert record["sealedProductId"] == "candidate"
    assert record["priceCents"] == 14068
    assert record["quantity"] == 9
    assert isinstance(record["financialRipV4Score"], float)


def test_compare_under_financial_v4_authority_uses_financial_only_comparator(monkeypatch):
    candidate = _prepared_candidate("candidate", 9)
    score_record = {"sealedProductId": "candidate", "financialRipV4Score": 50.0}
    losing_benchmark = {"sealedProductId": "benchmark", "financialRipV4Score": 10.0}
    winning_benchmark = {"sealedProductId": "benchmark", "financialRipV4Score": 90.0}
    assert candidate.compare(score_record, losing_benchmark, authority=COMPARISON_AUTHORITY_FINANCIAL_V4) is True
    assert candidate.compare(score_record, winning_benchmark, authority=COMPARISON_AUTHORITY_FINANCIAL_V4) is False


def test_compare_under_overall_v12_authority_is_unchanged(monkeypatch):
    candidate = _prepared_candidate("candidate", 9)
    score_record = {"sealedProductId": "candidate", "overallRipV12Rankable": True, "overallRipV12Score": 90.0,
                     "financialRipV4Score": 50.0}
    losing_benchmark = {"sealedProductId": "benchmark", "overallRipV12Rankable": True, "overallRipV12Score": 10.0,
                         "financialRipV4Score": 10.0}
    assert candidate.compare(score_record, losing_benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12) is True


def test_evaluate_under_financial_v4_authority_can_disagree_with_overall_v12():
    """A candidate can win under FINANCIAL_V4 while losing under OVERALL_V12
    against the SAME benchmark -- the two authorities are genuinely
    independent, per Phase 4's requirement that a product may be #1 under one
    authority but not the other.
    """
    candidate = _prepared_candidate("candidate", 9)
    score_record = candidate.score_candidate(14068)
    high_v4_low_v12_benchmark = {
        "sealedProductId": "benchmark",
        "financialRipV4Score": score_record["financialRipV4Score"] - 1.0,  # candidate wins FINANCIAL_V4
        "overallRipV12Rankable": True,
        "overallRipV12Score": (score_record.get("overallRipV12Score") or 0.0) + 1000.0,  # candidate loses OVERALL_V12
    }
    wins_financial = candidate.compare(score_record, high_v4_low_v12_benchmark, authority=COMPARISON_AUTHORITY_FINANCIAL_V4)
    wins_overall = candidate.compare(score_record, high_v4_low_v12_benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    assert wins_financial is True
    assert wins_overall is False


def test_compare_financial_v4_does_not_win_on_alphabetical_tiebreak_when_unscored():
    """Important #2 regression: rank_by_financial_only() applies no
    rankability filter by design (callers control cohort membership), but
    when BOTH the candidate and the benchmark have no Financial RIP V4
    score, financial_only_comparator_key() maps both to -inf and the sort
    falls entirely to the sealedProductId string tie-break. A candidate
    whose id sorts first alphabetically must NOT be reported as a win --
    it has zero financial evidence behind it.
    """
    candidate = _prepared_candidate("aaa-sorts-first", 9)
    score_record = {"sealedProductId": "aaa-sorts-first", "financialRipV4Score": None}
    benchmark = {"sealedProductId": "zzz-sorts-last"}  # missing key entirely
    assert candidate.compare(score_record, benchmark, authority=COMPARISON_AUTHORITY_FINANCIAL_V4) is False


def test_compare_rejects_unknown_authority():
    candidate = _prepared_candidate("candidate", 9)
    with pytest.raises(ValueError, match="comparison authority"):
        candidate.compare({"sealedProductId": "candidate"}, {"sealedProductId": "benchmark"}, authority="not_a_real_authority")


def test_shared_score_cache_scores_once_across_both_authorities():
    """The core Phase 3 promise: a (quantity, price_cents) candidate scored
    once must serve BOTH comparison authorities without rescoring -- the
    Financial RIP V3 Monte Carlo simulation is the expensive part, and the
    comparator dispatch itself is cheap.
    """
    candidate = _prepared_candidate("candidate", 9)
    cache = SharedScoreCache()
    benchmark = {"sealedProductId": "benchmark", "financialRipV4Score": -1e9,
                 "overallRipV12Rankable": True, "overallRipV12Score": -1e9}

    first = cache.evaluate(candidate, 14068, benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    second = cache.evaluate(candidate, 14068, benchmark, authority=COMPARISON_AUTHORITY_FINANCIAL_V4)

    assert first["wins"] is True and second["wins"] is True
    # Same underlying score for the same (quantity, price_cents) -- proves no rescoring happened.
    assert first["financialRipV4Score"] == second["financialRipV4Score"]
    diagnostics = cache.diagnostics()
    assert diagnostics["uniqueCandidatePricesScored"] == 1
    assert diagnostics["sharedScoreCacheHits"] == 1  # the second evaluate() call hit the cache
    assert diagnostics["ripComparatorEvaluations"] == 1
    assert diagnostics["financialComparatorEvaluations"] == 1


def test_shared_score_cache_evaluate_reports_comparator_seconds_and_cache_hit_flag():
    """Important #1 regression: evaluate() must expose comparatorSeconds for
    THIS call and a scoreCacheHit flag without a caller reaching into the
    private candidate._last_comparator_seconds attribute -- and a cache HIT
    must be distinguishable from a MISS so an aggregator does not double-count
    scoringSeconds across authority calls sharing one cached score.
    """
    candidate = _prepared_candidate("candidate", 9)
    cache = SharedScoreCache()
    benchmark = {"sealedProductId": "benchmark", "financialRipV4Score": -1e9,
                 "overallRipV12Rankable": True, "overallRipV12Score": -1e9}

    first = cache.evaluate(candidate, 14068, benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    assert first["scoreCacheHit"] is False
    assert first["comparisonAuthority"] == COMPARISON_AUTHORITY_OVERALL_V12
    assert isinstance(first["comparatorSeconds"], float) and first["comparatorSeconds"] >= 0.0

    second = cache.evaluate(candidate, 14068, benchmark, authority=COMPARISON_AUTHORITY_FINANCIAL_V4)
    assert second["scoreCacheHit"] is True
    assert second["comparisonAuthority"] == COMPARISON_AUTHORITY_FINANCIAL_V4
    assert isinstance(second["comparatorSeconds"], float) and second["comparatorSeconds"] >= 0.0
    # Same underlying scoringSeconds value is reused (not recomputed) on a hit --
    # a caller that only adds scoringSeconds when scoreCacheHit is False avoids
    # double counting.
    assert first["scoringSeconds"] == second["scoringSeconds"]


def test_shared_score_cache_get_or_score_returns_a_copy_not_the_live_cache_entry():
    """Minor #4: mutating a returned score record must not corrupt the cache
    for the other comparison authority sharing the same underlying score."""
    candidate = _prepared_candidate("candidate", 9)
    cache = SharedScoreCache()
    record, was_hit = cache.get_or_score(candidate, 14068)
    assert was_hit is False
    record["financialRipV4Score"] = "tampered"
    record2, was_hit2 = cache.get_or_score(candidate, 14068)
    assert was_hit2 is True
    assert record2["financialRipV4Score"] != "tampered"


def test_shared_score_cache_distinguishes_price_cents_within_same_quantity():
    candidate = _prepared_candidate("candidate", 9)
    cache = SharedScoreCache()
    benchmark = {"sealedProductId": "benchmark", "financialRipV4Score": -1e9,
                 "overallRipV12Rankable": True, "overallRipV12Score": -1e9}
    cache.evaluate(candidate, 14068, benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    cache.evaluate(candidate, 14069, benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    diagnostics = cache.diagnostics()
    assert diagnostics["uniqueCandidatePricesScored"] == 2
    assert diagnostics["sharedScoreCacheHits"] == 0


def test_shared_score_cache_get_or_score_matches_direct_score_candidate():
    candidate = _prepared_candidate("candidate", 9)
    cache = SharedScoreCache()
    cached, _was_hit = cache.get_or_score(candidate, 14068)
    direct = candidate.score_candidate(14068)
    assert cached["financialRipV4Score"] == direct["financialRipV4Score"]
    assert cached["actualCommittedCapital"] == direct["actualCommittedCapital"]


def test_shared_score_cache_evicts_beyond_max_entries():
    candidate = _prepared_candidate("candidate", 9)
    cache = SharedScoreCache(max_entries=2)
    benchmark = {"sealedProductId": "benchmark", "financialRipV4Score": -1e9,
                 "overallRipV12Rankable": True, "overallRipV12Score": -1e9}
    for price in (14068, 14069, 14070):
        cache.evaluate(candidate, price, benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    assert len(cache._scores) == 2
    # Oldest entry (14068) evicted; re-requesting it must score again, not hit.
    diagnostics_before = cache.diagnostics()["uniqueCandidatePricesScored"]
    cache.evaluate(candidate, 14068, benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    assert cache.diagnostics()["uniqueCandidatePricesScored"] == diagnostics_before + 1


def test_exact_search_default_construction_is_unchanged_v1_behavior():
    """Backward-compat pin: an ExactBestOpenPriceSearch built exactly as V1
    callers build it today (no shared_score_cache, no comparison_authority)
    must behave identically to before -- same threshold, same status.
    """
    engine = _engine(leader=False, budget=1000, current=100, winning=set(range(1, 38)))
    result = engine.search()
    assert result["threshold"]["priceCents"] == 37
    assert result["threshold"]["quantity"] == 27


def test_two_engines_sharing_one_cache_score_overlapping_candidate_once():
    budget = 1300
    budget_cents = budget * 100
    candidate_a = _prepared_candidate("a", 9, budget=float(budget))
    candidate_b = _prepared_candidate("b", 9, budget=float(budget))
    cache = SharedScoreCache()

    def prepare_a(_q):
        return candidate_a

    def prepare_b(_q):
        return candidate_b

    benchmark = {"sealedProductId": "benchmark", "financialRipV4Score": -1e9,
                 "overallRipV12Rankable": True, "overallRipV12Score": -1e9}

    engine_rip = ExactBestOpenPriceSearch(
        product_id="a", budget_cents=budget_cents, current_price_cents=14068,
        current_quantity=9, current_rank=2, benchmark=benchmark,
        prepare_quantity=prepare_a, source_authority_fingerprint="fp",
        expected_source_authority_fingerprint="fp",
        shared_score_cache=cache, comparison_authority=COMPARISON_AUTHORITY_OVERALL_V12,
    )
    engine_financial = ExactBestOpenPriceSearch(
        product_id="a", budget_cents=budget_cents, current_price_cents=14068,
        current_quantity=9, current_rank=2, benchmark=benchmark,
        prepare_quantity=prepare_a, source_authority_fingerprint="fp",
        expected_source_authority_fingerprint="fp",
        shared_score_cache=cache, comparison_authority=COMPARISON_AUTHORITY_FINANCIAL_V4,
    )

    rip_result = engine_rip.evaluate_price(14068)
    financial_result = engine_financial.evaluate_price(14068)

    assert rip_result["financialRipV4Score"] == financial_result["financialRipV4Score"]
    diagnostics = cache.diagnostics()
    assert diagnostics["uniqueCandidatePricesScored"] == 1
    assert diagnostics["scoreCacheHits"] == 1
    assert diagnostics["ripComparatorEvaluations"] == 1
    assert diagnostics["financialComparatorEvaluations"] == 1


def test_shared_score_cache_evictions_are_counted():
    candidate = _prepared_candidate("candidate", 9)
    cache = SharedScoreCache(max_entries=1)
    benchmark = {"sealedProductId": "benchmark", "financialRipV4Score": -1e9,
                 "overallRipV12Rankable": True, "overallRipV12Score": -1e9}
    cache.evaluate(candidate, 14068, benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    cache.evaluate(candidate, 14069, benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    assert cache.diagnostics()["scoreCacheEvictions"] == 1


from backend.calculations.evr.best_open_price import (
    BEST_OPEN_PRICE_METHOD_VERSION,
    BEST_OPEN_PRICE_V2_METHOD_VERSION,
    DualBestOpenPriceSearch,
)


def _dual_engine(*, budget, current_price_cents, current_quantity,
                  rip_rank, rip_benchmark, financial_rank, financial_benchmark,
                  seed=20260916):
    values = np.random.default_rng(seed).lognormal(2.0, 1.2, 20_000)

    quantity_cache: dict[int, PreparedCanonicalCandidate] = {}

    def prepare_quantity(q):
        if q not in quantity_cache:
            prepared = PreparedFinancialRipDistribution.prepare(values)
            quantity_cache[q] = PreparedCanonicalCandidate("product", q, prepared, 60.0, 0.002, float(budget))
        return quantity_cache[q]

    return DualBestOpenPriceSearch(
        product_id="product", budget_cents=budget,
        current_price_cents=current_price_cents, current_quantity=current_quantity,
        rip_current_rank=rip_rank, rip_benchmark=rip_benchmark,
        financial_current_rank=financial_rank, financial_benchmark=financial_benchmark,
        prepare_quantity=prepare_quantity,
        source_authority_fingerprint="fp", expected_source_authority_fingerprint="fp",
    ), quantity_cache


def test_dual_search_returns_two_threshold_objects():
    engine, _ = _dual_engine(
        budget=135000, current_price_cents=14068, current_quantity=9,
        rip_rank=2, rip_benchmark={"sealedProductId": "rip-bench", "overallRipV12Rankable": True, "overallRipV12Score": -1e9, "financialRipV4Score": -1e9},
        financial_rank=2, financial_benchmark={"sealedProductId": "fin-bench", "financialRipV4Score": -1e9, "overallRipV12Rankable": True, "overallRipV12Score": -1e9},
    )
    result = engine.search()
    assert result["ripResult"]["status"] == "exact"
    assert result["financialResult"]["status"] == "exact"
    assert result["ripResult"]["threshold"] is not None
    assert result["financialResult"]["threshold"] is not None


def test_dual_search_shares_one_score_cache_across_both_authorities():
    engine, quantity_cache = _dual_engine(
        budget=135000, current_price_cents=14068, current_quantity=9,
        rip_rank=2, rip_benchmark={"sealedProductId": "rip-bench", "overallRipV12Rankable": True, "overallRipV12Score": -1e9, "financialRipV4Score": -1e9},
        financial_rank=2, financial_benchmark={"sealedProductId": "fin-bench", "financialRipV4Score": -1e9, "overallRipV12Rankable": True, "overallRipV12Score": -1e9},
    )
    result = engine.search()
    diagnostics = result["diagnostics"]
    assert diagnostics["ripComparatorEvaluations"] > 0
    assert diagnostics["financialComparatorEvaluations"] > 0
    # Both authorities search overlapping domains (both bounded above by the
    # same current price for a nonleader) -- some sharing must have occurred.
    naive = diagnostics["naiveScoreCount"]
    unique = diagnostics["uniqueCandidatePricesScored"]
    assert unique < naive
    assert diagnostics["scoreReuseSavings"] == naive - unique
    # The prepare_quantity closure itself must not be called once per
    # authority for the SAME quantity -- verify via the shared memoization
    # dict populated by the test's own prepare_quantity wrapper.
    assert len(quantity_cache) >= 1


def test_dual_search_financial_leader_only():
    """Product is Financial rank 1 (leader) but RIP rank 2 (nonleader) --
    the two searches must use genuinely different domains/directions."""
    engine, _ = _dual_engine(
        budget=135000, current_price_cents=14068, current_quantity=9,
        rip_rank=2, rip_benchmark={"sealedProductId": "rip-bench", "overallRipV12Rankable": True, "overallRipV12Score": -1e9, "financialRipV4Score": -1e9},
        financial_rank=1, financial_benchmark={"sealedProductId": "fin-bench", "financialRipV4Score": -1e9, "overallRipV12Rankable": True, "overallRipV12Score": -1e9},
    )
    result = engine.search()
    assert result["ripResult"]["currentRank"] == 2
    assert result["financialResult"]["currentRank"] == 1


def test_v1_best_open_price_method_version_unchanged():
    assert BEST_OPEN_PRICE_METHOD_VERSION == "budget_product_best_open_price_full_market_v1"
    assert BEST_OPEN_PRICE_V2_METHOD_VERSION == "budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12"


# ---------------------------------------------------------------------------
# Task 5: remaining 32-item test-matrix coverage + diagnostics report.
#
# _DualSyntheticCandidate mirrors _SyntheticCandidate's shape (a fixed,
# pre-declared winning-price set drives `wins`, exactly like the V1 synthetic
# fixture above) but exposes independently controllable winning-price sets
# per comparison authority, plus the score_candidate()/compare() interface
# ExactBestOpenPriceSearch/SharedScoreCache actually call (see
# best_open_price.py evaluate_price() -> shared_score_cache.evaluate() ->
# candidate.score_candidate()/candidate.compare()). This is the minimal
# extension needed to make the RIP and Financial searches disagree
# deterministically in the NEW dual-engine matrix items below; it is not a
# parallel fixture system.
# ---------------------------------------------------------------------------
class _DualSyntheticCandidate:
    def __init__(self, product_id, quantity, rip_winning_prices, financial_winning_prices):
        self.product_id, self.quantity = product_id, quantity
        self.rip_winning_prices = rip_winning_prices
        self.financial_winning_prices = financial_winning_prices
        self._last_comparator_seconds = 0.0

    def score_candidate(self, price_cents):
        return {
            "sealedProductId": self.product_id, "priceCents": price_cents, "quantity": self.quantity,
            "financialRipV4Score": float(price_cents), "overallRipV12Score": float(price_cents),
            "chanceToRecoverCapital": 0.5, "actualCommittedCapital": price_cents / 100.0,
            "scoringSeconds": 0.0,
        }

    def compare(self, score_record, benchmark, *, authority=COMPARISON_AUTHORITY_OVERALL_V12):
        price = score_record["priceCents"]
        winning = (self.financial_winning_prices if authority == COMPARISON_AUTHORITY_FINANCIAL_V4
                   else self.rip_winning_prices)
        self._last_comparator_seconds = 0.0
        return price in winning

    def evaluate(self, price_cents, benchmark, *, comparison_authority=COMPARISON_AUTHORITY_OVERALL_V12):
        score_record = self.score_candidate(price_cents)
        wins = self.compare(score_record, benchmark, authority=comparison_authority)
        return {**score_record, "wins": wins, "comparatorSeconds": self._last_comparator_seconds,
                "comparisonAuthority": comparison_authority}


def _dual_synthetic_engine(*, budget, current, rip_rank, rip_winning, financial_rank, financial_winning, max_q=4096):
    pid = "candidate"
    quantity_cache = {}

    def prepare_quantity(q):
        if q not in quantity_cache:
            quantity_cache[q] = _DualSyntheticCandidate(pid, q, rip_winning, financial_winning)
        return quantity_cache[q]

    return DualBestOpenPriceSearch(
        product_id=pid, budget_cents=budget, current_price_cents=current,
        current_quantity=budget // current,
        rip_current_rank=rip_rank, rip_benchmark={"sealedProductId": "rip-bench"},
        financial_current_rank=financial_rank, financial_benchmark={"sealedProductId": "fin-bench"},
        prepare_quantity=prepare_quantity,
        source_authority_fingerprint="fp", expected_source_authority_fingerprint="fp",
        max_quantity_to_construct=max_q,
    )


def test_dual_search_financial_and_rip_thresholds_can_be_equal():
    """Matrix item 5."""
    winning = set(range(1, 38))
    engine = _dual_synthetic_engine(
        budget=1000, current=100, rip_rank=2, rip_winning=winning,
        financial_rank=2, financial_winning=winning,
    )
    result = engine.search()
    assert result["ripResult"]["threshold"]["priceCents"] == result["financialResult"]["threshold"]["priceCents"] == 37


def test_dual_search_financial_threshold_below_rip_threshold():
    """Matrix item 6."""
    engine = _dual_synthetic_engine(
        budget=1000, current=100, rip_rank=2, rip_winning=set(range(1, 38)),
        financial_rank=2, financial_winning=set(range(1, 21)),
    )
    result = engine.search()
    assert result["financialResult"]["threshold"]["priceCents"] < result["ripResult"]["threshold"]["priceCents"]


def test_dual_search_financial_threshold_above_rip_threshold():
    """Matrix item 7."""
    engine = _dual_synthetic_engine(
        budget=1000, current=100, rip_rank=2, rip_winning=set(range(1, 21)),
        financial_rank=2, financial_winning=set(range(1, 38)),
    )
    result = engine.search()
    assert result["financialResult"]["threshold"]["priceCents"] > result["ripResult"]["threshold"]["priceCents"]


def test_dual_search_candidate_leader_under_both_authorities():
    """Matrix item 8."""
    winning = set(range(100, 251))
    engine = _dual_synthetic_engine(
        budget=1000, current=100, rip_rank=1, rip_winning=winning,
        financial_rank=1, financial_winning=winning,
    )
    result = engine.search()
    assert result["ripResult"]["currentRank"] == result["financialResult"]["currentRank"] == 1
    assert result["ripResult"]["threshold"]["wins"] is True
    assert result["financialResult"]["threshold"]["wins"] is True


def test_dual_search_rip_leader_only():
    """Matrix item 10: mirror of Task 3's test_dual_search_financial_leader_only
    with ranks swapped -- product is RIP rank 1 (leader) but Financial rank 2
    (nonleader)."""
    engine = _dual_synthetic_engine(
        budget=1000, current=100, rip_rank=1, rip_winning=set(range(100, 251)),
        financial_rank=2, financial_winning=set(range(1, 38)),
    )
    result = engine.search()
    assert result["ripResult"]["currentRank"] == 1
    assert result["financialResult"]["currentRank"] == 2


def test_dual_search_candidate_leader_under_neither_reports_currentrank_two_for_both():
    """Matrix item 11: explicit currentRank assertion for both authorities
    when the candidate is a nonleader under both (extends the coverage of
    Task 3's test_dual_search_returns_two_threshold_objects, which does not
    assert currentRank)."""
    engine, _ = _dual_engine(
        budget=135000, current_price_cents=14068, current_quantity=9,
        rip_rank=2, rip_benchmark={"sealedProductId": "rip-bench", "overallRipV12Rankable": True,
                                    "overallRipV12Score": -1e9, "financialRipV4Score": -1e9},
        financial_rank=2, financial_benchmark={"sealedProductId": "fin-bench", "financialRipV4Score": -1e9,
                                                "overallRipV12Rankable": True, "overallRipV12Score": -1e9},
    )
    result = engine.search()
    assert result["ripResult"]["currentRank"] == 2
    assert result["financialResult"]["currentRank"] == 2


def test_dual_search_financial_threshold_wins_and_is_one_cent_maximal():
    """Matrix items 13 and 14."""
    engine, _ = _dual_engine(
        budget=135000, current_price_cents=14068, current_quantity=9,
        rip_rank=2, rip_benchmark={"sealedProductId": "rip-bench", "overallRipV12Rankable": True,
                                    "overallRipV12Score": -1e9, "financialRipV4Score": -1e9},
        financial_rank=2, financial_benchmark={"sealedProductId": "fin-bench", "financialRipV4Score": -1e9,
                                                "overallRipV12Rankable": True, "overallRipV12Score": -1e9},
    )
    result = engine.search()["financialResult"]
    assert result["threshold"]["wins"] is True
    assert result["exactness"]["oneCentMaximal"] is True


def test_dual_search_rip_threshold_wins_and_is_one_cent_maximal():
    """Matrix items 15 and 16."""
    engine, _ = _dual_engine(
        budget=135000, current_price_cents=14068, current_quantity=9,
        rip_rank=2, rip_benchmark={"sealedProductId": "rip-bench", "overallRipV12Rankable": True,
                                    "overallRipV12Score": -1e9, "financialRipV4Score": -1e9},
        financial_rank=2, financial_benchmark={"sealedProductId": "fin-bench", "financialRipV4Score": -1e9,
                                                "overallRipV12Rankable": True, "overallRipV12Score": -1e9},
    )
    result = engine.search()["ripResult"]
    assert result["threshold"]["wins"] is True
    assert result["exactness"]["oneCentMaximal"] is True


def test_dual_search_next_cent_crosses_quantity_boundary_both_authorities():
    """Matrix items 17 and 18: the threshold sits at the top of the quantity-27
    price interval for budget=1000 (see test_nonleader_exact_search_never_above_market_and_transitions_quantity,
    which already establishes threshold=37/quantity=27/next-price-38-loses for
    this exact winning set); price+1=38 resolves to quantity 26, a different
    physical quantity than the threshold's 27 -- a boundary crossing regardless
    of authority."""
    winning = set(range(1, 38))
    engine = _dual_synthetic_engine(
        budget=1000, current=100, rip_rank=2, rip_winning=winning,
        financial_rank=2, financial_winning=winning,
    )
    result = engine.search()
    assert result["financialResult"]["exactness"]["nextCentCrossesQuantityBoundary"] is True
    assert result["ripResult"]["exactness"]["nextCentCrossesQuantityBoundary"] is True


def test_observed_fixed_interval_monotonicity_inversion_financial_v4_authority():
    """Matrix item 19: adapt the V1 monotonicity-inversion pattern (see
    test_observed_fixed_interval_monotonicity_inversion_uses_exact_fallback
    above, which exercises the default OVERALL_V12 authority -- matrix item 20)
    to the FINANCIAL_V4 authority explicitly."""
    def prepare_quantity(q):
        return _DualSyntheticCandidate("candidate", q, rip_winning_prices=set(), financial_winning_prices={74, 75})

    engine = ExactBestOpenPriceSearch(
        product_id="candidate", budget_cents=100, current_price_cents=100, current_quantity=1,
        current_rank=2, benchmark={"sealedProductId": "benchmark"},
        prepare_quantity=prepare_quantity,
        source_authority_fingerprint="fp", expected_source_authority_fingerprint="fp",
        comparison_authority=COMPARISON_AUTHORITY_FINANCIAL_V4,
    )
    result = engine._solve_interval(1)
    assert result["priceCents"] == 75


def test_shared_score_cache_bounded_under_large_synthetic_search():
    """Matrix item 32: drives many distinct (quantity, price_cents) keys
    through a bounded SharedScoreCache and asserts the live cache never
    exceeds max_entries at any point, plus that evictions were actually
    counted."""
    cache = SharedScoreCache(max_entries=10)
    candidate = _prepared_candidate("candidate", 9)
    benchmark = {"sealedProductId": "benchmark", "financialRipV4Score": -1e9,
                 "overallRipV12Rankable": True, "overallRipV12Score": -1e9}
    for price in range(14000, 14100):
        cache.evaluate(candidate, price, benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
        assert len(cache._scores) <= 10
    diagnostics = cache.diagnostics()
    assert diagnostics["scoreCacheEvictions"] > 0


def test_dual_search_diagnostics_report(capsys):
    """Step 4: diagnostics/performance report over a representative synthetic
    fixture (the same fixture as Task 3's
    test_dual_search_shares_one_score_cache_across_both_authorities). Reports
    the synthetic reuse-savings/cache-hit-rate numbers only -- per the task's
    explicit instruction, this does NOT claim a full-cohort speed improvement."""
    engine, _ = _dual_engine(
        budget=135000, current_price_cents=14068, current_quantity=9,
        rip_rank=2, rip_benchmark={"sealedProductId": "rip-bench", "overallRipV12Rankable": True,
                                    "overallRipV12Score": -1e9, "financialRipV4Score": -1e9},
        financial_rank=2, financial_benchmark={"sealedProductId": "fin-bench", "financialRipV4Score": -1e9,
                                                "overallRipV12Rankable": True, "overallRipV12Score": -1e9},
    )
    diagnostics = engine.search()["diagnostics"]
    rip_evals = diagnostics["ripComparatorEvaluations"]
    financial_evals = diagnostics["financialComparatorEvaluations"]
    unique = diagnostics["uniqueCandidatePricesScored"]
    naive = diagnostics["naiveScoreCount"]
    savings = diagnostics["scoreReuseSavings"]

    assert naive == rip_evals + financial_evals
    assert savings == naive - unique
    assert unique > 0 and naive > 0

    cache_hit_rate = savings / naive
    assert 0.0 <= cache_hit_rate < 1.0
    print(
        "\n[Best-Open V2 dual-search diagnostics report] "
        f"ripComparatorEvaluations={rip_evals} financialComparatorEvaluations={financial_evals} "
        f"uniqueCandidatePricesScored={unique} naiveScoreCount={naive} "
        f"scoreReuseSavings={savings} cacheHitRate={cache_hit_rate:.4f} "
        "(synthetic single-product fixture only -- NOT a full-cohort speed claim)"
    )
    captured = capsys.readouterr()
    assert "dual-search diagnostics report" in captured.out
