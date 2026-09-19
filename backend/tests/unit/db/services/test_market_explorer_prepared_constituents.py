from backend.db.services.market_explorer_prepared_directory import read_prepared_constituents


class _Result:
    data = {"availability": "available", "marketKey": "set:151", "totalCount": 207}


class _RPC:
    def execute(self):
        return _Result()


class _Client:
    def __init__(self):
        self.name = None
        self.params = None

    def rpc(self, name, params):
        self.name, self.params = name, params
        return _RPC()


def test_prepared_page_uses_generation_pinned_rpc():
    client = _Client()
    result = read_prepared_constituents(client, "set:151", "generation-a", 100, 50)
    assert result["totalCount"] == 207
    assert client.name == "get_pokemon_market_explorer_prepared_constituents_v2"
    assert client.params == {
        "p_market_key": "set:151", "p_generation_id": "generation-a",
        "p_after_rank": 100, "p_limit": 50,
    }


def test_prepared_page_rejects_unbounded_requests_before_rpc():
    for cursor, limit in [(-1, 10), (0, 0), (0, 101)]:
        try:
            read_prepared_constituents(_Client(), "set:151", "generation-a", cursor, limit)
        except ValueError:
            pass
        else:
            raise AssertionError("request should be rejected")
