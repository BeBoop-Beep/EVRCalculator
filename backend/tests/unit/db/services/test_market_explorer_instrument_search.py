from types import SimpleNamespace

import pytest

from backend.db.services.market_explorer_instrument_search import (
    SEARCH_RPC,
    search_market_explorer_instruments,
)


class RpcClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.rows))


def test_one_rpc_owns_ranking_and_result_cap_for_all_assets():
    rows = [
        {"asset": "sealed", "instrument_id": "s1", "display_name": "Mega Dragonite ETB", "set_name": "Test"},
        {"asset": "cards", "instrument_id": "c1", "display_name": "Mega Dragonite", "collector_number": "128/100"},
    ]
    client = RpcClient(rows)
    payload = search_market_explorer_instruments(client, q="  dragonite mega  ", asset="all", limit=20)
    assert client.calls == [(SEARCH_RPC, {"p_query": "dragonite mega", "p_asset": "all", "p_limit": 20})]
    assert [item["instrumentId"] for item in payload["items"]] == ["s1", "c1"]
    assert payload["items"][1]["displayName"] == "Mega Dragonite"
    assert payload["items"][1]["cardNumber"] == "128/100"
    assert all("rank" not in item and "score" not in item for item in payload["items"])


def test_card_and_sealed_rows_share_the_canonical_browser_contract():
    client = RpcClient([
        {"asset": "cards", "instrument_id": "c1", "name": "Gastly", "set_id": "set-1",
         "set_name": "Temporal Forces", "image_url": "card.jpg", "card_number": "102",
         "rarity": "Illustration Rare", "edition": "Unlimited", "printing_type": "Holofoil",
         "special_type": "Full Art", "match_kind": "name_set_context", "relevance_score": 76000,
         "name_similarity": 0.75},
        {"asset": "sealed", "instrument_id": "s1", "name": "Elite Trainer Box", "set_id": "set-1",
         "set_name": "Temporal Forces", "image_url": "sealed.jpg", "product_family": "ETB",
         "variant_label": "Pokemon Center", "match_kind": "name_tokens", "relevance_score": 90000,
         "name_similarity": 1.0},
    ])
    items = search_market_explorer_instruments(client, q="temporal forces", asset="all")["items"]
    assert items[0] == {
        "asset": "cards", "instrumentId": "c1", "displayName": "Gastly", "name": "Gastly",
        "label": "Gastly", "setId": "set-1", "setName": "Temporal Forces", "imageUrl": "card.jpg",
        "cardNumber": "102", "rarity": "Illustration Rare", "edition": "Unlimited",
        "printingType": "Holofoil", "specialType": "Full Art",
    }
    assert items[1] == {
        "asset": "sealed", "instrumentId": "s1", "displayName": "Elite Trainer Box",
        "name": "Elite Trainer Box", "label": "Elite Trainer Box", "setId": "set-1",
        "setName": "Temporal Forces", "imageUrl": "sealed.jpg", "productFamily": "ETB",
        "productType": "ETB", "variantLabel": "Pokemon Center",
    }


@pytest.mark.parametrize("asset", ["cards", "sealed"])
def test_asset_contract_is_defended_even_if_rpc_returns_a_bad_row(asset):
    other = "sealed" if asset == "cards" else "cards"
    client = RpcClient([
        {"asset": asset, "instrument_id": "keep", "display_name": "Keep"},
        {"asset": other, "instrument_id": "drop", "display_name": "Drop"},
    ])
    payload = search_market_explorer_instruments(client, q="gastly temporal forces", asset=asset)
    assert [item["instrumentId"] for item in payload["items"]] == ["keep"]


@pytest.mark.parametrize("q", ["", " ", "a"])
def test_short_queries_do_not_reach_the_database(q):
    client = RpcClient([])
    with pytest.raises(ValueError):
        search_market_explorer_instruments(client, q=q)
    assert client.calls == []
