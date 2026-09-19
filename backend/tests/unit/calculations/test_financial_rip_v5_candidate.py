import numpy as np
import pytest

from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.calculations.evr.financial_rip_v4 import build_financial_rip_v4
from backend.calculations.evr.financial_rip_v5_candidate import (
    WEIGHTS, project_financial_rip_v5_from_payload, score_financial_rip_v5_candidate,
    shortfall_resilience_direct, shortfall_resilience_prepared,
)


@pytest.mark.parametrize("cost", [.01, .5, 1, 2, 10, 100])
def test_direct_prepared_parity_and_bounds(cost):
    values = np.random.default_rng(51).choice([0, .1, .499, .5, .999, 1, 5, 100], 10001)
    prepared = PreparedFinancialRipDistribution.prepare(values)
    direct = shortfall_resilience_direct(values, cost)
    fast = shortfall_resilience_prepared(prepared, cost)
    assert fast == pytest.approx(direct, abs=1e-10)
    assert 0 <= fast <= 100


def test_v4_isolation_five_components_and_reconstruction():
    values = np.random.default_rng(61).choice([0, .2, .6, 1, 3, 15], 10001)
    before = build_financial_rip_v4(values, 1)
    candidate = score_financial_rip_v5_candidate(values, 1)
    after = build_financial_rip_v4(values, 1)
    assert before == after
    assert candidate["researchOnly"] is True
    for key in WEIGHTS:
        if key != "shortfall_resilience":
            assert candidate["components"][key] == before["components"][key]
    assert candidate["score"] == round(sum(candidate["components"][key]["score"] * weight
                                            for key, weight in WEIGHTS.items()), 4)
    assert "shortfall_resilience" in candidate["components"]
    assert "loss_resilience" not in candidate["components"]


@pytest.mark.parametrize("win_probability", [.3, .5, .7, .9])
def test_downside_dominance(win_probability):
    n = 10000
    winners = int(n * win_probability)
    low = np.array([0] * (n - winners) + [2] * winners, dtype=float)
    high = np.array([.4] * (n - winners) + [2] * winners, dtype=float)
    a = score_financial_rip_v5_candidate(low, 1)
    b = score_financial_rip_v5_candidate(high, 1)
    assert b["components"]["shortfall_resilience"]["score"] >= a["components"]["shortfall_resilience"]["score"]
    assert b["score"] >= a["score"]


def test_payload_only_projection_fails_closed():
    source = build_financial_rip_v4(np.array([0, 2] * 5000), 1)
    result = project_financial_rip_v5_from_payload(source)
    assert result["score"] is None
    assert result["rankable"] is False


def test_hard_loss_to_soft_loss_construction_is_real():
    hard = np.array([0] * 4000 + [2] * 6000, dtype=float)
    soft = np.array([.6] * 4000 + [2] * 6000, dtype=float)
    assert not np.array_equal(hard, soft)
    assert np.count_nonzero(hard < .5) > np.count_nonzero(soft < .5)
    assert shortfall_resilience_direct(soft, 1) > shortfall_resilience_direct(hard, 1)


def test_same_ev_and_p50_with_different_downside():
    a = np.array([0] * 2500 + [.6] * 5000 + [2] * 2500, dtype=float)
    b = np.array([.4] * 2500 + [.6] * 5000 + [1.6] * 2500, dtype=float)
    assert abs(a.mean() - b.mean()) < 1e-12
    assert abs(np.median(a) - np.median(b)) < 1e-12
    assert shortfall_resilience_direct(b, 1) > shortfall_resilience_direct(a, 1)


def test_p95_independence_with_fixed_downside():
    a = np.array([.2] * 4000 + [1] * 6000, dtype=float)
    b = np.array([.2] * 4000 + [2] * 6000, dtype=float)
    assert np.percentile(b, 95) - np.percentile(a, 95) >= 1
    assert np.array_equal(a[a < 1], b[b < 1])
    assert shortfall_resilience_direct(a, 1) == pytest.approx(shortfall_resilience_direct(b, 1), abs=1e-12)
