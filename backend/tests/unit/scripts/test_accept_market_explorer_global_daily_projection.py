from backend.scripts.accept_market_explorer_global_daily_projection import run_acceptance


class Response:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, client, name):
        self.client = client
        self.name = name
        self.filters = {}

    def select(self, *_a, **_k):
        return self

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def in_(self, field, values):
        self.filters[field] = list(values)
        return self

    def range(self, start, end):
        self.start, self.end = start, end
        return self

    def execute(self):
        if self.name == "pokemon_set_value_daily_history_coverage":
            rows = [{"set_id": s, "has_history": True} for s in self.client.tracked_sets]
            start = getattr(self, "start", 0) or 0
            end = getattr(self, "end", len(rows) - 1)
            return Response(rows[start:end + 1])
        if self.name == "pokemon_market_explorer_card_daily_coverage":
            requested = self.filters.get("set_id", [])
            rows = [dict(self.client.coverage[s]) for s in requested if s in self.client.coverage]
            return Response(rows)
        raise AssertionError(f"unexpected table {self.name}")


class Client:
    def __init__(self):
        self.tracked_sets = ["set-a", "set-b"]
        self.coverage = {
            "set-a": {"set_id": "set-a", "first_market_date": "2026-04-07", "computed_through": "2026-04-09"},
            "set-b": {"set_id": "set-b", "first_market_date": "2026-04-07", "computed_through": "2026-04-09"},
        }
        # Both RPCs return identical rows for every request in this test --
        # the point here is exercising scope/coverage wiring, not the RPC
        # comparison itself (already covered by the existing ten-set script).
        self.rpc_calls = []

    def table(self, name):
        return Query(self, name)

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return _RpcCall([{"market_date": params["p_start_date"], "value": 1}])


class _RpcCall:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return Response(self._data)


def test_global_scope_reports_full_coverage_and_exact_parity():
    client = Client()
    report = run_acceptance(client, start_date="2026-04-07", end_date="2026-04-09", perf_samples=1)
    assert report["plannerPathCoverage"]["global"] is True
    assert report["expectedPath"]["global"] == "projection"
    assert report["allExact"] is True
    assert "global.allRaw" in report["correctness"]
    assert "global.top10" in report["correctness"]
    assert "global.rareHolo" in report["correctness"]
    assert "global.premium" in report["correctness"]


def test_uncovered_scope_reports_interval_fallback_expected():
    client = Client()
    client.coverage["set-b"]["computed_through"] = "2026-04-08"  # short of end_date
    report = run_acceptance(client, start_date="2026-04-07", end_date="2026-04-09", perf_samples=1)
    assert report["plannerPathCoverage"]["global"] is False
    assert report["expectedPath"]["global"] == "interval_fallback"


def test_era_representative_scopes_are_included():
    client = Client()
    report = run_acceptance(
        client, start_date="2026-04-07", end_date="2026-04-09",
        era_representatives={"era-1": "set-a"}, perf_samples=1,
    )
    assert "era:era-1" in report["plannerPathCoverage"]
    assert "era:era-1.allRaw" in report["correctness"]
    assert "era:era-1.top10" in report["correctness"]
