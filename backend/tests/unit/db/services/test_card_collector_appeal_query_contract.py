from types import SimpleNamespace
import pytest

from backend.db.services.card_collector_appeal_query_service import (
    _pointer_cache,
    _public_row,
    query_card_collector_appeal,
)


def test_public_projection_excludes_unused_diagnostics():
    payload = _public_row({"subject_policy": "pokemon", "subject_baseline_score": 81,
                           "component_inputs_json": {"internal": True}})
    assert "pokemonAppeal" not in payload
    assert "subjectIdentity" not in payload
    assert "component_inputs_json" not in payload


def test_artist_projection_alone_exposes_artist_names():
    row = {"artist_names": ["Artist"]}
    assert _public_row(row, "artist")["artistNames"] == ["Artist"]
    assert "artistNames" not in _public_row(row, "overall")


class _Query:
    def __init__(self, client, table):
        self.client, self.name = client, table
        self.ops = []

    def __getattr__(self, operation):
        def chained(*args, **kwargs):
            self.ops.append((operation, args, kwargs))
            return self
        return chained

    @property
    def not_(self):
        query = self
        class _Negation:
            def is_(self, *args, **kwargs):
                query.ops.append(("not.is", args, kwargs))
                return query
        return _Negation()

    def execute(self):
        self.client.calls.append((self.name, self.ops))
        rows, count = self.client.responses.get(self.name, ([], None))
        return SimpleNamespace(data=rows, count=count)


class _Client:
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        query = _Query(self, name)
        query.ops.append(("rpc", (params,), {}))
        return query


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
    assert payload["rows"][0]["collectorAppeal"] == 88
    assert payload["rows"][0]["imageSmallUrl"].endswith("pika.jpg")
    names = [name for name, _ in client.calls]
    assert "pokemon_card_collector_appeal_rankings_current_v" not in names
    assert names.count("pokemon_card_collector_appeal_rankings") == 1
    assert names.count("pokemon_canonical_cards") == 1
    assert names.count("pokemon_card_collector_appeal_scores") == 0
    assert names.count("eras") == 0
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


@pytest.mark.parametrize(("lens", "column", "policy"), [
    ("pokemon", "pokemon_appeal", "pokemon"),
    ("trainer", "trainer_appeal", "trainer"),
    ("artist", "artist_appeal", None),
    ("playability", "playability", None),
])
def test_component_lenses_rank_only_available_component_cohort(lens, column, policy):
    _pointer_cache.clear()
    ranking = {"model_run_id": "run", "pokemon_canonical_card_id": "card", "set_id": "set",
               "card_name": "Card", "rarity": "Rare", "collector_appeal_score": 80,
               "rank": 999, "cohort_size": 18293, "subject_policy": policy or "neutral_functional",
               column: 77, "methodology_version": "v7"}
    client = _Client({
        "pokemon_collector_appeal_current": ([{"model_run_id": "run", "model_version": "v7", "as_of_date": "2026-09-11"}], None),
        "pokemon_card_collector_appeal_rankings": ([ranking], 40),
        "get_pokemon_card_component_rankings_v1": ({
            "rows": [{**ranking, "component_rank": 73, "component_score": 77}],
            "total": 1, "componentCohortSize": 40,
        }, None),
        "pokemon_canonical_cards": ([], None),
        "pokemon_card_collector_appeal_scores": ([{"pokemon_canonical_card_id": "card", "subject_policy": policy,
            "subject_baseline_score": 77, "artist_recognition_score": 77, "playability_score": 77,
            "component_inputs_json": {}}], None),
        "sets": ([{"id": "set", "name": "Set", "canonical_key": "set", "era_id": "era"}], None),
        "eras": ([{"id": "era", "name": "Era", "canonical_key": "era"}], None),
    })
    result = query_card_collector_appeal(client, lens=lens)
    assert result["rankSemantics"] == "global_component_cohort"
    assert result["componentCohortSize"] == 40
    assert result["rows"][0]["rank"] == 73 and result["rows"][0]["cohortSize"] == 40
    assert result["rows"][0]["componentScore"] == 77
    rpc_ops = next(ops for name, ops in client.calls if name == "get_pokemon_card_component_rankings_v1")
    assert rpc_ops[0][1][0]["p_lens"] == lens
    names = [name for name, _ in client.calls]
    assert names.count("pokemon_card_collector_appeal_scores") == (1 if lens == "artist" else 0)
    assert names.count("eras") == 0
