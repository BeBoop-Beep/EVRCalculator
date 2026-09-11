from backend.db.services.sitewide_search import match_prepared_markets, search_sitewide


class Result:
    def __init__(self, data): self.data = data


class Query:
    def __init__(self, rows): self.rows = rows
    def select(self, *_args): return self
    def in_(self, *_args): return self
    def execute(self): return Result(self.rows)


class Client:
    def rpc(self, name, _params):
        if name == "search_pokemon_market_explorer_instruments_v2":
            return Query([{"asset": "sealed", "instrument_id": "p1", "name": "Elite Trainer Box", "set_name": "Temporal Forces"}])
        return Query([{"market_key": "set:tf", "market_type": "set", "label": "Temporal Forces"}])
    def table(self, _name): return Query([])


def test_prepared_matching_is_normalized_order_independent_and_typo_tolerant():
    rows = [{"market_key": "set:1", "market_type": "set", "label": "Evolving Skies"},
            {"market_key": "era:1", "market_type": "era", "label": "Scarlet & Violet"}]
    assert match_prepared_markets(rows, "skies evolving")[0]["market_key"] == "set:1"
    assert match_prepared_markets(rows, "evolvng skies")[0]["market_key"] == "set:1"
    assert match_prepared_markets(rows, "scarlet violet")[0]["market_key"] == "era:1"


def test_site_search_composes_prepared_and_canonical_leaf_results():
    result = search_sitewide(Client(), q="temporal forces", limit=10)
    assert [item["category"] for item in result["items"]] == ["Sets", "Sealed"]
    assert result["items"][0]["href"].startswith("/TCGs/Pokemon/Sets/")
    assert result["items"][1]["href"] == "/sealed-products/p1"
