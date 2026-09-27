import copy

import numpy as np
import pytest

from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.calculations.evr.financial_rip_v4 import build_financial_rip_v4
from backend.calculations.evr.financial_rip_v4_config import FINANCIAL_RIP_V4_VERSION
from backend.calculations.evr.financial_rip_v5 import (
    build_financial_rip_v5, project_financial_rip_v5_from_v4_payload,
    shortfall_resilience_from_raw, validate_financial_rip_v5_payload,
    verify_financial_rip_v5_score,
)
from backend.calculations.evr.financial_rip_v5_candidate import (
    score_financial_rip_v5_candidate, shortfall_resilience_direct,
)
from backend.calculations.evr.financial_rip_v5_config import (
    FINANCIAL_RIP_V5_VERSION, FINANCIAL_RIP_V5_WEIGHTS,
)

COSTS = [.25, 1, 2.75, 10]


def _values(seed=71):
    return np.random.default_rng(seed).choice([0, .2, .6, 1, 3, 15], 10001)


@pytest.mark.parametrize("cost", COSTS)
def test_reproduces_frozen_research_candidate(cost):
    values = _values()
    prod = build_financial_rip_v5(values, cost)
    research = score_financial_rip_v5_candidate(values, cost)
    assert prod["score"] == research["score"]
    for key, block in research["components"].items():
        assert prod["components"][key]["score"] == block["score"]
        assert prod["components"][key]["contribution"] == block["contribution"]
    assert list(prod["components"]) == list(FINANCIAL_RIP_V5_WEIGHTS)


def test_identity_is_distinct_and_v4_is_isolated():
    values = _values()
    before = build_financial_rip_v4(values, 1)
    v5 = build_financial_rip_v5(values, 1)
    assert build_financial_rip_v4(values, 1) == before
    assert v5["scoreVersion"] == FINANCIAL_RIP_V5_VERSION != FINANCIAL_RIP_V4_VERSION
    assert v5["configVersion"] != before["configVersion"]
    assert v5["audit"]["weights"]["scoreVersion"] == FINANCIAL_RIP_V5_VERSION
    assert "loss_resilience" not in v5["components"]
    for key in FINANCIAL_RIP_V5_WEIGHTS:
        if key != "shortfall_resilience":
            assert v5["components"][key] == before["components"][key]
    assert "average_retention_given_loss" not in v5["audit"]["normalizedInputs"]


@pytest.mark.parametrize("cost", COSTS)
def test_direct_parity_score_reconstruction_and_raw_persistence(cost):
    values = _values(72)
    v5 = build_financial_rip_v5(values, cost)
    sr = v5["components"]["shortfall_resilience"]
    assert sr["score"] == pytest.approx(shortfall_resilience_direct(values, cost), abs=1e-4)
    assert shortfall_resilience_from_raw(sr["raw"]) == pytest.approx(
        shortfall_resilience_direct(values, cost), abs=1e-6)
    assert v5["score"] == round(sum(v5["components"][k]["score"] * w
                                    for k, w in FINANCIAL_RIP_V5_WEIGHTS.items()), 4)
    assert verify_financial_rip_v5_score(v5)["reconstructed"]
    assert validate_financial_rip_v5_payload(v5) == (True, [])


def test_validator_rejects_mixed_or_tampered_payloads():
    v5 = build_financial_rip_v5(_values(), 1)
    v4 = build_financial_rip_v4(_values(), 1)
    assert validate_financial_rip_v5_payload(v4)[0] is False
    tampered = copy.deepcopy(v5)
    tampered["components"]["shortfall_resilience"]["raw"]["expectedDeepShortfall"] += .01
    assert validate_financial_rip_v5_payload(tampered)[0] is False
    mixed = copy.deepcopy(v5)
    mixed["components"]["loss_resilience"] = copy.deepcopy(v4["components"]["loss_resilience"])
    assert validate_financial_rip_v5_payload(mixed)[0] is False
    stale = copy.deepcopy(v5)
    stale["scoreVersion"] = FINANCIAL_RIP_V4_VERSION
    assert validate_financial_rip_v5_payload(stale)[0] is False
    stripped = copy.deepcopy(v5)
    del stripped["components"]["shortfall_resilience"]["raw"]["sumBelowHalfCost"]
    assert validate_financial_rip_v5_payload(stripped)[0] is False


@pytest.mark.parametrize("win_probability", [.3, .5, .7, .9])
def test_downside_dominance_regression(win_probability):
    n = 10000
    winners = int(n * win_probability)
    low = np.array([0] * (n - winners) + [2] * winners, dtype=float)
    high = np.array([.4] * (n - winners) + [2] * winners, dtype=float)
    a, b = build_financial_rip_v5(low, 1), build_financial_rip_v5(high, 1)
    assert b["components"]["shortfall_resilience"]["score"] >= a["components"]["shortfall_resilience"]["score"]
    assert b["score"] >= a["score"]


def test_payload_projection_fails_closed_and_invalid_input_unavailable():
    v4 = build_financial_rip_v4(_values(), 1)
    projected = project_financial_rip_v5_from_v4_payload(v4)
    assert projected["status"] == "unavailable" and projected["score"] is None
    assert projected["rankable"] is False
    bad = build_financial_rip_v5(_values()[:50], 1)  # below minimum simulation count
    assert bad["status"] == "unavailable" and bad["scoreVersion"] == FINANCIAL_RIP_V5_VERSION
    assert validate_financial_rip_v5_payload(bad)[0] is True
    prepared = PreparedFinancialRipDistribution.prepare(_values())
    assert build_financial_rip_v5(prepared, 1) == build_financial_rip_v5(_values(), 1)
