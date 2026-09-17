"""Runtime resilience regressions for the market publication audit."""

from __future__ import annotations

from postgrest.exceptions import APIError

from backend.scripts import audit_pokemon_market_publication as audit


DATE = "2026-09-15"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.columns = ""
        self.ids = []
        self.filters = {}

    def select(self, columns):
        self.columns = columns
        return self

    def in_(self, _column, values):
        self.ids = list(values)
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def execute(self):
        self.client.selects.append((self.table, self.columns, tuple(self.ids)))
        return _Result(self.client.execute(self.table, self.columns, self.ids, self.filters))


class _Client:
    def __init__(self, handler):
        self.handler = handler
        self.selects = []

    def table(self, table):
        return _Query(self, table)

    def execute(self, table, columns, ids, filters):
        return self.handler(table, columns, ids, filters)


def test_cards_snapshot_market_date_accepts_compact_payload_meta_projection():
    assert audit.cards_snapshot_market_date({
        "set_id": "set-1",
        "payload_meta": {"pricingContract": {"latestMarketDate": DATE}},
    }) == DATE


def test_card_loader_uses_compact_meta_without_fetching_cards_json():
    def handler(table, columns, ids, _filters):
        assert table == "pokemon_set_cards_snapshot_latest"
        assert ids == ["set-1"]
        if "payload_meta:payload_json->meta" in columns:
            return [{
                "set_id": "set-1",
                "payload_meta": {"pricingContract": {"latestMarketDate": DATE}},
                "card_count": 1,
            }]
        raise AssertionError(f"unexpected fallback read: {columns}")

    client = _Client(handler)
    rows = audit._load_card_rows(client, ["set-1"])

    assert audit.cards_snapshot_market_date(rows["set-1"]) == DATE
    assert len(client.selects) == 1
    assert "cards_json" not in client.selects[0][1]


def test_card_loader_fetches_heavy_fallback_only_for_missing_meta_date():
    def handler(table, columns, ids, _filters):
        assert table == "pokemon_set_cards_snapshot_latest"
        assert ids == ["set-1"]
        if "payload_meta:payload_json->meta" in columns:
            return [{"set_id": "set-1", "payload_meta": {}, "card_count": 1}]
        if "cards_json" in columns:
            return [{
                "set_id": "set-1",
                "payload_json": {"meta": {}},
                "cards_json": [{"id": "c1", "priceUpdatedAt": DATE}],
                "card_count": 1,
            }]
        raise AssertionError(columns)

    client = _Client(handler)
    rows = audit._load_card_rows(client, ["set-1"])

    assert audit.cards_snapshot_market_date(rows["set-1"]) == DATE
    assert len(client.selects) == 2
    assert "cards_json" not in client.selects[0][1]
    assert "cards_json" in client.selects[1][1]


def test_chunk_read_retries_transient_521_with_fresh_client_factory():
    def fail_521(_table, _columns, _ids, _filters):
        raise APIError({
            "message": "JSON could not be generated",
            "code": 521,
            "hint": "Refer to full message for details",
            "details": "<html><title>521: Web server is down</title></html>",
        })

    first = _Client(fail_521)
    second = _Client(lambda _table, _columns, ids, _filters: [
        {"set_id": sid, "market_date": DATE} for sid in ids
    ])
    clients = iter((first, second))

    rows = audit._load_rows(
        first,
        "pokemon_set_sealed_market_snapshot_latest",
        "set_id,market_date",
        ["set-1"],
        chunk_size=10,
        client_factory=lambda: next(clients),
    )

    assert rows["set-1"]["market_date"] == DATE
    assert len(first.selects) == 1
    assert len(second.selects) == 1
