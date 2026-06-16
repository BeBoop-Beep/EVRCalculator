from types import SimpleNamespace

from backend.desirability.pokeapi import build_reference_row, build_reference_upsert_payload
from backend.desirability.repository import PokemonDesirabilityRepository


class FakeSupabase:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        table = self.tables.setdefault(name, FakeTable())
        return table


class FakeTable:
    def __init__(self):
        self.rows_by_pokedex = {}
        self.pending = []

    def upsert(self, rows, on_conflict):
        assert on_conflict == "pokedex_number"
        self.pending = rows
        return self

    def execute(self):
        for row in self.pending:
            self.rows_by_pokedex[row["pokedex_number"]] = dict(row)
        return SimpleNamespace(data=list(self.rows_by_pokedex.values()))


def test_build_reference_row_maps_pokeapi_detail_payload():
    detail = {
        "id": 25,
        "name": "pikachu",
        "sprites": {
            "front_default": "front.png",
            "other": {"official-artwork": {"front_default": "official.png"}},
        },
    }

    row = build_reference_row(detail)

    assert row["pokedex_number"] == 25
    assert row["canonical_name"] == "pikachu"
    assert row["display_name"] == "Pikachu"
    assert row["generation"] == 1
    assert row["sprite_url"] == "official.png"
    assert row["api_url"].endswith("/pokemon/25/")


def test_reference_upsert_payload_dedupes_by_pokedex_number():
    rows = [
        {"pokedex_number": 1, "canonical_name": "bulbasaur", "display_name": "Bulbasaur"},
        {"pokedex_number": 1, "canonical_name": "bulbasaur", "display_name": "Bulbasaur Updated"},
        {"pokedex_number": 4, "canonical_name": "charmander", "display_name": "Charmander"},
    ]

    payload = build_reference_upsert_payload(rows)

    assert len(payload) == 2
    assert payload[0]["display_name"] == "Bulbasaur Updated"
    assert payload[1]["pokedex_number"] == 4


def test_repository_upsert_is_idempotent_for_canonical_references():
    fake_client = FakeSupabase()
    repository = PokemonDesirabilityRepository(client=fake_client)
    rows = [
        {"pokedex_number": 1, "canonical_name": "bulbasaur", "display_name": "Bulbasaur"},
        {"pokedex_number": 4, "canonical_name": "charmander", "display_name": "Charmander"},
    ]

    first = repository.upsert_pokemon_references(rows)
    second = repository.upsert_pokemon_references(rows)

    assert len(first) == 2
    assert len(second) == 2
    assert len(fake_client.tables["pokemon_reference"].rows_by_pokedex) == 2

