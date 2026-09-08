from datetime import date, timedelta

import pytest

from backend.db.services.market_explorer_constituent_movement import (
    QUALITY_TABLE, V1_TABLE, V2_TABLE, enrich_card_constituent_page,
)


class Response:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, client, table):
        self.client, self.table_name = client, table

    def select(self, *_args): return self
    def eq(self, *_args): return self
    def in_(self, *_args): return self
    def gte(self, *_args): return self
    def lte(self, *_args): return self
    def order(self, *_args, **_kwargs): return self

    def execute(self):
        self.client.executions.append(self.table_name)
        return Response(self.client.rows[self.table_name])


class Client:
    def __init__(self, rows):
        self.rows, self.executions = rows, []

    def table(self, name):
        return Query(self, name)


def test_page_movement_batches_physical_ids_and_returns_all_windows():
    end = date(2026, 9, 6)
    quality = [{"market_date": (end - timedelta(days=offset)).isoformat()} for offset in range(100, -1, -1)]
    client = Client({
        QUALITY_TABLE: quality,
        V2_TABLE: [
            {"card_variant_id": "a", "market_date": "2026-09-05", "market_price": 100},
            {"card_variant_id": "a", "market_date": "2026-08-30", "market_price": 80},
            {"card_variant_id": "a", "market_date": "2026-08-07", "market_price": 50},
            {"card_variant_id": "a", "market_date": "2026-06-08", "market_price": 40},
            {"card_variant_id": "b", "market_date": "2026-09-05", "market_price": 10},
        ],
        V1_TABLE: [],
    })
    page = {"as_of": "2026-09-06", "items": [
        {"cardVariantId": "a", "marketPrice": 120},
        {"cardVariantId": "b", "marketPrice": 12},
    ]}

    enriched = enrich_card_constituent_page(client, page)

    assert enriched["items"][0]["changes"] == pytest.approx({"1D": 20, "7D": 50, "30D": 140, "3M": 200})
    assert enriched["items"][1]["changes"]["1D"] == pytest.approx(20)
    assert enriched["items"][1]["changes"]["7D"] is None
    assert client.executions.count(V2_TABLE) == 1
    assert client.executions.count(V1_TABLE) == 0


def test_missing_v2_baseline_falls_back_to_one_batched_v1_read():
    end = date(2026, 9, 6)
    quality = [{"market_date": (end - timedelta(days=offset)).isoformat()} for offset in range(100, -1, -1)]
    client = Client({
        QUALITY_TABLE: quality,
        V2_TABLE: [{"card_variant_id": "exact", "market_date": "2026-09-05", "market_price": 9}],
        V1_TABLE: [{"card_variant_id": "exact", "market_date": value, "market_price": 5}
                   for value in ("2026-08-30", "2026-08-07", "2026-06-08")],
    })
    enriched = enrich_card_constituent_page(client, {"as_of": "2026-09-06", "items": [
        {"cardVariantId": "exact", "marketPrice": 10},
    ]})
    assert set(enriched["items"][0]["changes"]) == {"1D", "7D", "30D", "3M"}
    assert client.executions.count(V2_TABLE) == 1
    assert client.executions.count(V1_TABLE) == 1
