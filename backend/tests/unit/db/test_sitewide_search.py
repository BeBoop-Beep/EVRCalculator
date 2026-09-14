from backend.db.services.market_explorer_prepared_directory import _reset_prepared_directory_cache
from backend.db.services.sitewide_search import (
    _prepared_result, _reset_sitewide_result_cache, match_prepared_markets, search_sitewide,
)


class Result:
    def __init__(self, data): self.data = data


class Query:
    def __init__(self, rows): self.rows = rows
    def select(self, *_args): return self
    def in_(self, *_args): return self
    def execute(self): return Result(self.rows)


class Client:
    def __init__(self): self.calls = []
    def rpc(self, name, _params):
        self.calls.append(name)
        if name == "search_pokemon_sitewide_instruments_v1":
            return Query([
                {"asset": "cards", "instrument_id": "v1", "name": "Gastly", "set_id": "sv5",
                 "set_name": "Temporal Forces", "image_url": "https://images.pokemontcg.io/sv5/102.png",
                 "canonical_card_id": "sv5-102"},
                {"asset": "sealed", "instrument_id": "p1", "name": "Elite Trainer Box", "set_name": "Temporal Forces"},
            ])
        return Query([{"market_key": "set:tf", "market_type": "set", "label": "Temporal Forces",
                       "metadata": {"logoUrl": "https://images.pokemontcg.io/sv5/logo.png",
                                    "symbolUrl": "https://images.pokemontcg.io/sv5/symbol.png"}}])
    def table(self, _name): raise AssertionError("sitewide search must not issue a card route table query")


def setup_function():
    _reset_sitewide_result_cache()
    _reset_prepared_directory_cache()


def test_prepared_matching_is_normalized_order_independent_and_typo_tolerant():
    rows = [{"market_key": "set:1", "market_type": "set", "label": "Evolving Skies"},
            {"market_key": "era:1", "market_type": "era", "label": "Scarlet & Violet"}]
    assert match_prepared_markets(rows, "skies evolving")[0]["market_key"] == "set:1"
    assert match_prepared_markets(rows, "evolvng skies")[0]["market_key"] == "set:1"
    assert match_prepared_markets(rows, "scarlet violet")[0]["market_key"] == "era:1"


def test_site_search_composes_prepared_and_canonical_leaf_results():
    client = Client()
    result = search_sitewide(client, q="temporal forces", limit=10)
    assert [item["category"] for item in result["items"]] == ["Sets", "Cards", "Sealed"]
    assert result["items"][0]["href"].startswith("/TCGs/Pokemon/Sets/")
    assert result["items"][0]["imageUrl"].endswith("/logo.png")
    assert result["items"][0]["imageFallbackUrl"].endswith("/symbol.png")
    assert result["items"][1]["imageUrl"].endswith("/102.png")
    assert result["items"][2]["href"] == "/sealed-products/p1"
    assert result["timing"]["cardRouteMs"] == 0
    assert client.calls == ["search_pokemon_sitewide_instruments_v1", "get_pokemon_market_explorer_prepared_directory_v1"]


def test_public_result_cache_normalizes_query_and_preserves_order_without_new_rpcs():
    client = Client()
    first = search_sitewide(client, q="Temporal   Forces", limit=10)
    second = search_sitewide(client, q="temporal forces", limit=10)
    assert [item["id"] for item in second["items"]] == [item["id"] for item in first["items"]]
    assert second["timing"]["cacheHit"] is True
    assert client.calls == ["search_pokemon_sitewide_instruments_v1", "get_pokemon_market_explorer_prepared_directory_v1"]


def test_prepared_images_are_set_only_and_safely_fall_back_to_symbol():
    set_result = _prepared_result({"market_key": "set:1", "market_type": "set", "label": "Set",
                                   "metadata": {"symbolUrl": "https://images.pokemontcg.io/s1/symbol.png"}})
    era_result = _prepared_result({"market_key": "era:1", "market_type": "era", "label": "Era",
                                   "metadata": {"logoUrl": "private"}})
    quick_result = _prepared_result({"market_key": "quick:1", "market_type": "curated", "label": "Quick",
                                     "metadata": {"logoUrl": "private"}})
    assert set_result["imageUrl"] is None
    assert set_result["imageFallbackUrl"].endswith("/symbol.png")
    assert "imageUrl" not in era_result and "imageFallbackUrl" not in era_result
    assert "imageUrl" not in quick_result and "imageFallbackUrl" not in quick_result
