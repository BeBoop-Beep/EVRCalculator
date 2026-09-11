from backend.db.services.market_explorer_prepared_directory import (
    read_prepared_comparison, read_prepared_directory, read_prepared_history,
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
