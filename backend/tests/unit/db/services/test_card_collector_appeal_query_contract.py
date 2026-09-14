from types import SimpleNamespace

from backend.db.services.card_collector_appeal_query_service import (
    _pointer_cache,
    _public_row,
    query_card_collector_appeal,
)


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


class _Query:
    def __init__(self, client, table):
        self.client, self.name = client, table
        self.ops = []

    def __getattr__(self, operation):
        def chained(*args, **kwargs):
            self.ops.append((operation, args, kwargs))
            return self
        return chained

    def execute(self):
        self.client.calls.append((self.name, self.ops))
        rows, count = self.client.responses.get(self.name, ([], None))
        return SimpleNamespace(data=rows, count=count)


class _Client:
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def table(self, name):
        return _Query(self, name)


def test_query_pages_prepared_authority_then_batch_enriches_only_page():
    _pointer_cache.clear()
    run_id = "e282f26e-2136-4105-b0a3-f0974c4d9d70"
    card_id = "3f01b1db-e997-4c39-8c25-ddcdeb4e0785"
    set_id = "1e62ec39-2f9f-4d13-baaa-163952e31cc3"
    era_id = "53786e20-84f6-4dea-a61c-bcae3a3b96c4"
    client = _Client({
        "pokemon_collector_appeal_current": ([{"model_run_id": run_id, "model_version": "v7", "as_of_date": "2026-09-12"}], None),
        "pokemon_card_collector_appeal_rankings": ([{
            "model_run_id": run_id, "pokemon_canonical_card_id": card_id, "set_id": set_id,
            "card_name": "Pikachu", "rarity": "Rare", "collector_appeal_score": 88,
            "rank": 7, "cohort_size": 18293, "subject_policy": "pokemon",
            "methodology_version": "global", "treatment_category": "illustration",
        }], 18293),
        "pokemon_canonical_cards": ([{"id": card_id, "image_small_url": "https://img.test/pika.jpg"}], None),
        "pokemon_card_collector_appeal_scores": ([{
            "pokemon_canonical_card_id": card_id, "subject_policy": "pokemon",
            "subject_baseline_score": 91, "artist_recognition_score": 70,
            "playability_score": 60, "confidence": "high", "component_inputs_json": {},
        }], None),
        "sets": ([{"id": set_id, "name": "Test Set", "canonical_key": "test-set", "era_id": era_id}], None),
        "eras": ([{"id": era_id, "name": "Test Era", "canonical_key": "test-era"}], None),
    })

    payload = query_card_collector_appeal(client)

    assert payload["total"] == 18293
    assert payload["rows"][0]["pokemonAppeal"] == 91
    assert payload["rows"][0]["imageSmallUrl"].endswith("pika.jpg")
    names = [name for name, _ in client.calls]
    assert "pokemon_card_collector_appeal_rankings_current_v" not in names
    assert names.count("pokemon_card_collector_appeal_rankings") == 1
    assert names.count("pokemon_canonical_cards") == 1
    assert names.count("pokemon_card_collector_appeal_scores") == 1
    ranking_ops = next(ops for name, ops in client.calls if name == "pokemon_card_collector_appeal_rankings")
    assert any(op == "range" and args == (0, 49) for op, args, _ in ranking_ops)


def test_unknown_era_returns_empty_without_scanning_rankings():
    _pointer_cache.clear()
    client = _Client({
        "pokemon_collector_appeal_current": ([{"model_run_id": "run", "model_version": "v7", "as_of_date": "2026-09-12"}], None),
        "eras": ([], None),
    })
    payload = query_card_collector_appeal(client, era="does-not-exist")
    assert payload["available"] is True and payload["total"] == 0
    assert not any(name == "pokemon_card_collector_appeal_rankings" for name, _ in client.calls)
