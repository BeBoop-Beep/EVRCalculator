"""Ranking V2 (Financial V5 + Overall V14) and Best-Open V3 engine tests."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest

import backend.calculations.evr.best_open_price_v3 as bo3
from backend.calculations.evr import budget_normalized_product_ranking as rk
from backend.calculations.evr.best_open_price import (
    BEST_OPEN_PRICE_METHOD_VERSION, BEST_OPEN_PRICE_V2_METHOD_VERSION, BestOpenPriceSearchError,
)
from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.calculations.evr.financial_rip_v4 import project_financial_rip_v4_from_v3_payload
from backend.calculations.evr.financial_rip_v5 import build_financial_rip_v5
from backend.calculations.evr.financial_rip_v5_candidate import score_financial_rip_v5_candidate
from backend.desirability.chase_accessibility_overall_score import chase_accessibility_overall_score

CHASE = 0.01
COLLECTOR = 55.5


def _values(seed=5, n=20001):
    return np.random.default_rng(seed).choice([0, .2, .6, 1, 3, 15], n).astype(float)


# ---------------------------------------------------------------- Ranking V2

def test_identities_unique_and_v1_frozen():
    assert rk.BUDGET_NORMALIZED_RANKING_METHOD_VERSION == "budget_product_ranking_v1"
    assert rk.BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2 == "budget_product_ranking_v2"
    assert rk.ALLOCATION_METHOD_VERSION == "budget_allocation_floor_quantity_v1"
    assert BEST_OPEN_PRICE_METHOD_VERSION.endswith("_v1")
    assert BEST_OPEN_PRICE_V2_METHOD_VERSION.endswith("dual_financial_v4_overall_v12")
    assert bo3.BEST_OPEN_PRICE_V3_METHOD_VERSION.endswith("v3_dual_financial_v5_overall_v14")
    assert len({BEST_OPEN_PRICE_METHOD_VERSION, BEST_OPEN_PRICE_V2_METHOD_VERSION,
                bo3.BEST_OPEN_PRICE_V3_METHOD_VERSION}) == 3


def test_v2_scoring_uses_v5_and_v14_and_never_v4_v12_fields():
    values = _values()
    cap = 3.0
    v2 = rk.score_budget_strategy_v2(values, cap, COLLECTOR, chase_accessibility_raw=CHASE)
    prepared = PreparedFinancialRipDistribution.prepare(values)
    assert v2["financialRipV5Score"] == build_financial_rip_v5(prepared, cap)["score"]
    assert v2["financialRipV5Score"] == score_financial_rip_v5_candidate(values, cap)["score"]
    a = chase_accessibility_overall_score(CHASE)
    assert v2["overallRipV14Score"] == round(.86 * v2["financialRipV5Score"] + .04 * a + .10 * COLLECTOR, 4)
    assert v2["overallRipV14Version"].startswith("overall_rip_v14_")
    assert not [k for k in v2 if "V4" in k or "V12" in k or "V10" in k]
    v1 = rk.score_budget_strategy(values, cap, COLLECTOR, chase_accessibility_raw=CHASE)
    assert v1["financialRipV4Score"] != v2["financialRipV5Score"]
    assert "financialRipV5Score" not in v1


def test_v2_missing_pillars_are_unranked_not_fallback():
    v = _values()
    no_chase = rk.score_budget_strategy_v2(v, 3.0, COLLECTOR)
    assert no_chase["overallRipV14Score"] is None and no_chase["overallRipV14Rankable"] is False
    assert rk.rank_budget_cohort_v2([{**no_chase, "sealedProductId": "x", "actualCommittedCapital": 3,
                                      "targetBudget": 3}]) == []
    v12_only = {"sealedProductId": "y", "overallRipV12Score": 99.0, "overallRipV12Rankable": True,
                "financialRipV4Score": 99.0, "actualCommittedCapital": 1, "targetBudget": 1}
    assert rk.rank_budget_cohort_v2([v12_only]) == []


def _entry(pid, overall, fin, recover=0.1, cap=100.0):
    return {"sealedProductId": pid, "overallRipV14Score": overall, "overallRipV14Rankable": True,
            "financialRipV5Score": fin, "financialRipV5Rankable": True,
            "chanceToRecoverCapital": recover, "actualCommittedCapital": cap, "targetBudget": 100.0}


def test_v2_comparator_shape_ranks_contiguous_and_deterministic():
    rows = [_entry("c", 50, 40), _entry("a", 50, 40), _entry("b", 50, 45),
            _entry("d", 50, 40, recover=0.2), _entry("e", 60, 10), _entry("f", 50, 40, cap=90.0)]
    ranked = rk.rank_budget_cohort_v2(rows)
    assert [r["sealedProductId"] for r in ranked] == ["e", "b", "d", "a", "c", "f"]
    assert [r["budgetRankV14"] for r in ranked] == list(range(1, 7))
    assert {r["budgetCohortSizeV14"] for r in ranked} == {6}
    assert rk.rank_budget_cohort_v2(list(reversed(rows))) == ranked
    assert [r["sealedProductId"] for r in sorted(ranked, key=lambda r: r["financialOnlyRankV5"])][0] == "b"
    assert all("budgetRank" not in r and "financialOnlyRank" not in r for r in ranked)


# ---------------------------------------------------------------- Best-Open V3

def _candidate(quantity=1, seed=5):
    return bo3.PreparedV5Candidate(
        product_id="p", quantity=quantity,
        distribution=PreparedFinancialRipDistribution.prepare(_values(seed)),
        collector_appeal_score=COLLECTOR, chase_accessibility_raw=CHASE, target_budget=10.0)


def test_v3_source_must_be_ranking_v2():
    bo3.require_ranking_v2_source("budget_product_ranking_v2")
    for bad in ("budget_product_ranking_v1", None, ""):
        with pytest.raises(BestOpenPriceSearchError):
            bo3.require_ranking_v2_source(bad)


def test_v3_candidate_scores_v5_v14_and_differs_from_v4_v12():
    cand = _candidate(quantity=2)
    rec = cand.score_candidate(150)
    capital = 2 * 1.5
    values = _values()
    assert rec["financialRipV5Score"] == score_financial_rip_v5_candidate(values, capital)["score"]
    v3 = cand.distribution.score(capital)
    v4 = project_financial_rip_v4_from_v3_payload(v3)
    assert rec["financialRipV5Score"] != v4["score"]  # mutation guard: a V4 call would fail this
    a = chase_accessibility_overall_score(CHASE)
    assert rec["overallRipV14Score"] == round(.86 * rec["financialRipV5Score"] + .04 * a + .10 * COLLECTOR, 4)
    assert not [k for k in rec if "V4" in k or "V12" in k]


def test_v3_comparators_use_own_authority_and_never_delegate():
    cand = _candidate()
    rec = {"sealedProductId": "p", "financialRipV5Score": 50.0, "overallRipV14Score": 55.0,
           "overallRipV14Rankable": True, "chanceToRecoverCapital": .1,
           "actualCommittedCapital": 10.0, "targetBudget": 10.0}
    bench = {**rec, "sealedProductId": "z", "financialRipV5Score": 49.0, "overallRipV14Score": 56.0}
    assert cand.compare(rec, bench, authority=bo3.COMPARISON_AUTHORITY_FINANCIAL_V5) is True
    assert cand.compare(rec, bench, authority=bo3.COMPARISON_AUTHORITY_OVERALL_V14) is False
    v12_bench = {"sealedProductId": "z", "financialRipV4Score": 1.0, "overallRipV12Score": 1.0}
    with pytest.raises(Exception):
        cand.compare(rec, bench, authority="overall_v12")
    with pytest.raises(Exception):
        cand.compare(rec, v12_bench, authority="financial_v4")
    unscored = {**rec, "financialRipV5Score": None}
    assert cand.compare(unscored, bench, authority=bo3.COMPARISON_AUTHORITY_FINANCIAL_V5) is False


@dataclass
class _Fake:
    product_id: str
    quantity: int
    _last_comparator_seconds: float = field(default=0.0, init=False)

    def score_candidate(self, price_cents):
        return {"sealedProductId": self.product_id, "priceCents": price_cents, "quantity": self.quantity,
                "targetBudget": 10.0, "actualCommittedCapital": self.quantity * price_cents / 100,
                "financialRipV5Score": float(price_cents), "overallRipV14Score": float(price_cents),
                "scoringSeconds": 0.0}

    def compare(self, record, benchmark, *, authority):
        return int(record["priceCents"]) <= int(benchmark["thresholdCents"])


def test_v3_fused_search_is_exact_and_relabelled():
    def build(rank):
        return bo3.build_dual_best_open_v3_search(
            product_id="p", budget_cents=1000, current_price_cents=500, current_quantity=2,
            overall_v14_current_rank=rank, financial_v5_current_rank=rank,
            overall_v14_benchmark={"sealedProductId": "z", "thresholdCents": 620,
                                   "overallRipV14Score": 61.0, "financialRipV5Score": 60.0},
            financial_v5_benchmark={"sealedProductId": "y", "thresholdCents": 610,
                                    "overallRipV14Score": 59.0, "financialRipV5Score": 62.0},
            source_ranking_method_version="budget_product_ranking_v2",
            prepare_quantity=lambda q: _Fake("p", q),
            source_authority_fingerprint="f", expected_source_authority_fingerprint="f")
    out = bo3.run_dual_best_open_v3(build(1))
    assert out["overallResult"]["threshold"]["priceCents"] == 620
    assert out["financialResult"]["threshold"]["priceCents"] == 610
    for axis in ("overallResult", "financialResult"):
        assert out[axis]["methodVersion"] == bo3.BEST_OPEN_PRICE_V3_METHOD_VERSION
        assert "benchmarkOverallRipV12Score" not in out[axis]
        assert out[axis]["exactness"]["thresholdWins"] and out[axis]["exactness"]["oneCentMaximal"]
    assert out["overallResult"]["benchmarkOverallRipV14Score"] == 61.0
    with pytest.raises(BestOpenPriceSearchError):
        bo3.build_dual_best_open_v3_search(
            product_id="p", budget_cents=1000, current_price_cents=500, current_quantity=2,
            overall_v14_current_rank=1, financial_v5_current_rank=1,
            overall_v14_benchmark={}, financial_v5_benchmark={},
            source_ranking_method_version="budget_product_ranking_v1",
            prepare_quantity=lambda q: _Fake("p", q),
            source_authority_fingerprint="f", expected_source_authority_fingerprint="f")
