from types import SimpleNamespace

import pytest

from backend.db.services.market_explorer_instrument_search import (
    GRADED_UNAVAILABLE_REASON, LEAF_SEARCH_RPC, LEGACY_SEARCH_RPC,
    search_market_explorer_instruments, search_market_explorer_leaves,
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
    assert client.calls == [(LEGACY_SEARCH_RPC, {"p_query": "dragonite mega", "p_asset": "all", "p_limit": 20})]
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
        "productType": "ETB", "variantLabel": "Pokemon Center", "sealedProductId": "s1",
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


def test_leaf_shape_preserves_price_freshness_and_optional_asset_metadata_without_reranking():
    rows = [
        {"asset": "cards", "instrument_id": "dragonite", "display_name": "Dragonite",
         "canonical_card_id": "card-1", "set_id": "fossil", "set_name": "Fossil",
         "market_price": 42.5, "market_date": "2026-09-25", "variant_label": "1st Edition"},
        {"asset": "sealed", "instrument_id": "case-1", "sealed_product_id": "case-1",
         "display_name": "Ascended Heroes Case", "product_family": "Case",
         "product_type": "Case", "is_bulk_container": True, "market_price": 999.0,
         "market_date": "2026-09-24"},
    ]
    card = search_market_explorer_leaves(RpcClient(rows[:1]), q="Dragonite", asset="cards", limit=10)
    assert card["items"][0]["displayName"] == "Dragonite"
    assert card["items"][0]["marketPrice"] == 42.5
    assert card["items"][0]["marketDate"] == "2026-09-25"
    assert card["items"][0]["canonicalCardId"] == "card-1"
    assert card["items"][0]["variantLabel"] == "1st Edition"
    sealed = search_market_explorer_leaves(RpcClient(rows[1:]), q="Ascended Heroes", asset="sealed")
    assert sealed["items"][0]["sealedProductId"] == "case-1"
    assert sealed["items"][0]["bulkContainer"] is True


def test_leaf_and_legacy_search_use_distinct_rpcs_with_their_exact_argument_contracts():
    legacy = RpcClient([])
    search_market_explorer_instruments(legacy, q="Dragonite", asset="cards", limit=7)
    assert legacy.calls == [(LEGACY_SEARCH_RPC, {
        "p_query": "Dragonite", "p_asset": "cards", "p_limit": 7,
    })]
    leaf = RpcClient([])
    search_market_explorer_leaves(leaf, q="Dragonite", asset="cards", limit=7)
    assert leaf.calls == [(LEAF_SEARCH_RPC, {
        "p_asset": "cards", "p_query": "Dragonite", "p_limit": 7,
    })]


def test_graded_leaf_search_is_a_stable_truthful_contract_and_never_calls_db():
    client = RpcClient([])
    payload = search_market_explorer_leaves(client, q="PSA 10", asset="graded", limit=25)
    assert payload == {
        "query": "PSA 10", "asset": "graded", "limit": 25, "items": [],
        "availability": "INSUFFICIENT_AUTHORITY", "reason": GRADED_UNAVAILABLE_REASON,
    }
    assert client.calls == []


@pytest.mark.parametrize("query,asset", [
    ("Dragonite", "cards"), ("Charizard", "cards"), ("3 pack", "sealed"),
    ("Ascended Heroes", "sealed"), ("Case", "sealed"),
])
def test_leaf_search_matrix_returns_only_physical_leaf_rows(query, asset):
    rows = [{"asset": asset, "instrument_id": f"{asset}-1", "display_name": query}]
    payload = search_market_explorer_leaves(RpcClient(rows), q=query, asset=asset)
    assert [item["asset"] for item in payload["items"]] == [asset]
    assert all("marketKey" not in item and "result_kind" not in item for item in payload["items"])
