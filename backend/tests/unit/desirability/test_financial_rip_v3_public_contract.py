"""Financial RIP V3 / Overall RIP V5 — public service and contract tests.

The claims under test:

  * Financial RIP V2 and Overall RIP v4 still compute exactly what they did,
  * Overall RIP V5 is 0.90 * Financial RIP V3 + 0.10 * CA7, with the same 90/10
    relationship v4 uses and NO fallback to V2 or to Universal Set Desirability,
  * the V3 ranking uses the ABSOLUTE fixed-anchor score, so a cohort change
    cannot move a score (only a rank),
  * a missing V3 does not poison V2 - and is never silently replaced by it,
  * the v5 contract is internally consistent and keeps legacy behind an explicit
    namespace,
  * the ranked leaderboard and the set page read the SAME run.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_COMPONENT_ORDER,
    FINANCIAL_RIP_V3_VERSION,
    OVERALL_RIP_V5_VERSION,
    PUBLIC_RIP_CONTRACT_V5_VERSION,
)
from backend.desirability.public_rip_contract_v4 import build_public_rip_contract_v4
from backend.desirability.public_rip_contract_v5 import build_public_rip_contract_v5
from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
    FINANCIAL_RIP_V2_VERSION,
    FINANCIAL_RIP_V4_VERSION,
    OVERALL_RIP_V4_VERSION,
    OVERALL_RIP_V6_VERSION,
    OVERALL_RIP_V8_VERSION,
    OVERALL_RIP_V10_VERSION,
    OVERALL_RIP_V12_VERSION,
    canonical_financial_rip_is_v3,
    canonical_financial_rip_is_v4,
    canonical_overall_rip_is_v8,
    canonical_overall_rip_is_v9,
    canonical_overall_rip_is_v10,
    OVERALL_RIP_V9_VERSION,
)
from backend.desirability.weighted_rip import (
    compute_financial_rip,
    compute_financial_rip_v2,
    compute_financial_rip_v3,
    compute_overall_rip,
    compute_overall_rip_v5,
)

PACK_COST = 5.0
N = 20_000


def make_payload(*, top_value: float = 40.0, jackpot_value: float = 500.0) -> dict:
    bulk = np.full(int(N * 0.90), 1.0)
    mid = np.full(int(N * 0.05), 6.0)
    top = np.full(int(N * 0.04), top_value)
    jackpot = np.full(N - bulk.size - mid.size - top.size, jackpot_value)
    values = np.concatenate([bulk, mid, top, jackpot])
    return build_financial_rip_v3(values, PACK_COST)


def make_target(payload: dict, *, ca7: float | None = 70.0, set_id: str = "set-a") -> dict:
    """A ranked target row shaped like the one the explore service produces."""
    pillars = {"profit": 62.0, "safety": 44.0, "stability": 51.0}
    financial_v3 = compute_financial_rip_v3(payload)
    return {
        "target_id": set_id,
        "ripCore": compute_financial_rip(pillars),
        "rip": compute_overall_rip(pillars, ca7),
        "financialRipV3": {
            **financial_v3,
            "scoreVersion": payload.get("scoreVersion"),
            "normalizationVersion": payload.get("normalizationVersion"),
            "components": {
                key: {
                    **(financial_v3.get("components") or {}).get(key, {}),
                    "raw": (payload.get("components") or {}).get(key, {}).get("raw", {}),
                }
                for key in FINANCIAL_RIP_V3_COMPONENT_ORDER
            },
            "depthAndRobustness": payload.get("depthAndRobustness") or {},
            "distributionDisclosures": payload.get("distributionDisclosures") or {},
            "sourceRun": {"calculationRunId": "run-1", "runAt": "2026-08-01", "packCost": PACK_COST},
            "audit": payload.get("audit") or {},
        },
        "overallRipV5": compute_overall_rip_v5(financial_v3.get("score"), ca7),
        "openingExperience": {
            "collectorAppeal": {"score": ca7, "version": "ca7_v1", "rank": 3, "cohortSize": 21},
            "dualPathDepth": {"rawValue": 4.2},
            "chaseAppeal": {"eliteScarcity": 0.31},
            "coverage": {"status": "full", "reasons": []},
        },
        "universalSetDesirability": {"score": 66.0, "rank": 5, "rankedSetCount": 40, "percentile": 0.8},
    }


# ---------------------------------------------------------------------------
# The cutover switch
# ---------------------------------------------------------------------------

def test_canonical_versions_point_at_v4_and_v10():
    """Financial RIP V4 / Overall RIP V10 are now canonical (the V4/V10 cutover).

    V3 and V9 (this module's own subject) are now LEGACY, alongside V5 (90/10
    over legacy CA7), V6 (80/20 over Collector Appeal V2), V7 and V8. Their
    identifiers and their arithmetic are unchanged - only their canonical status
    moved - and the tests below (and elsewhere in this module) still pin that
    arithmetic, and still exercise it directly as history.

    UPDATED FOR THE 2026-09-03 V12 CUTOVER: this test previously asserted that
    V10 was canonical. `CANONICAL_FINANCIAL_RIP_VERSION` stays Financial RIP
    V4 (unchanged by the V12 cutover, which only added Chase Accessibility as
    a third pillar), but `CANONICAL_OVERALL_RIP_VERSION` now resolves to
    Overall RIP V12; V3/V9/V10 remain registered and computable as history but
    are no longer the canonical selection.
    """
    assert CANONICAL_FINANCIAL_RIP_VERSION == FINANCIAL_RIP_V4_VERSION
    assert CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V12_VERSION
    assert canonical_financial_rip_is_v4() is True
    assert canonical_financial_rip_is_v3() is False
    assert canonical_overall_rip_is_v10() is False
    assert canonical_overall_rip_is_v9() is False
    # V8 and V9 are retained and identifiable, but are no longer canonical.
    assert canonical_overall_rip_is_v8() is False
    assert OVERALL_RIP_V8_VERSION != OVERALL_RIP_V9_VERSION
    # Every legacy identifier still exists and is still distinct.
    assert FINANCIAL_RIP_V2_VERSION != FINANCIAL_RIP_V3_VERSION
    assert OVERALL_RIP_V4_VERSION != OVERALL_RIP_V5_VERSION
    assert OVERALL_RIP_V5_VERSION != OVERALL_RIP_V6_VERSION
    assert OVERALL_RIP_V6_VERSION != OVERALL_RIP_V8_VERSION


# ---------------------------------------------------------------------------
# V2 / v4 remain exactly what they were
# ---------------------------------------------------------------------------

def test_financial_rip_v2_is_unchanged_and_still_60_25_15():
    pillars = {"profit": 60.0, "safety": 40.0, "stability": 50.0}
    result = compute_financial_rip(pillars)
    assert result["score"] == pytest.approx(0.60 * 60 + 0.25 * 40 + 0.15 * 50)
    assert result["version"] == FINANCIAL_RIP_V2_VERSION
    # The explicit V2 alias is the same computation, not a second one.
    assert compute_financial_rip_v2(pillars) == result


def test_overall_rip_v4_formula_is_unchanged():
    pillars = {"profit": 60.0, "safety": 40.0, "stability": 50.0}
    v4 = compute_overall_rip(pillars, 70.0)
    financial = compute_financial_rip(pillars)["score"]
    assert v4["score"] == pytest.approx(0.90 * financial + 0.10 * 70.0)
    assert v4["version"] == OVERALL_RIP_V4_VERSION


# ---------------------------------------------------------------------------
# Overall RIP V5
# ---------------------------------------------------------------------------

def test_overall_rip_v5_is_ninety_ten_over_v3_and_ca7():
    result = compute_overall_rip_v5(58.0, 72.0)
    assert result["score"] == pytest.approx(0.90 * 58.0 + 0.10 * 72.0)
    assert result["version"] == OVERALL_RIP_V5_VERSION
    assert result["components"]["financialRipV3"]["weight"] == 0.90
    assert result["components"]["openingDesirability"]["weight"] == 0.10
    assert result["rankable"] is True


def test_overall_rip_v5_shares_the_ninety_ten_relationship_with_v4():
    """Only the financial INPUT changed at the cutover, not the blend."""
    pillars = {"profit": 60.0, "safety": 40.0, "stability": 50.0}
    v2_score = compute_financial_rip(pillars)["score"]
    v4 = compute_overall_rip(pillars, 70.0)
    # Feeding V5 the V2 number reproduces v4 exactly, which is the proof that
    # the weights are identical and only the input differs.
    as_if_v2 = compute_overall_rip_v5(v2_score, 70.0)
    assert as_if_v2["score"] == pytest.approx(v4["score"])


@pytest.mark.parametrize(
    "financial,ca7,missing",
    [(None, 70.0, "financial_rip_v3"), (58.0, None, "opening_desirability_ca7")],
)
def test_overall_rip_v5_is_unavailable_without_both_inputs(financial, ca7, missing):
    result = compute_overall_rip_v5(financial, ca7)
    assert result["score"] is None
    assert result["rankable"] is False
    assert missing in result["missingInputs"]
    assert "never substituted" in result["statusReason"]


def test_overall_rip_v5_never_falls_back_to_v2_or_universal_desirability():
    result = compute_overall_rip_v5(None, 70.0)
    assert result["score"] is None
    # A V2 score exists in this scenario and is deliberately not used.
    assert compute_financial_rip({"profit": 60.0, "safety": 40.0, "stability": 50.0})["score"]
    assert "Financial RIP V2" in result["statusReason"]
    assert "Universal Set Desirability" in result["statusReason"]


# ---------------------------------------------------------------------------
# The V3 consumer validates rather than recomputes
# ---------------------------------------------------------------------------

def test_compute_financial_rip_v3_returns_the_absolute_score_unchanged():
    payload = make_payload()
    result = compute_financial_rip_v3(payload)
    assert result["score"] == payload["score"]
    assert result["normalizationMode"] == "fixed_absolute_anchors"
    assert result["rankable"] is True


def test_compute_financial_rip_v3_rejects_an_invalid_payload_without_scoring_it():
    tampered = json.loads(json.dumps(make_payload()))
    tampered["score"] = 91.0
    result = compute_financial_rip_v3(tampered)
    assert result["score"] is None
    assert result["rankable"] is False
    assert result["validationProblems"]


def test_v3_ranking_uses_absolute_scores_so_a_cohort_change_moves_ranks_not_scores():
    strong = make_payload(top_value=90.0, jackpot_value=900.0)
    weak = make_payload(top_value=8.0, jackpot_value=30.0)

    small_cohort = [("a", strong), ("b", weak)]
    extra = make_payload(top_value=200.0, jackpot_value=5000.0)
    large_cohort = small_cohort + [("c", extra)]

    def rank(cohort):
        scored = [
            (set_id, compute_financial_rip_v3(payload)["score"]) for set_id, payload in cohort
        ]
        scored.sort(key=lambda item: (-item[1], item[0]))
        return {set_id: index for index, (set_id, _) in enumerate(scored, start=1)}, dict(scored)

    small_ranks, small_scores = rank(small_cohort)
    large_ranks, large_scores = rank(large_cohort)

    # SCORES are identical - the added set cannot touch them.
    assert small_scores["a"] == large_scores["a"]
    assert small_scores["b"] == large_scores["b"]
    # RANKS may move, because a rank is a property of a cohort.
    assert large_ranks["a"] >= small_ranks["a"]


def test_v3_ranking_ties_break_deterministically_on_set_id():
    payload = make_payload()
    entries = [("z-set", payload), ("a-set", payload)]
    scored = [(set_id, compute_financial_rip_v3(p)["score"]) for set_id, p in entries]
    scored.sort(key=lambda item: (-item[1], item[0]))
    assert [set_id for set_id, _ in scored] == ["a-set", "z-set"]


# ---------------------------------------------------------------------------
# Public contract v5
# ---------------------------------------------------------------------------

def test_v4_contract_is_byte_for_byte_unchanged_by_the_v5_addition():
    target = make_target(make_payload())
    v4 = build_public_rip_contract_v4(target)
    assert v4["contractVersion"] == "public_rip_contract_v4"
    assert set(v4) == {
        "contractVersion",
        "overallRip",
        "financialRip",
        "openingDesirability",
        "universalSetDesirability",
    }
    # v4's financialRip is still the V2 pillars.
    assert set(v4["financialRip"]["components"]) == {"profit", "safety", "stability"}


def test_v5_contract_publishes_v3_as_financial_rip_and_v5_as_overall_rip():
    target = make_target(make_payload())
    v5 = build_public_rip_contract_v5(target)

    assert v5["contractVersion"] == PUBLIC_RIP_CONTRACT_V5_VERSION
    assert v5["financialRip"]["version"] == FINANCIAL_RIP_V3_VERSION
    assert v5["overallRip"]["version"] == OVERALL_RIP_V5_VERSION
    assert set(v5["financialRip"]["components"]) == {
        "trueWinFrequency",
        "typicalRetention",
        "lossResilience",
        "realisticUpside",
        "jackpotUpside",
        "baseEconomicEfficiency",
    }


def test_v5_financial_score_is_the_absolute_score_not_a_relative_one():
    payload = make_payload()
    v5 = build_public_rip_contract_v5(make_target(payload))
    assert v5["financialRip"]["score"] == payload["score"]
    assert v5["financialRip"]["absoluteScore"] == payload["score"]
    assert v5["financialRip"]["normalizationMode"] == "fixed_absolute_anchors"


def test_v5_legacy_blocks_are_namespaced_and_carry_the_old_models():
    target = make_target(make_payload())
    v5 = build_public_rip_contract_v5(target)
    assert v5["legacy"]["financialRipV2"]["version"] == FINANCIAL_RIP_V2_VERSION
    assert set(v5["legacy"]["financialRipV2"]["components"]) == {"profit", "safety", "stability"}
    assert v5["legacy"]["overallRipV4"]["version"] == OVERALL_RIP_V4_VERSION
    # V2 is NOT reachable under the canonical names.
    assert "profit" not in v5["financialRip"]["components"]


def test_v5_component_blocks_carry_no_weight_field():
    """The six cards show no weighting percentage, so the block carries none."""
    v5 = build_public_rip_contract_v5(make_target(make_payload()))
    for component in v5["financialRip"]["components"].values():
        assert "weight" not in component
    # The weights remain auditable in the audit block.
    assert v5["audit"]["weights"]["weights"]["true_win_frequency"] == 0.25


def test_missing_v3_does_not_poison_v2_and_is_never_replaced_by_it():
    unavailable = build_financial_rip_v3(np.array([1.0, 2.0]), PACK_COST)
    assert unavailable["status"] == "unavailable"
    target = make_target(unavailable)
    v5 = build_public_rip_contract_v5(target)

    # V3 is honestly unavailable.
    assert v5["financialRip"]["score"] is None
    assert v5["financialRip"]["statusReason"]
    assert "NEVER replaced by Financial RIP V2" in v5["financialRip"]["fallbackPolicy"]
    # V2 is untouched and still fully published under the legacy namespace.
    assert v5["legacy"]["financialRipV2"]["absoluteScore"] is not None
    # And the two are different numbers, so no accidental copy happened.
    assert v5["financialRip"]["score"] != v5["legacy"]["financialRipV2"]["absoluteScore"]


def test_v5_overall_is_unavailable_when_ca7_is_missing_but_v3_survives():
    target = make_target(make_payload(), ca7=None)
    v5 = build_public_rip_contract_v5(target)
    assert v5["overallRip"]["score"] is None
    assert v5["overallRip"]["statusReason"]
    assert v5["financialRip"]["score"] is not None


def test_v5_contract_is_internally_consistent():
    target = make_target(make_payload())
    v5 = build_public_rip_contract_v5(target)

    financial = v5["financialRip"]["score"]
    ca7 = v5["openingDesirability"]["absoluteScore"]
    overall = v5["overallRip"]["score"]
    assert overall == pytest.approx(0.90 * financial + 0.10 * ca7, abs=1e-3)

    components = v5["overallRip"]["components"]
    assert components["financialRipV3"]["score"] == pytest.approx(financial)
    assert components["financialRipV3"]["contribution"] == pytest.approx(0.90 * financial, abs=1e-3)
    assert components["openingDesirability"]["contribution"] == pytest.approx(0.10 * ca7, abs=1e-3)


def test_rankings_and_set_page_read_the_same_run():
    """The set page lifts the SAME object the leaderboard ranked."""
    target = make_target(make_payload())
    leaderboard_v5 = build_public_rip_contract_v5(target)

    # `_merge_canonical_rip_contract_into_set_payload` copies these keys verbatim.
    set_page_payload = {
        key: target[key]
        for key in ("rip", "ripCore", "financialRipV3", "overallRipV5")
    }
    set_page_payload["openingExperience"] = target["openingExperience"]
    set_page_payload["universalSetDesirability"] = target["universalSetDesirability"]
    set_page_v5 = build_public_rip_contract_v5(set_page_payload)

    assert set_page_v5["financialRip"]["score"] == leaderboard_v5["financialRip"]["score"]
    assert set_page_v5["overallRip"]["score"] == leaderboard_v5["overallRip"]["score"]
    assert (
        set_page_v5["financialRip"]["sourceRun"]["calculationRunId"]
        == leaderboard_v5["financialRip"]["sourceRun"]["calculationRunId"]
    )
