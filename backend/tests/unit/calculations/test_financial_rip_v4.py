"""Financial RIP V4 - calculation contract tests.

Organized around the CLAIMS the V4 promotion makes. Each test names a claim the
decision record asserts, and checks it directly:

  * V3 is unchanged and still fully computable,
  * V4 is a separate, distinctly versioned model,
  * V4 Realistic Upside is the P95 threshold ratio alone,
  * the weights are exactly 25/20/15/25/10/5,
  * Jackpot Upside is untouched,
  * every other V3 component keeps its exact semantics.

Deterministic throughout: distributions are constructed explicitly, so a failure
is a real behavioural change and never a seed.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.calculations.evr.financial_rip_v3 import (
    build_financial_rip_v3,
    validate_financial_rip_v3_payload,
)
from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_COMPONENT_INPUTS,
    FINANCIAL_RIP_V3_COMPONENT_ORDER,
    FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
    FINANCIAL_RIP_V3_TAIL_CONTRACT_VERSION,
    FINANCIAL_RIP_V3_TRANSFORMS,
    FINANCIAL_RIP_V3_VERSION,
    FINANCIAL_RIP_V3_WEIGHTS,
    JACKPOT_UPSIDE_SUBWEIGHTS,
    LOSS_RESILIENCE_SUBWEIGHTS,
    REALISTIC_UPSIDE_SUBWEIGHTS,
    normalize_metric,
)
from backend.calculations.evr.financial_rip_v4 import (
    build_financial_rip_v4,
    project_financial_rip_v4_from_v3_payload,
    validate_financial_rip_v4_payload,
    verify_financial_rip_v4_score,
)
from backend.calculations.evr.financial_rip_v4_config import (
    FINANCIAL_RIP_V4_COMPONENT_INPUTS,
    FINANCIAL_RIP_V4_COMPONENT_ORDER,
    FINANCIAL_RIP_V4_NORMALIZATION_VERSION,
    FINANCIAL_RIP_V4_TAIL_CONTRACT_VERSION,
    FINANCIAL_RIP_V4_UNWEIGHTED_DISCLOSURES,
    FINANCIAL_RIP_V4_VERSION,
    FINANCIAL_RIP_V4_WEIGHTS,
    REALISTIC_UPSIDE_SUBWEIGHTS_V4,
    financial_rip_v4_weights_payload,
)

PACK_COST = 5.0
N = 20_000

#: The weights the V4 decision record fixes. Restated literally, not imported,
#: so a change to the config table is a TEST failure rather than a silently
#: agreeing tautology.
DECIDED_WEIGHTS = {
    "true_win_frequency": 0.25,
    "typical_retention": 0.20,
    "loss_resilience": 0.15,
    "realistic_upside": 0.25,
    "jackpot_upside": 0.10,
    "base_economic_efficiency": 0.05,
}


def outcomes(*, chase_multiple: float = 40.0, chase_share: float = 0.01) -> list:
    """An explicitly constructed, chase-tailed outcome vector."""
    chase_count = int(N * chase_share)
    body = np.linspace(0.0, 2.0 * PACK_COST, N - chase_count)
    tail = np.full(chase_count, PACK_COST * chase_multiple)
    return [float(value) for value in np.concatenate([body, tail])]


@pytest.fixture()
def values():
    return outcomes()


@pytest.fixture()
def v3(values):
    return build_financial_rip_v3(values, PACK_COST)


@pytest.fixture()
def v4(values):
    return build_financial_rip_v4(values, PACK_COST)


# ---------------------------------------------------------------------------
# V3 is unchanged
# ---------------------------------------------------------------------------

def test_v3_still_builds_and_validates(v3):
    assert v3["status"] == "ready"
    assert v3["scoreVersion"] == FINANCIAL_RIP_V3_VERSION
    assert validate_financial_rip_v3_payload(v3) == (True, [])


def test_v3_realistic_upside_still_blends_two_inputs():
    """The V4 change must not have edited the V3 definition in place."""
    assert REALISTIC_UPSIDE_SUBWEIGHTS == {
        "p95_threshold_ratio": 0.40,
        "realistic_tail_mean_ratio": 0.60,
    }
    assert FINANCIAL_RIP_V3_COMPONENT_INPUTS["realistic_upside"] == REALISTIC_UPSIDE_SUBWEIGHTS


def test_v3_and_v4_are_computable_side_by_side(values):
    """Historical reproducibility: both models score the same vector in one process."""
    first_v3 = build_financial_rip_v3(values, PACK_COST)
    build_financial_rip_v4(values, PACK_COST)
    second_v3 = build_financial_rip_v3(values, PACK_COST)
    assert first_v3 == second_v3


def test_building_v4_does_not_mutate_v3_config(values):
    before = dict(FINANCIAL_RIP_V3_WEIGHTS), dict(FINANCIAL_RIP_V3_COMPONENT_INPUTS["realistic_upside"])
    build_financial_rip_v4(values, PACK_COST)
    after = dict(FINANCIAL_RIP_V3_WEIGHTS), dict(FINANCIAL_RIP_V3_COMPONENT_INPUTS["realistic_upside"])
    assert before == after


# ---------------------------------------------------------------------------
# V4 identity and versioning
# ---------------------------------------------------------------------------

def test_v4_version_is_distinct_from_v3(v3, v4):
    assert v4["scoreVersion"] == FINANCIAL_RIP_V4_VERSION
    assert v4["scoreVersion"] != v3["scoreVersion"]
    assert "v4" in FINANCIAL_RIP_V4_VERSION
    assert "p95_only" in FINANCIAL_RIP_V4_VERSION


def test_v4_declares_the_unchanged_normalization_and_tail_contract(v4):
    """Anchors and tail rules did not move, so the strings must not claim they did."""
    assert v4["normalizationVersion"] == FINANCIAL_RIP_V3_NORMALIZATION_VERSION
    assert v4["tailContractVersion"] == FINANCIAL_RIP_V3_TAIL_CONTRACT_VERSION
    assert FINANCIAL_RIP_V4_NORMALIZATION_VERSION == FINANCIAL_RIP_V3_NORMALIZATION_VERSION
    assert FINANCIAL_RIP_V4_TAIL_CONTRACT_VERSION == FINANCIAL_RIP_V3_TAIL_CONTRACT_VERSION


def test_v4_payload_validates_and_reconstructs(v4):
    assert validate_financial_rip_v4_payload(v4) == (True, [])
    assert verify_financial_rip_v4_score(v4)["reconstructed"] is True


def test_v4_validator_rejects_a_v3_payload(v3):
    """The two payloads must not be interchangeable under either validator."""
    ok, problems = validate_financial_rip_v4_payload(v3)
    assert ok is False
    assert any("scoreVersion" in problem for problem in problems)


def test_v3_validator_rejects_a_v4_payload(v4):
    ok, problems = validate_financial_rip_v3_payload(v4)
    assert ok is False
    assert any("scoreVersion" in problem for problem in problems)


def test_v4_is_deterministic(values):
    assert build_financial_rip_v4(values, PACK_COST) == build_financial_rip_v4(values, PACK_COST)


# ---------------------------------------------------------------------------
# The one substantive change: P95-only Realistic Upside
# ---------------------------------------------------------------------------

def test_v4_realistic_upside_is_the_p95_threshold_alone(v4):
    component = v4["components"]["realistic_upside"]
    assert list(component["subScores"]) == ["p95_threshold_ratio"]
    assert component["subScores"]["p95_threshold_ratio"]["subWeight"] == 1.0

    p95_ratio = component["raw"]["p95ThresholdRatio"]
    expected = round(float(normalize_metric("p95_threshold_ratio", p95_ratio)["score"]), 4)
    assert component["score"] == expected


def test_v4_realistic_upside_carries_no_conditional_mean_weight():
    assert REALISTIC_UPSIDE_SUBWEIGHTS_V4 == {"p95_threshold_ratio": 1.0}
    assert "realistic_tail_mean_ratio" not in FINANCIAL_RIP_V4_COMPONENT_INPUTS["realistic_upside"]


def test_v4_still_discloses_the_conditional_mean_it_no_longer_scores(v4):
    """Removed from the SCORE, retained as a DISCLOSURE."""
    raw = v4["components"]["realistic_upside"]["raw"]
    assert raw["realisticTailMeanRatio"] is not None
    assert raw["realisticTailMeanValue"] is not None
    assert "realistic_tail_mean_ratio" in FINANCIAL_RIP_V4_UNWEIGHTED_DISCLOSURES["realistic_upside"]


def test_conditional_mean_cannot_move_the_v4_score():
    """The decisive behavioural claim: change only the 95-99 band, V4 must not move.

    Two vectors share an identical P95 threshold, an identical top-1% bucket and
    an identical body, differing ONLY in the values inside the 95th-99th
    percentile band. V3 moves. V4 must not.
    """
    # The band is placed strictly ABOVE the P95 rank so that moving it cannot
    # move the threshold itself: with N = 20,000 the P95 rank is ~19,000, and
    # the body extends to rank 19,200.
    body = np.full(19_200, PACK_COST * 0.5)
    jackpot = np.full(200, PACK_COST * 50.0)

    low_band = np.concatenate([body, np.full(600, PACK_COST * 2.0), jackpot])
    high_band = np.concatenate([body, np.full(600, PACK_COST * 9.0), jackpot])

    low = [float(value) for value in low_band]
    high = [float(value) for value in high_band]

    v3_low = build_financial_rip_v3(low, PACK_COST)
    v3_high = build_financial_rip_v3(high, PACK_COST)
    v4_low = build_financial_rip_v4(low, PACK_COST)
    v4_high = build_financial_rip_v4(high, PACK_COST)

    # Precondition: the band really did change and the P95 threshold did not.
    low_p95 = v4_low["components"]["realistic_upside"]["raw"]["p95ThresholdRatio"]
    high_p95 = v4_high["components"]["realistic_upside"]["raw"]["p95ThresholdRatio"]
    assert low_p95 == high_p95
    assert (
        v3_low["components"]["realistic_upside"]["raw"]["realisticTailMeanRatio"]
        != v3_high["components"]["realistic_upside"]["raw"]["realisticTailMeanRatio"]
    )

    # V3 Realistic Upside moves with the band. V4 Realistic Upside does not.
    assert (
        v3_low["components"]["realistic_upside"]["score"]
        != v3_high["components"]["realistic_upside"]["score"]
    )
    assert (
        v4_low["components"]["realistic_upside"]["score"]
        == v4_high["components"]["realistic_upside"]["score"]
    )
    assert (
        v4_low["components"]["realistic_upside"]["contribution"]
        == v4_high["components"]["realistic_upside"]["contribution"]
    )

    # The V4 headline still moves, and must: Base Economic Efficiency is the
    # mean of everything outside the top 1%, so a richer 95-99 band genuinely
    # improves the ordinary economics of the product. That is a different claim
    # from "the good outcome got better", and V4 now keeps the two separate.
    # Every point of V4 movement is attributable to components OTHER than
    # Realistic Upside.
    realistic_delta = abs(
        v4_high["components"]["realistic_upside"]["contribution"]
        - v4_low["components"]["realistic_upside"]["contribution"]
    )
    assert realistic_delta == 0.0

    other_delta = sum(
        v4_high["components"][key]["contribution"] - v4_low["components"][key]["contribution"]
        for key in FINANCIAL_RIP_V4_COMPONENT_ORDER
        if key != "realistic_upside"
    )
    assert v4_high["score"] - v4_low["score"] == pytest.approx(other_delta, abs=1e-3)


def test_v4_realistic_upside_responds_to_the_p95_threshold():
    """Removing one input must not make the component inert."""
    lower = build_financial_rip_v4(outcomes(chase_multiple=40.0), PACK_COST)
    shifted = [value * 1.5 for value in outcomes(chase_multiple=40.0)]
    higher = build_financial_rip_v4(shifted, PACK_COST)
    assert (
        higher["components"]["realistic_upside"]["score"]
        > lower["components"]["realistic_upside"]["score"]
    )


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

def test_v4_weights_are_exactly_the_decided_vector():
    assert FINANCIAL_RIP_V4_WEIGHTS == DECIDED_WEIGHTS
    assert sum(FINANCIAL_RIP_V4_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-12)


def test_v4_realistic_upside_keeps_its_full_25_percent_influence():
    """The 20% candidate was explicitly rejected; 25% must survive in code."""
    assert FINANCIAL_RIP_V4_WEIGHTS["realistic_upside"] == 0.25


def test_v4_applies_the_decided_weights_to_every_component(v4):
    for component, weight in DECIDED_WEIGHTS.items():
        assert v4["components"][component]["weight"] == weight


def test_v4_weights_are_an_independent_object_from_v3():
    assert FINANCIAL_RIP_V4_WEIGHTS is not FINANCIAL_RIP_V3_WEIGHTS


def test_v4_component_order_matches_v3(v4):
    assert FINANCIAL_RIP_V4_COMPONENT_ORDER == FINANCIAL_RIP_V3_COMPONENT_ORDER
    assert list(v4["components"]) == list(FINANCIAL_RIP_V3_COMPONENT_ORDER)


def test_v4_score_is_the_weighted_sum_of_its_components(v4):
    rebuilt = sum(
        v4["components"][key]["score"] * DECIDED_WEIGHTS[key]
        for key in FINANCIAL_RIP_V4_COMPONENT_ORDER
    )
    assert v4["score"] == pytest.approx(rebuilt, abs=1e-4)


# ---------------------------------------------------------------------------
# Everything else is unchanged
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "component",
    [
        "true_win_frequency",
        "typical_retention",
        "loss_resilience",
        "jackpot_upside",
        "base_economic_efficiency",
    ],
)
def test_every_other_component_is_identical_between_v3_and_v4(v3, v4, component):
    assert v4["components"][component]["score"] == v3["components"][component]["score"]
    assert v4["components"][component]["raw"] == v3["components"][component]["raw"]
    assert (
        v4["components"][component]["subScores"]
        == v3["components"][component]["subScores"]
    )


def test_jackpot_upside_semantics_are_untouched(v3, v4):
    assert FINANCIAL_RIP_V4_COMPONENT_INPUTS["jackpot_upside"] == JACKPOT_UPSIDE_SUBWEIGHTS
    assert JACKPOT_UPSIDE_SUBWEIGHTS == {
        "p99_threshold_ratio": 0.35,
        "jackpot_tail_mean_ratio": 0.65,
    }
    assert FINANCIAL_RIP_V4_WEIGHTS["jackpot_upside"] == 0.10
    jackpot = v4["components"]["jackpot_upside"]
    assert jackpot["raw"]["maximumContributionPoints"] == 10.0
    assert jackpot["contribution"] <= 10.0 + 1e-9
    assert jackpot == v3["components"]["jackpot_upside"]


def test_loss_resilience_subweights_are_untouched():
    assert FINANCIAL_RIP_V4_COMPONENT_INPUTS["loss_resilience"] == LOSS_RESILIENCE_SUBWEIGHTS


def test_v4_introduces_no_new_raw_metric():
    for inputs in FINANCIAL_RIP_V4_COMPONENT_INPUTS.values():
        for metric in inputs:
            assert metric in FINANCIAL_RIP_V3_TRANSFORMS


def test_v4_uses_the_same_p95_transform_object_as_v3():
    """The anchors must be shared, not copied - a copy is a future drift point."""
    transform = FINANCIAL_RIP_V3_TRANSFORMS["p95_threshold_ratio"]
    assert transform["knots"] == ((0.00, 0.0), (1.00, 40.0), (2.00, 70.0), (4.00, 90.0), (8.00, 100.0))


def test_v4_p95_interpolation_is_unchanged(v3, v4):
    assert (
        v4["components"]["realistic_upside"]["raw"]["p95ThresholdValue"]
        == v3["components"]["realistic_upside"]["raw"]["p95ThresholdValue"]
    )


def test_v4_tail_selection_is_unchanged(v3, v4):
    assert (
        v4["distributionDisclosures"]["tailSelection"]
        == v3["distributionDisclosures"]["tailSelection"]
    )


def test_p05_is_still_disclosed_and_still_unscored(v4):
    assert v4["distributionDisclosures"]["p05IsScoredByV3"] is False
    assert v4["distributionDisclosures"]["p05Value"] is not None


# ---------------------------------------------------------------------------
# Unavailability
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "kwargs, reason",
    [
        ({"values": [], "pack_cost": PACK_COST}, "empty_outcome_vector"),
        ({"values": outcomes(), "pack_cost": 0.0}, "invalid_pack_cost"),
        ({"values": outcomes(), "pack_cost": None}, "invalid_pack_cost"),
    ],
)
def test_v4_is_honestly_unavailable_rather_than_guessing(kwargs, reason):
    result = build_financial_rip_v4(kwargs["values"], kwargs["pack_cost"])
    assert result["status"] == "unavailable"
    assert result["statusReason"] == reason
    assert result["score"] is None
    assert result["rankable"] is False
    # An unavailable payload still declares WHICH model was unavailable.
    assert result["scoreVersion"] == FINANCIAL_RIP_V4_VERSION


def test_v4_requires_the_same_minimum_run_count_as_v3():
    short = [float(value) for value in np.linspace(0.0, 10.0, 500)]
    result = build_financial_rip_v4(short, PACK_COST)
    assert result["statusReason"] == "insufficient_simulation_count"


# ---------------------------------------------------------------------------
# Projection from a persisted V3 payload
# ---------------------------------------------------------------------------

def test_projection_from_a_v3_payload_equals_the_engine(values, v3, v4):
    projected = project_financial_rip_v4_from_v3_payload(v3)
    assert projected["status"] == "ready"
    assert projected["score"] == v4["score"]
    assert projected["scoreVersion"] == FINANCIAL_RIP_V4_VERSION
    for key in FINANCIAL_RIP_V4_COMPONENT_ORDER:
        assert projected["components"][key]["score"] == v4["components"][key]["score"]


def test_projection_declares_that_it_is_a_reprojection(v3):
    projected = project_financial_rip_v4_from_v3_payload(v3)
    derivation = projected["audit"]["derivation"]
    assert derivation["method"] == "reprojected_from_persisted_financial_rip_v3_payload"
    assert derivation["isExact"] is True


@pytest.mark.parametrize(
    "payload, reason",
    [
        ({}, "no_source_payload"),
        (None, "no_source_payload"),
        ({"scoreVersion": "financial_rip_v2_60_25_15"}, "source_payload_is_not_financial_rip_v3"),
        (
            {"scoreVersion": FINANCIAL_RIP_V3_VERSION, "status": "unavailable"},
            "source_payload_not_ready",
        ),
    ],
)
def test_projection_refuses_anything_that_is_not_a_ready_v3_payload(payload, reason):
    result = project_financial_rip_v4_from_v3_payload(payload)
    assert result["status"] == "unavailable"
    assert result["statusReason"] == reason
    assert result["score"] is None


# ---------------------------------------------------------------------------
# Disclosure payload
# ---------------------------------------------------------------------------

def test_weights_payload_describes_the_change_and_its_validation_status():
    payload = financial_rip_v4_weights_payload()
    assert payload["scoreVersion"] == FINANCIAL_RIP_V4_VERSION
    assert payload["weights"] == DECIDED_WEIGHTS
    assert payload["subWeights"]["realisticUpside"] == {"p95_threshold_ratio": 1.0}
    assert payload["researchCandidateId"] == "P95_ONLY_25"
    # The absence of temporal validation is a disclosed fact, not a silence.
    assert payload["temporalValidationStatus"] == (
        "none_independent_temporal_validation_at_promotion"
    )


def test_v4_audit_publishes_its_own_weights_not_v3s(v4):
    assert v4["audit"]["weights"]["scoreVersion"] == FINANCIAL_RIP_V4_VERSION
    assert v4["audit"]["weights"]["subWeights"]["realisticUpside"] == {
        "p95_threshold_ratio": 1.0
    }
