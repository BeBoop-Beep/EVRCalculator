from backend.db.services.market_explorer_prepared_directory import (
    DIRECTORY_CACHE_TTL_SECONDS, _reset_prepared_directory_cache,
    _prepared_window_movements, read_prepared_comparison, read_prepared_comparison_bundle,
    read_prepared_directory, read_prepared_directory_cached, read_prepared_history,
    read_prepared_screen, read_set_context_ranking,
)

class Result:
    def __init__(self, data): self.data = data
class Call:
    def __init__(self, data): self.data = data
    def execute(self): return Result(self.data)
class Client:
    def __init__(self): self.calls = []
    def rpc(self, name, args):
        self.calls.append((name, args))
        return Call({"available": True} if "context" in name else [{"market_key": "set:x"}])

def test_prepared_reads_use_only_bounded_read_rpcs():
    client = Client()
    assert read_prepared_directory(client)[0]["market_key"] == "set:x"
    read_prepared_comparison(client, ["set:x"])
    read_prepared_history(client, ["set:x"], "2026-06-01")
    read_prepared_screen(client, "momentum-leaders", None, 10)
    assert read_set_context_ranking(client, "id", "risers", "30D", 10, "2026-09-08")["available"]
    assert all("query" not in name and "preflight" not in name and "build" not in name for name, _ in client.calls)

def test_comparison_enforces_database_maximum_before_rpc():
    client = Client()
    try: read_prepared_comparison(client, [str(i) for i in range(26)])
    except ValueError: pass
    else: raise AssertionError("expected bound")
    assert client.calls == []

def test_directory_cache_is_bounded_expires_and_serves_stale_on_refresh_error():
    _reset_prepared_directory_cache()
    client = Client()
    assert read_prepared_directory_cached(client, now=10)[0]["market_key"] == "set:x"
    assert read_prepared_directory_cached(client, now=10 + DIRECTORY_CACHE_TTL_SECONDS - 1)[0]["market_key"] == "set:x"
    assert len(client.calls) == 1
    assert read_prepared_directory_cached(client, now=10 + DIRECTORY_CACHE_TTL_SECONDS)[0]["market_key"] == "set:x"
    assert len(client.calls) == 2
    client.rpc = lambda *_args: (_ for _ in ()).throw(RuntimeError("refresh failed"))
    assert read_prepared_directory_cached(client, now=1000)[0]["market_key"] == "set:x"
    _reset_prepared_directory_cache()


def test_prepared_window_movements_publish_long_horizons_and_since_tracking():
    history = [
        {"market_key": "rarity:x", "market_date": "2026-04-11", "index_value": 100},
        {"market_key": "rarity:x", "market_date": "2026-06-23", "index_value": 105},
        {"market_key": "rarity:x", "market_date": "2026-09-21", "index_value": 120},
    ]
    movement = _prepared_window_movements(history)["rarity:x"]
    assert movement["3M"]["available"] is True
    assert movement["6M"]["available"] is True
    assert movement["6M"]["isSinceFirstAvailable"] is True
    assert movement["1Y"]["available"] is True
    assert movement["1Y"]["isSinceFirstAvailable"] is True
    assert movement["SinceTracking"]["available"] is True
    assert movement["SinceTracking"]["startDate"] == "2026-04-11"


class TableQuery:
    def __init__(self, rows):
        self.rows = list(rows)
        self.filters = []
    def select(self, *_args): return self
    def in_(self, field, values):
        self.filters.append(("in", field, set(values)))
        return self
    def eq(self, field, value):
        self.filters.append(("eq", field, value))
        return self
    def execute(self):
        rows = self.rows
        for op, field, value in self.filters:
            if op == "in":
                rows = [row for row in rows if row.get(field) in value]
            else:
                rows = [row for row in rows if row.get(field) == value]
        return Result(rows)


class BundleClient:
    def rpc(self, name, args):
        if name == "get_pokemon_market_explorer_prepared_comparison_v1":
            return Call([{
                "market_key": "rarity:x", "market_type": "prepared_rarity",
                "label": "Rarity X", "metadata": {"queryFingerprint": "fp-x"},
                "comparison_as_of": "2026-09-21",
            }])
        if name == "get_pokemon_market_explorer_prepared_history_v1":
            return Call([
                {"market_key": "rarity:x", "market_date": "2026-04-11", "index_value": 100},
                {"market_key": "rarity:x", "market_date": "2026-09-21", "index_value": 120},
            ])
        raise AssertionError(name)
    def table(self, name):
        if name == "pokemon_market_explorer_query_cache":
            return TableQuery([{"query_fingerprint": "fp-x", "constituent_count": 42}])
        if name == "pokemon_set_market_dashboard_snapshot_latest":
            return TableQuery([])
        raise AssertionError(name)


def test_prepared_comparison_bundle_enriches_server_owned_metrics_and_count():
    result = read_prepared_comparison_bundle(BundleClient(), ["rarity:x"])
    market = result["markets"][0]
    assert market["constituent_count"] == 42
    assert market["window_movements"]["SinceTracking"]["available"] is True
    assert market["window_movements"]["SinceTracking"]["percent"] == 20.0
    assert len(result["history"]) == 2
