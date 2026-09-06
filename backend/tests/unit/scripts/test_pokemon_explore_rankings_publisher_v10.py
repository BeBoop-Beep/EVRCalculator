"""Publisher score-contract validation.

2026-09-05 cutover: the publisher's canonical score-contract validation
(`_score_contract_problems`) moved from `publicRipContractV10` to
`publicRipContractV11` - the CURRENT canonical public RIP contract, which
carries Overall RIP V12 in its stable generic `overallRip` slot. This file
keeps its historical name (it predates the V11/V12 cutover) but its
assertions now exercise the current canonical contract key.
"""
import pytest
from backend.scripts.pokemon_explore_rankings_publisher import (
    _canonical_public_rip_contract_target_key,
    _score_contract_problems,
    publication_contract,
    validate_publication_payload,
)


def _v11_contract():
    pillar = lambda: {
        "score": 50.0, "absoluteScore": 50.0, "relativeScore": 50.0, "leaderNormalizedScore": 50.0,
        "rank": 1, "tier": "A", "rankedSetCount": 22, "cohortFingerprint": "fp",
    }
    return {
        "overallRip": pillar(), "financialRip": {**pillar(), "components": {}},
        "collectorAppeal": {
            **pillar(),
            "components": {
                "rosterDesirability": {
                    "rank": 1, "tier": "A", "rankedSetCount": 22, "relativeScore": 50.0,
                    "modeledPokemon": [{"name": "Pikachu", "desirabilityScore": 90.0}],
                },
                "desirableOutcomeFrequency": {
                    "rank": 1, "tier": "A", "rankedSetCount": 22, "relativeScore": 50.0,
                },
            },
        },
    }


def test_canonical_contract_target_key_is_v11():
    assert _canonical_public_rip_contract_target_key() == "publicRipContractV11"


def test_score_contract_problems_reads_v11_contract_key():
    target = {"set_id": "set-1", "publicRipContractV11": _v11_contract()}
    assert _score_contract_problems(target) == []


def test_score_contract_problems_flags_missing_v11_contract():
    problems = _score_contract_problems({"set_id": "set-1"})
    assert problems == ["set-1: publicRipContractV11 is missing"]


def test_score_contract_problems_ignores_a_v10_only_payload():
    """A superficially-complete `publicRipContractV10` block does NOT satisfy
    the canonical score contract now that canonical validation reads V11 - a
    payload that only carries the historical V10 contract must still fail
    closed rather than being accepted as if it were current."""
    target = {"set_id": "set-1", "publicRipContractV10": _v11_contract()}
    problems = _score_contract_problems(target)
    assert problems == ["set-1: publicRipContractV11 is missing"]


def _dict_key_string_literals(mod):
    """String literals that appear as an actual dict-subscript/`.get()` key in
    executable code -- NOT anywhere else in the module (docstrings, comments,
    other string arguments). ast.parse never sees comments at all, and this
    walk further ignores plain string-constant statements (docstrings), so a
    historical lineage comment like `target["financialRipV3"]` cannot trip
    this check the way a raw substring scan over `inspect.getsource(mod)`
    could -- that previously forced stripping the quotes out of a correct,
    quoted comment purely to dodge this test.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(mod))
    keys = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            slice_node = node.slice
            # Python <3.9 wraps the slice in ast.Index; unwrap if present.
            slice_node = getattr(slice_node, "value", slice_node)
            if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
                keys.add(slice_node.value)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                keys.add(node.args[0].value)
    return keys


def test_publisher_has_no_v9_key_fallback():
    from backend.scripts import pokemon_explore_rankings_publisher as mod

    keys = _dict_key_string_literals(mod)
    assert "overallRipV9" not in keys
    assert "financialRipV3" not in keys
    assert "publicRipContractV9" not in keys


def test_publisher_never_hardcodes_the_old_canonical_v10_literal_as_a_target_read():
    """The publisher may still MENTION `overallRipV10`/`publicRipContractV10`
    (historical-lineage docstrings, the registered-but-superseded entry in the
    canonical-selection authority dict), but the CURRENT ranked-cohort /
    score-contract reads must resolve through the canonical-selection
    authority, not a literal V10 key."""
    from backend.scripts import pokemon_explore_rankings_publisher as mod
    import inspect

    source = inspect.getsource(mod.publication_contract)
    assert '"overallRipV10"' not in source
    source = inspect.getsource(mod.validate_publication_payload)
    assert '"overallRipV10"' not in source
