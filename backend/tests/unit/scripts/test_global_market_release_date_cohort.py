from types import SimpleNamespace

from backend.scripts.build_pokemon_explore_set_value_snapshot import _load_sets


class Query:
    def __init__(self, rows): self.rows = rows
    def select(self, *_a): return self
    def in_(self, *_a): return self
    def execute(self): return SimpleNamespace(data=self.rows)


class Client:
    def __init__(self):
        self.sets = [{"id": "current", "canonical_key": "current", "name": "Current", "era_id": "era",
                      "release_date": "2026-08-17", "supports_opening_simulation": True},
                     {"id": "future", "canonical_key": "future", "name": "Future", "era_id": "era",
                      "release_date": "2026-08-18", "supports_opening_simulation": True},
                     {"id": "unknown", "canonical_key": "unknown", "name": "Unknown", "era_id": "era",
                      "release_date": None, "supports_opening_simulation": True}]
    def table(self, name):
        return Query(self.sets if name == "sets" else [{"id": "era", "name": "Scarlet & Violet"}])


def test_future_supported_public_set_enters_only_on_release_date():
    today = {row["id"] for row in _load_sets(Client(), market_date="2026-08-17")}
    release_day = {row["id"] for row in _load_sets(Client(), market_date="2026-08-18")}
    assert today == {"current", "unknown"}
    assert release_day == {"current", "future", "unknown"}
