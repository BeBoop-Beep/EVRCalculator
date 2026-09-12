from __future__ import annotations

import ast
import inspect
from datetime import date, timedelta

import pytest

from backend.db.services import market_explorer_constituent_movement as movement


class Response:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, client, table):
        self.client = client
        self.table_name = table
        self.start = None
        self.end = None

    def select(self, *_args): return self
    def eq(self, *_args): return self
    def in_(self, *_args): return self
    def gte(self, *_args): return self
    def lte(self, *_args): return self
    def order(self, *_args, **_kwargs): return self

    def range(self, start, end):
        self.start, self.end = start, end
        return self

    def execute(self):
        self.client.executions.append(self.table_name)
        rows = list(self.client.rows.get(self.table_name, []))
        if self.start is not None:
            rows = rows[self.start:self.end + 1]
        return Response(rows)


class Client:
    def __init__(self, rows):
        self.rows = rows
        self.executions: list[str] = []

    def table(self, name):
        return Query(self, name)


def _quality_rows():
    end = date(2026, 9, 6)
    return [
        {"market_date": (end - timedelta(days=offset)).isoformat()}
        for offset in range(100, -1, -1)
    ]


def test_page_movement_uses_bounded_v2_daily_rows_when_baselines_exist():
    client = Client({
        movement.QUALITY_TABLE: _quality_rows(),
        movement.V2_DAILY_TABLE: [
            {"card_variant_id": "a", "market_date": "2026-09-05", "market_price": 100},
            {"card_variant_id": "a", "market_date": "2026-08-30", "market_price": 80},
            {"card_variant_id": "a", "market_date": "2026-08-07", "market_price": 50},
            {"card_variant_id": "a", "market_date": "2026-06-08", "market_price": 40},
            {"card_variant_id": "b", "market_date": "2026-09-05", "market_price": 10},
        ],
        movement.V2_INTERVAL_TABLE: [],
    })
    page = {"as_of": "2026-09-06", "items": [
        {"cardVariantId": "a", "marketPrice": 120},
        {"cardVariantId": "b", "marketPrice": 12},
    ]}

    enriched = movement.enrich_card_constituent_page(client, page)

    assert enriched["items"][0]["changes"] == pytest.approx(
        {"1D": 20, "7D": 50, "30D": 140, "3M": 200}
    )
    assert enriched["items"][1]["changes"]["1D"] == pytest.approx(20)
    assert client.executions.count(movement.V2_DAILY_TABLE) == 1
    assert client.executions.count(movement.V2_INTERVAL_TABLE) == 0


def test_missing_v2_daily_baselines_fall_back_to_v2_intervals_not_v1():
    client = Client({
        movement.QUALITY_TABLE: _quality_rows(),
        movement.V2_DAILY_TABLE: [
            {"card_variant_id": "exact", "market_date": "2026-09-05", "market_price": 9},
        ],
        movement.V2_INTERVAL_TABLE: [
            {
                "card_variant_id": "exact",
                "set_id": "set-a",
                "market_price": 5,
                "valid_from": "2026-04-01",
                "valid_to": "2026-09-01",
            },
        ],
    })

    enriched = movement.enrich_card_constituent_page(client, {
        "as_of": "2026-09-06",
        "items": [{"cardVariantId": "exact", "marketPrice": 10}],
    })

    assert set(enriched["items"][0]["changes"]) == {"1D", "7D", "30D", "3M"}
    assert client.executions.count(movement.V2_DAILY_TABLE) == 1
    assert client.executions.count(movement.V2_INTERVAL_TABLE) == 1


def test_module_contains_no_exact_retired_v1_relation_literals():
    tree = ast.parse(inspect.getsource(movement))
    strings = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "pokemon_market_explorer_card_daily_states" not in strings
    assert "pokemon_card_variant_market_price_intervals" not in strings
