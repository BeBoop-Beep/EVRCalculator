from __future__ import annotations

import re

import pytest

from backend.db.services import pokemon_sets_catalog_service as svc


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTableQuery:
    def __init__(self, table_name, rows):
        self._table_name = table_name
        self._rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def ilike(self, *_args, **_kwargs):
        return self

    def in_(self, _column, values):
        wanted = set(values)
        self._rows = [row for row in self._rows if row.get("id") in wanted]
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        return FakeResult(list(self._rows))


class FakeClient:
    """Fake Supabase-like client that records RPC calls and forbids paging
    through pokemon_canonical_cards row-by-row.
    """

    def __init__(self, tcgs, sets_rows, canonical_counts_by_set):
        self._tcgs = tcgs
        self._sets_rows = sets_rows
        self._canonical_counts_by_set = canonical_counts_by_set
        self.rpc_calls = []
        self.canonical_cards_table_queries = 0

    def table(self, name):
        if name == "tcgs":
            return FakeTableQuery(name, self._tcgs)
        if name == "sets":
            return FakeTableQuery(name, self._sets_rows)
        if name == "eras":
            return FakeTableQuery(name, [])
        if name == "pokemon_canonical_cards":
            self.canonical_cards_table_queries += 1
            raise AssertionError(
                "pokemon_canonical_cards must not be queried row-by-row; "
                "use the get_pokemon_canonical_card_counts_by_set RPC instead"
            )
        raise AssertionError(f"unexpected table: {name}")

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        if name == "get_pokemon_canonical_card_counts_by_set":
            requested = set(params["p_set_ids"])
            rows = [
                {"set_id": set_id, "card_count": count}
                for set_id, count in self._canonical_counts_by_set.items()
                if set_id in requested
            ]
            return FakeRpcBuilder(rows)
        raise AssertionError(f"unexpected rpc: {name}")


class FakeRpcBuilder:
    def __init__(self, rows):
        self._rows = rows

    def execute(self):
        return FakeResult(self._rows)


def _install_fake_client(monkeypatch, client):
    monkeypatch.setattr(svc, "service_read_client", client)
    monkeypatch.setattr(
        svc,
        "run_public_read_with_retry",
        lambda fn, **_kwargs: fn(client),
    )


def _base_sets_rows():
    return [
        {"id": "set-1", "name": "Alpha Set", "tcg_id": "pkmn", "era_id": None, "release_date": "2024-01-01"},
        {"id": "set-2", "name": "Beta Set", "tcg_id": "pkmn", "era_id": None, "release_date": "2023-01-01"},
        {"id": "set-3", "name": "Zero Card Set", "tcg_id": "pkmn", "era_id": None, "release_date": "2022-01-01"},
    ]


def test_card_counts_come_from_aggregate_rpc_not_full_corpus_scan(monkeypatch):
    client = FakeClient(
        tcgs=[{"id": "pkmn", "name": "Pokemon"}],
        sets_rows=_base_sets_rows(),
        canonical_counts_by_set={"set-1": 250, "set-2": 1500},
    )
    _install_fake_client(monkeypatch, client)

    payload = svc.get_pokemon_sets_catalog_payload()

    by_id = {row["id"]: row for row in payload["sets"]}
    assert by_id["set-1"]["card_count"] == 250
    # A set with >1000 canonical cards must not require app-side paging.
    assert by_id["set-2"]["card_count"] == 1500
    # A set with zero canonical cards returns 0, not null/missing.
    assert by_id["set-3"]["card_count"] == 0

    # Exactly one RPC round trip for counts (single batch), never a
    # pokemon_canonical_cards table scan.
    count_calls = [c for c in client.rpc_calls if c[0] == "get_pokemon_canonical_card_counts_by_set"]
    assert len(count_calls) == 1
    assert client.canonical_cards_table_queries == 0


def test_catalog_ordering_and_metadata_preserved(monkeypatch):
    client = FakeClient(
        tcgs=[{"id": "pkmn", "name": "Pokemon"}],
        sets_rows=_base_sets_rows(),
        canonical_counts_by_set={},
    )
    _install_fake_client(monkeypatch, client)

    payload = svc.get_pokemon_sets_catalog_payload()
    ids_in_order = [row["id"] for row in payload["sets"]]
    assert ids_in_order == ["set-1", "set-2", "set-3"]
    assert payload["meta"]["sources"]["pokemon_canonical_cards"] == "OK"


def test_no_pagination_helper_reintroduced():
    """Guard against reintroducing app-side .range() paging over the full
    canonical card corpus to compute counts."""
    source = svc.__file__
    with open(source, "r", encoding="utf-8") as fh:
        text = fh.read()
    # The service must not select bare set_id rows off pokemon_canonical_cards
    # and page through them with .range(); counts must come from the SQL
    # aggregate RPC.
    assert not re.search(r'table\("pokemon_canonical_cards"\)', text)
    assert "get_pokemon_canonical_card_counts_by_set" in text
