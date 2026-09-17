"""Runtime resilience regressions for the market publication audit."""

from __future__ import annotations

from postgrest.exceptions import APIError

from backend.scripts import audit_pokemon_market_publication as core
from backend.scripts import audit_pokemon_market_publication_resilient as runtime


DATE = "2026-09-15"


def test_compact_card_loader_avoids_heavy_json_when_meta_has_market_date(monkeypatch):
    calls = []

    def fake_load_rows(client, table, columns, set_ids, *, chunk_size=200, **filters):
        calls.append((table, columns, list(set_ids), chunk_size, filters))
        assert table == "pokemon_set_cards_snapshot_latest"
        if columns == runtime._CARDS_META_COLUMNS:
            return {
                "set-1": {
                    "set_id": "set-1",
                    "payload_meta": {"pricingContract": {"latestMarketDate": DATE}},
                    "card_count": 1,
                }
            }
        raise AssertionError(f"unexpected heavy fallback read: {columns}")

    monkeypatch.setattr(runtime, "_ORIGINAL_LOAD_ROWS", fake_load_rows)
    rows = runtime._runtime_load_rows(
        object(),
        "pokemon_set_cards_snapshot_latest",
        runtime._CARDS_HEAVY_COLUMNS,
        ["set-1"],
        chunk_size=20,
    )

    assert core.cards_snapshot_market_date(rows["set-1"]) == DATE
    assert len(calls) == 1
    assert calls[0][1] == runtime._CARDS_META_COLUMNS


def test_compact_card_loader_fetches_heavy_json_only_for_missing_meta_date(monkeypatch):
    calls = []

    def fake_load_rows(client, table, columns, set_ids, *, chunk_size=200, **filters):
        calls.append((columns, list(set_ids), chunk_size))
        assert table == "pokemon_set_cards_snapshot_latest"
        if columns == runtime._CARDS_META_COLUMNS:
            return {"set-1": {"set_id": "set-1", "payload_meta": {}, "card_count": 1}}
        if columns == runtime._CARDS_HEAVY_COLUMNS:
            return {
                "set-1": {
                    "set_id": "set-1",
                    "payload_json": {"meta": {}},
                    "cards_json": [{"id": "c1", "priceUpdatedAt": DATE}],
                    "card_count": 1,
                }
            }
        raise AssertionError(columns)

    monkeypatch.setattr(runtime, "_ORIGINAL_LOAD_ROWS", fake_load_rows)
    rows = runtime._runtime_load_rows(
        object(),
        "pokemon_set_cards_snapshot_latest",
        runtime._CARDS_HEAVY_COLUMNS,
        ["set-1"],
        chunk_size=20,
    )

    assert core.cards_snapshot_market_date(rows["set-1"]) == DATE
    assert calls == [
        (runtime._CARDS_META_COLUMNS, ["set-1"], 20),
        (runtime._CARDS_HEAVY_COLUMNS, ["set-1"], 1),
    ]


class _Result:
    def __init__(self, data):
        self.data = data


class _ServiceQuery:
    def __init__(self, outcome):
        self.outcome = outcome

    @property
    def not_(self):
        return self

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def gte(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def is_(self, *_args, **_kwargs):
        return self

    def execute(self):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return _Result(self.outcome)


class _ServiceClient:
    def __init__(self, outcome):
        self.outcome = outcome
        self.tables = []

    def table(self, name):
        self.tables.append(name)
        return _ServiceQuery(self.outcome)


def test_retrying_query_retries_transient_521_with_fresh_clients(monkeypatch):
    first = _ServiceClient(APIError({
        "message": "JSON could not be generated",
        "code": 521,
        "hint": "Refer to full message for details",
        "details": "<html><title>521: Web server is down</title></html>",
    }))
    second = _ServiceClient([{"set_id": "set-1", "market_date": DATE}])
    clients = iter((first, second))

    monkeypatch.setattr(runtime, "create_service_role_client", lambda: next(clients))

    result = (
        runtime.RetryingServiceRoleClient()
        .table("pokemon_set_sealed_market_snapshot_latest")
        .select("set_id,market_date")
        .in_("set_id", ["set-1"])
        .execute()
    )

    assert result.data == [{"set_id": "set-1", "market_date": DATE}]
    assert first.tables == ["pokemon_set_sealed_market_snapshot_latest"]
    assert second.tables == ["pokemon_set_sealed_market_snapshot_latest"]


def test_non_cards_loads_keep_canonical_loader_contract(monkeypatch):
    called = {}

    def fake_load_rows(client, table, columns, set_ids, *, chunk_size=200, **filters):
        called.update({
            "client": client,
            "table": table,
            "columns": columns,
            "set_ids": list(set_ids),
            "chunk_size": chunk_size,
            "filters": filters,
        })
        return {"set-1": {"set_id": "set-1"}}

    monkeypatch.setattr(runtime, "_ORIGINAL_LOAD_ROWS", fake_load_rows)
    marker = object()
    rows = runtime._runtime_load_rows(
        marker,
        "pokemon_set_page_snapshot_latest",
        "set_id,updated_at",
        ["set-1"],
        chunk_size=7,
        scope="x",
    )

    assert rows == {"set-1": {"set_id": "set-1"}}
    assert called == {
        "client": marker,
        "table": "pokemon_set_page_snapshot_latest",
        "columns": "set_id,updated_at",
        "set_ids": ["set-1"],
        "chunk_size": 7,
        "filters": {"scope": "x"},
    }
