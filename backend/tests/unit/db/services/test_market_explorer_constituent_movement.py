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

    assert enriched["items"][0]["changes"] == pytest.approx({
        "1D": 20, "7D": 50, "30D": 140, "3M": 200,
        "6M": None, "1Y": None, "SinceTracking": 200,
    })
    assert enriched["items"][1]["changes"]["1D"] == pytest.approx(20)
    assert client.executions.count(movement.V2_DAILY_TABLE) == 1
    # Long-window baselines may be outside daily retention and therefore use
    # the existing interval authority without inventing another history path.
    assert client.executions.count(movement.V2_INTERVAL_TABLE) == 1


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

    assert set(enriched["items"][0]["changes"]) == {
        "1D", "7D", "30D", "3M", "6M", "1Y", "SinceTracking",
    }
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



class ScopedClient:
    def __init__(self, history_dates, scoped_prices):
        self.rows = {
            movement.SCOPED_ROOT_HISTORY_TABLE: [
                {"market_date": value, "set_id": "set-vintage", "market_scope": "unlimited", "certified_on_date": True}
                for value in history_dates
            ],
        }
        self.executions = []
        self.scoped_prices = scoped_prices
        self.rpc_calls = []

    def table(self, name):
        return Query(self, name)

    def rpc(self, name, args):
        assert name == movement.SCOPED_CONSTITUENT_RPC
        self.rpc_calls.append(dict(args))
        market_date = args["p_market_date"]
        return _RpcResult(self.scoped_prices.get(market_date, []))


class _RpcResult:
    def __init__(self, rows):
        self._rows = rows

    def execute(self):
        return Response(list(self._rows))


def test_scoped_page_movement_never_crosses_edition_and_keys_by_canonical_card():
    dates = [
        (date(2026, 9, 22) - timedelta(days=offset)).isoformat()
        for offset in range(400, -1, -1)
    ]
    scoped = {
        "2026-09-21": [
            {
                "canonical_card_id": "snorlax",
                "card_variant_id": "unlimited-old-variant",
                "market_price": 100,
            }
        ],
        "2026-09-15": [
            {
                "canonical_card_id": "snorlax",
                "card_variant_id": "unlimited-week-variant",
                "market_price": 80,
            }
        ],
    }
    client = ScopedClient(dates, scoped)
    page = {
        "as_of": "2026-09-22",
        "items": [{
            "setId": "set-vintage",
            "marketScope": "unlimited",
            "canonicalCardId": "snorlax",
            # The current preferred Unlimited physical id may differ from the
            # earlier one; the scoped market identity remains Snorlax+Unlimited.
            "cardVariantId": "unlimited-current-variant",
            "marketPrice": 120,
        }],
    }

    enriched = movement.enrich_scoped_card_constituent_page(client, page)

    assert enriched["items"][0]["changes"]["1D"] == pytest.approx(20)
    assert enriched["items"][0]["changes"]["7D"] == pytest.approx(50)
    assert client.rpc_calls
    assert {call["p_market_scope"] for call in client.rpc_calls} == {"unlimited"}
    assert {tuple(call["p_card_ids"]) for call in client.rpc_calls} == {("snorlax",)}
    assert all("first" not in str(call).lower() for call in client.rpc_calls)
