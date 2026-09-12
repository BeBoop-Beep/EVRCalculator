from backend.db.services.card_collector_appeal_query_service import _public_row


def test_subject_baselines_are_mutually_exclusive_and_missing_stays_missing():
    pokemon = _public_row({"subject_policy": "pokemon", "subject_baseline_score": 81})
    trainer = _public_row({"subject_policy": "trainer", "subject_baseline_score": 72})
    missing = _public_row({"subject_policy": "pokemon", "subject_baseline_score": None})
    assert pokemon["pokemonAppeal"] == 81 and pokemon["trainerAppeal"] is None
    assert trainer["trainerAppeal"] == 72 and trainer["pokemonAppeal"] is None
    assert missing["pokemonAppeal"] is None


def test_projection_exposes_context_without_inventing_scores():
    payload = _public_row({"treatment_category": "special_illustration", "modeled_pull_probability": None})
    assert payload["treatmentCategory"] == "special_illustration"
    assert "treatmentScore" not in payload
    assert payload["modeledPullProbability"] is None
