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


class SealedClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return QueryResult(self.rows)


class QueryResult:
    def __init__(self, rows):
        self.rows = rows

    def execute(self):
        return Response(self.rows)


def test_sealed_page_uses_one_rpc_for_100_products_and_maps_identity_and_nulls():
    items = [{"sealedProductId": f"00000000-0000-0000-0000-{i:012d}"} for i in range(100)]
    client = SealedClient([
        {"sealed_product_id": items[1]["sealedProductId"], "as_of": "2026-09-27",
         "movement_1d_pct": -2, "baseline_1d_date": "2026-09-26",
         "movement_7d_pct": 7.5, "baseline_7d_date": "2026-09-21",
         "movement_30d_pct": None, "baseline_30d_date": None,
         "movement_3m_pct": None, "baseline_3m_date": None,
         "movement_6m_pct": None, "baseline_6m_date": None,
         "movement_1y_pct": None, "baseline_1y_date": None,
         "movement_since_tracking_pct": 4, "baseline_since_tracking_date": "2026-01-01"},
        {"sealed_product_id": items[0]["sealedProductId"], "as_of": "2026-09-27",
         "movement_1d_pct": 1, "baseline_1d_date": "2026-09-26",
         "movement_7d_pct": 3, "baseline_7d_date": "2026-09-20",
         "movement_30d_pct": 5, "baseline_30d_date": "2026-08-29",
         "movement_3m_pct": 8, "baseline_3m_date": "2026-06-29",
         "movement_6m_pct": 10, "baseline_6m_date": "2026-03-31",
         "movement_1y_pct": None, "baseline_1y_date": None,
         "movement_since_tracking_pct": 12, "baseline_since_tracking_date": "2025-11-01"},
    ])
    result = movement.enrich_sealed_constituent_page(
        client, {"as_of": "2026-09-27", "items": items})
    assert len(client.calls) == 1
    assert client.calls[0] == (movement.SEALED_MOVEMENT_RPC, {
        "p_sealed_product_ids": [item["sealedProductId"] for item in items],
        "p_as_of": "2026-09-27",
    })
    assert result["items"][0]["changes"] == {
        "1D": 1.0, "7D": 3.0, "30D": 5.0, "3M": 8.0,
        "6M": 10.0, "1Y": None, "SinceTracking": 12.0,
    }
    assert result["items"][1]["changes"]["30D"] is None
    assert result["items"][1]["changes"]["3M"] is None
    assert result["items"][1]["changeBaselines"]["7D"] == "2026-09-21"
    assert result["items"][99]["changes"] == {
        "1D": None, "7D": None, "30D": None, "3M": None,
        "6M": None, "1Y": None, "SinceTracking": None,
    }


def test_sealed_movement_preserves_civil_date_and_declines_invalid_or_oversized_pages():
    client = SealedClient([])
    movement.enrich_sealed_constituent_page(
        client, {"as_of": "2026-09-27T23:59:59-07:00", "items": [{"sealedProductId": "p"}]})
    assert client.calls[0][1]["p_as_of"] == "2026-09-27"
    assert movement.enrich_sealed_constituent_page(
        SealedClient([]), {"as_of": "bad", "items": [{"sealedProductId": "p"}]})["items"]
    with pytest.raises(ValueError, match="1..100"):
        movement.enrich_sealed_constituent_page(
            SealedClient([]), {"as_of": "2026-09-27", "items": [
                {"sealedProductId": str(i)} for i in range(101)
            ]})
