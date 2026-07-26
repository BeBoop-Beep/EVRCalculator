"""Contract tests for the compact public RIP v4 snapshot projection.

Proves the shape both Explore and the set page read: versioned Overall/Financial
blocks, distinct absolute vs relative fields, CA7-gated Overall availability, a
separate Universal Set Desirability, and no large JSONB rollups.
"""

from __future__ import annotations

import copy

from backend.desirability.public_rip_contract_v4 import (
    CONTRACT_VERSION,
    build_public_rip_contract_v4,
)
from backend.desirability.scoring_config import (
    FINANCIAL_RIP_V2_VERSION,
    OVERALL_RIP_V4_VERSION,
)


def _full_target():
    return {
        "rip": {
            "score": 33.81,
            "relativeScore": 92.4,
            "rank": 1,
            "tier": "S",
            "cohortSize": 21,
            "version": OVERALL_RIP_V4_VERSION,
            "components": {
                "financialRip": {"score": 26.9, "weight": 0.90, "contribution": 24.21},
                "openingDesirability": {"score": 96.0, "weight": 0.10, "contribution": 9.6},
            },
        },
        "ripCore": {
            "score": 26.9,
            "relativeScore": 74.1,
            "rank": 8,
            "tier": "B",
            "cohortSize": 21,
            "version": FINANCIAL_RIP_V2_VERSION,
            "components": {
                "profit": {"score": 40.0, "relativeScore": 71.0, "weight": 0.60, "contribution": 24.0, "rank": 6, "cohortSize": 21},
                "safety": {"score": 10.0, "relativeScore": 33.0, "weight": 0.25, "contribution": 2.5, "rank": 9, "cohortSize": 21},
                "stability": {"score": 2.7, "relativeScore": 5.0, "weight": 0.15, "contribution": 0.4, "rank": 12, "cohortSize": 21},
            },
        },
        "universalSetDesirability": {
            "score": 88.0,
            "rank": 3,
            "rankedSetCount": 135,
            "percentile": 97.8,
            "version": "universal_set_desirability_v3",
        },
        "openingExperience": {
            "version": "collector_appeal_ca7_v1",
            "collectorAppeal": {
                "score": 96.0,
                "rank": 2,
                "cohortSize": 21,
                "tier": "A",
                "version": "collector_appeal_ca7_v1",
            },
            "dualPathDepth": {"rawValue": 0.42},
            "chaseAppeal": {"eliteScarcity": 0.61},
            # A large per-subject rollup that must NOT leak into the compact block.
            "topSubjects": [{"subject_name": "Pikachu", "cards": list(range(50))}],
        },
    }


def test_overall_block_is_v4_with_weighted_components():
    contract = build_public_rip_contract_v4(_full_target())
    overall = contract["overallRip"]
    assert overall["version"] == OVERALL_RIP_V4_VERSION
    assert overall["absoluteScore"] == 33.81
    assert overall["rank"] == 1 and isinstance(overall["rank"], int)
    assert overall["rankedSetCount"] == 21
    assert overall["components"]["financialRip"]["weight"] == 0.90
    assert overall["components"]["openingDesirability"]["weight"] == 0.10


def test_financial_block_is_v2_60_25_15():
    contract = build_public_rip_contract_v4(_full_target())
    financial = contract["financialRip"]
    assert financial["version"] == FINANCIAL_RIP_V2_VERSION
    weights = {p: financial["components"][p]["weight"] for p in ("profit", "safety", "stability")}
    assert weights == {"profit": 0.60, "safety": 0.25, "stability": 0.15}


def test_absolute_and_relative_are_distinct_never_conflated():
    contract = build_public_rip_contract_v4(_full_target())
    assert contract["overallRip"]["absoluteScore"] != contract["overallRip"]["relativeScore"]
    assert contract["financialRip"]["absoluteScore"] != contract["financialRip"]["relativeScore"]
    # Pillars carry an absolute AND a cohort-relative public score (restoring
    # main's relative_*_score presentation), never conflated.
    assert contract["financialRip"]["components"]["profit"]["absoluteScore"] == 40.0
    assert contract["financialRip"]["components"]["profit"]["relativeScore"] == 71.0


def test_public_score_is_the_relative_score_absolute_is_the_raw_output():
    """`score` is the canonical PUBLIC relative score; `absoluteScore` is raw."""
    contract = build_public_rip_contract_v4(_full_target())

    overall = contract["overallRip"]
    assert overall["score"] == overall["relativeScore"] == 92.4
    assert overall["absoluteScore"] == 33.81
    assert overall["score"] != overall["absoluteScore"]
    assert overall["normalizationMode"] == "cohort_min_max"

    financial = contract["financialRip"]
    assert financial["score"] == financial["relativeScore"] == 74.1
    assert financial["absoluteScore"] == 26.9
    assert financial["score"] != financial["absoluteScore"]
    assert financial["normalizationMode"] == "cohort_min_max"


def test_missing_relative_leaves_public_score_null_never_promotes_absolute():
    """A present absolute with a null relative must NOT promote the absolute."""
    target = _full_target()
    target["rip"]["relativeScore"] = None
    target["ripCore"]["relativeScore"] = None

    contract = build_public_rip_contract_v4(target)
    # Public score stays null even though the raw formula output is present.
    assert contract["overallRip"]["score"] is None
    assert contract["overallRip"]["absoluteScore"] == 33.81
    assert contract["financialRip"]["score"] is None
    assert contract["financialRip"]["absoluteScore"] == 26.9


def test_opening_desirability_is_ca7_with_price_independent_signals():
    contract = build_public_rip_contract_v4(_full_target())
    opening = contract["openingDesirability"]
    assert opening["version"] == "collector_appeal_ca7_v1"
    assert opening["absoluteScore"] == 96.0
    assert opening["components"] == {
        "universalRoster": 88.0,
        "obtainableDesirableCards": 0.42,
        "chaseIntensity": 0.61,
    }


def test_universal_set_desirability_is_a_separate_block():
    contract = build_public_rip_contract_v4(_full_target())
    universal = contract["universalSetDesirability"]
    assert universal["score"] == 88.0
    assert universal["rank"] == 3
    assert universal["rankedSetCount"] == 135
    assert universal["version"] == "universal_set_desirability_v3"


def test_missing_ca7_keeps_financial_and_universal_but_removes_overall():
    target = _full_target()
    # CA7 unavailable: no collectorAppeal score, and Overall RIP recomputed as
    # unavailable upstream (score None) with a reason.
    target["openingExperience"]["collectorAppeal"]["score"] = None
    target["rip"] = {
        "score": None,
        "version": OVERALL_RIP_V4_VERSION,
        "status": "unavailable_missing_input",
        "statusReason": "Overall RIP needs a valid CA7 Opening Desirability score.",
        "components": {},
    }
    target["openingExperience"]["coverage"] = {"reasons": ["dual_path_depth_unavailable_no_pull_model"]}

    contract = build_public_rip_contract_v4(target)
    assert contract["overallRip"]["absoluteScore"] is None
    assert contract["overallRip"]["status"] == "unavailable_missing_input"
    assert contract["overallRip"]["statusReason"]
    # Financial RIP and Universal Set Desirability stay fully published.
    assert contract["financialRip"]["absoluteScore"] == 26.9
    assert contract["universalSetDesirability"]["score"] == 88.0
    # Opening Desirability itself reports unavailable, never zero.
    assert contract["openingDesirability"]["absoluteScore"] is None
    assert contract["openingDesirability"]["absoluteScore"] != 0


def test_compact_payload_excludes_large_jsonb_rollups():
    contract = build_public_rip_contract_v4(_full_target())
    opening = contract["openingDesirability"]
    # The heavy per-subject rollup present on the source openingExperience must
    # not appear anywhere in the compact projection.
    assert "topSubjects" not in opening
    assert "topSubjects" not in contract
    text = repr(contract)
    assert "Pikachu" not in text


def test_projection_does_not_mutate_the_source_target():
    target = _full_target()
    snapshot = copy.deepcopy(target)
    build_public_rip_contract_v4(target)
    assert target == snapshot


def test_null_target_is_all_unavailable_never_throws():
    contract = build_public_rip_contract_v4({})
    assert contract["contractVersion"] == CONTRACT_VERSION
    assert contract["overallRip"]["absoluteScore"] is None
    assert contract["financialRip"]["absoluteScore"] is None
    assert contract["openingDesirability"]["absoluteScore"] is None
    assert contract["universalSetDesirability"]["score"] is None
