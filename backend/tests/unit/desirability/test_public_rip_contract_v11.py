"""Public RIP contract V11 - SHADOW contract carrying Overall RIP V12.

Phase 14 E: raw Accessibility distinct from A_score, V12 composition correct,
ECE absent, Chase Depth diagnostic only, no "chance of a chase" string
anywhere in this module's source or output.
"""

from __future__ import annotations

import inspect

from backend.desirability.public_rip_contract_v10 import PUBLIC_RIP_CONTRACT_V10_KEY
from backend.desirability.public_rip_contract_v11 import (
    CHASE_ACCESSIBILITY_PUBLIC_QUESTION,
    CHASE_ACCESSIBILITY_TECHNICAL_TOOLTIP,
    PUBLIC_RIP_CONTRACT_V11_KEY,
    PUBLIC_RIP_CONTRACT_V11_VERSION,
    build_public_rip_contract_v11,
)
from backend.desirability.scoring_config import (
    CANONICAL_OVERALL_RIP_VERSION,
    OVERALL_RIP_V10_VERSION,
    OVERALL_RIP_V12_VERSION,
    canonical_public_rip_contract_version,
)


def _target():
    return {
        "overallRipV10": {"score": 71.0, "version": OVERALL_RIP_V10_VERSION,
                           "rankable": True, "components": {"financialRipV4": {"score": 70.0}}},
        "financialRipV4": {"score": 70.0, "version": "financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5"},
        "overallRipV12": {
            "score": 68.4, "version": OVERALL_RIP_V12_VERSION, "status": "ready",
            "rankable": True,
            "components": {
                "financialRipV4": {"score": 70.0, "weight": 0.86},
                "chaseAccessibility": {"raw": 0.002, "score": 50.0, "weight": 0.04},
                "collectorAppeal": {"score": 60.0, "weight": 0.10},
            },
        },
        "chaseAccessibility": {
            "chaseAccessibility": 0.002,
            "chaseAccessibilityPct": 0.2,
            "chaseAccessibilityStatus": "ready",
            "chaseAccessibilityVersion": "chase_accessibility_v1_hc_value_squared_modeled_probability",
            "chaseDepth": 12.4,
            "mappedHcMass": 1.0,
        },
        "collectorAppeal": {},
        "openingExperience": {},
    }


def test_v11_is_not_canonical():
    assert canonical_public_rip_contract_version() != PUBLIC_RIP_CONTRACT_V11_VERSION
    assert CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V10_VERSION


def test_v11_embeds_v10_unchanged():
    target = _target()
    target[PUBLIC_RIP_CONTRACT_V10_KEY] = {"marker": "v10-was-here"}
    contract = build_public_rip_contract_v11(target)
    assert contract[PUBLIC_RIP_CONTRACT_V10_KEY] == {"marker": "v10-was-here"}


def test_raw_accessibility_distinct_from_a_score():
    contract = build_public_rip_contract_v11(_target())
    raw = contract["chaseAccessibility"]["value"]
    a_score = contract["overallRipV12"]["components"]["chaseAccessibility"]["score"]
    assert raw == 0.002
    assert a_score == 50.0
    assert raw != a_score  # two different scales, never confused


def test_v12_composition_names_exact_three_inputs_and_weights():
    contract = build_public_rip_contract_v11(_target())
    composition = contract["overallRipV12Composition"]
    assert composition["inputs"] == {
        "financialRip": "financial_rip_v4",
        "chaseAccessibility": "chase_accessibility_v1",
        "collectorAppeal": "collector_appeal_v5",
    }
    assert composition["weights"]["financial_rip"] == 0.86
    assert composition["weights"]["chase_accessibility"] == 0.04
    assert composition["weights"]["collector_appeal"] == 0.10
    assert composition["version"] == OVERALL_RIP_V12_VERSION


def test_v12_block_marked_shadow_not_canonical():
    contract = build_public_rip_contract_v11(_target())
    assert contract["overallRipV12"]["canonical"] is False


def test_chase_depth_present_only_as_diagnostic_never_in_composition_inputs():
    contract = build_public_rip_contract_v11(_target())
    assert contract["chaseAccessibility"]["chaseDepth"] == 12.4
    composition_inputs = contract["overallRipV12Composition"]["inputs"]
    assert "chaseDepth" not in composition_inputs
    assert "chase_depth" not in composition_inputs


def test_no_ece_anywhere_in_the_module_source():
    import backend.desirability.public_rip_contract_v11 as module
    source = inspect.getsource(module)
    assert "ECE" not in source
    assert "expected_calibration_error" not in source.lower()


def test_no_chance_of_a_chase_string_in_output():
    # The module docstring legitimately DISCUSSES the forbidden phrase (as
    # chase_accessibility.py's own docstring does) to document what must never
    # be emitted. What must never happen is the phrase appearing in actual
    # CONTRACT OUTPUT served to a consumer.
    contract = build_public_rip_contract_v11(_target())
    assert "chance of a chase" not in str(contract).lower()


def test_approved_copy_is_used_verbatim():
    contract = build_public_rip_contract_v11(_target())
    assert contract["chaseAccessibility"]["publicQuestion"] == CHASE_ACCESSIBILITY_PUBLIC_QUESTION
    assert contract["chaseAccessibility"]["technicalTooltip"] == CHASE_ACCESSIBILITY_TECHNICAL_TOOLTIP
    assert CHASE_ACCESSIBILITY_PUBLIC_QUESTION == (
        "How reachable are this set's most important cards from a pack?"
    )
    assert CHASE_ACCESSIBILITY_TECHNICAL_TOOLTIP == (
        "How accessible the set's most important collectible value is from one pack."
    )


def test_v12_unavailable_status_preserved_not_coerced_to_zero():
    target = _target()
    target["overallRipV12"] = {
        "score": None, "version": OVERALL_RIP_V12_VERSION,
        "status": "unavailable_missing_input", "rankable": False,
        "missingInputs": ["chase_accessibility_v1"], "components": {},
    }
    contract = build_public_rip_contract_v11(target)
    assert contract["overallRipV12"]["score"] is None
    assert contract["overallRipV12"]["score"] != 0.0
    assert contract["overallRipV12"]["status"] == "unavailable_missing_input"
