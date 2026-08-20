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


def test_publisher_has_no_v9_key_fallback():
    import inspect
    from backend.scripts import pokemon_explore_rankings_publisher as mod
    source = inspect.getsource(mod)
    assert '"overallRipV9"' not in source
    assert '"financialRipV3"' not in source
    assert '"publicRipContractV9"' not in source
