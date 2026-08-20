import pytest
from backend.scripts.pokemon_explore_rankings_publisher import (
    _score_contract_problems,
    publication_contract,
    validate_publication_payload,
)


def _v10_contract():
    pillar = lambda: {
        "score": 50.0, "absoluteScore": 50.0, "relativeScore": 50.0,
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


def test_score_contract_problems_reads_v10_contract_key():
    target = {"set_id": "set-1", "publicRipContractV10": _v10_contract()}
    assert _score_contract_problems(target) == []


def test_score_contract_problems_flags_missing_v10_contract():
    problems = _score_contract_problems({"set_id": "set-1"})
    assert problems == ["set-1: publicRipContractV10 is missing"]


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
