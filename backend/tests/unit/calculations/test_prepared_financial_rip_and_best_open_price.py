import random

import numpy as np
import pytest

from backend.calculations.evr.best_open_price import (
    BestOpenPriceSearchError,
    ExactBestOpenPriceSearch,
    quantity_price_interval_cents,
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

    def evaluate(self, cents, benchmark):
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
    assert engine.cache_misses == len(engine._quantities)
    engine.clear()
    assert not engine._quantities and not engine._evaluations


def test_extreme_quantity_guard_returns_unresolved_without_fabrication():
    engine = _engine(leader=False, budget=1000, current=100, winning={1}, max_q=20)
    result = engine.search()
    assert result["status"] == "unresolved_extreme_quantity"
    assert result["threshold"] is None
    assert max(result["physicalQuantitiesConstructed"]) <= 20
