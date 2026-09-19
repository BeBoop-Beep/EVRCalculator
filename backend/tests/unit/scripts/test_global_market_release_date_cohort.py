from types import SimpleNamespace

from backend.scripts import build_pokemon_explore_set_value_snapshot as builder
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



def test_post_cutover_uses_lightweight_authority_membership_and_direct_metadata(monkeypatch):
    seen_tables = []

    monkeypatch.setattr(
        builder,
        "resolve_market_root_ids",
        lambda _client, *, market_date: ["set-a", "set-b"],
    )

    class PostCutoverClient:
        def table(self, name):
            seen_tables.append(name)
            if name == "sets":
                return Query([
                    {
                        "id": "set-a", "name": "Alpha", "canonical_key": "alpha",
                        "era_id": "era-1", "release_date": "2001-01-01",
                        "logo_image_url": "alpha.png", "symbol_image_url": "alpha-symbol.png",
                        "catalog_only": False, "parent_opening_set_id": None,
                    },
                    {
                        "id": "set-b", "name": "Beta", "canonical_key": "beta",
                        "era_id": "era-1", "release_date": "2002-01-01",
                        "logo_image_url": "beta.png", "symbol_image_url": "beta-symbol.png",
                        "catalog_only": False, "parent_opening_set_id": None,
                    },
                ])
            if name == "eras":
                return Query([{"id": "era-1", "name": "Neo"}])
            raise AssertionError(f"unexpected heavyweight/unknown table read: {name}")

    rows = _load_sets(PostCutoverClient(), market_date="2026-09-18")

    assert [row["id"] for row in rows] == ["set-a", "set-b"]
    assert [row["era"] for row in rows] == ["Neo", "Neo"]
    assert seen_tables == ["sets", "eras"]
    assert all(row["market_scope"] == "standard" for row in rows)
    assert all(row["market_publication_ready"] is True for row in rows)
