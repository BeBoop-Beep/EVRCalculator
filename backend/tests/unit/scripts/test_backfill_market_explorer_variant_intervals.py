from backend.scripts import backfill_market_explorer_variant_intervals as backfill


class Response:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, client, kind, name, params=None):
        self.client = client
        self.kind = kind
        self.name = name
        self.params = params or {}
        self.filters = {}
        self.start = 0
        self.end = 999

    def select(self, *_args, **_kwargs): return self
    def order(self, *_args, **_kwargs): return self
    def in_(self, field, values):
        self.filters[field] = list(values)
        return self
    def range(self, start, end):
        self.start, self.end = start, end
        return self

    def execute(self):
        if self.kind == "rpc":
            requested = list(self.params["p_set_ids"])
            self.client.writes.append(requested)
            rows = sum(self.client.interval_counts.get(set_id, 0) for set_id in requested)
            return Response({"set_count": len(requested), "interval_rows": rows})
        if self.name == backfill.V2_COVERAGE_TABLE:
            rows = [{"set_id": value} for value in self.client.covered]
        elif self.name == backfill.V2_INTERVAL_TABLE:
            requested = self.filters.get("set_id", [])
            rows = [
                {"set_id": set_id, "card_variant_id": f"{set_id}-v{index}", "valid_from": "2026-09-01"}
                for set_id in requested
                for index in range(self.client.interval_counts.get(set_id, 0))
            ]
        elif self.name == backfill.SETS_TABLE:
            rows = [{"id": value, "era_id": "era-a"} for value in self.client.set_ids]
        else:
            raise AssertionError(self.name)
        return Response(rows[self.start:self.end + 1])


class Client:
    def __init__(self):
        self.set_ids = ["set-a", "set-b", "set-c"]
        self.interval_counts = {"set-a": 2, "set-b": 1, "set-c": 3}
        self.covered = {"set-a"}
        self.writes = []

    def rpc(self, name, params):
        assert name == backfill.V2_REBUILD_RPC
        return Query(self, "rpc", name, params)

    def table(self, name):
        return Query(self, "table", name)


def _tracked(_client):
    return ["set-a", "set-b", "set-c"]


def test_dry_run_plans_set_batches_without_writes(monkeypatch):
    monkeypatch.setattr(backfill, "resolve_tracked_set_ids", _tracked)
    client = Client()
    report = backfill.run_backfill(client, commit=False, batch_size=2)
    assert client.writes == []
    assert report["sets_attempted"] == 3
    assert report["sets_succeeded"] == 3
    assert report["batches_succeeded"] == 2
    assert report["interval_rows_created"] == 0


def test_commit_rebuilds_and_exactly_reconciles_v2_interval_rows(monkeypatch):
    monkeypatch.setattr(backfill, "resolve_tracked_set_ids", _tracked)
    client = Client()
    report = backfill.run_backfill(
        client, commit=True, batch_size=2, set_ids=["set-a", "set-b"],
    )
    assert client.writes == [["set-a", "set-b"]]
    assert report["interval_rows_created"] == 3
    assert report["sets_succeeded"] == 2
    assert report["failures"] == 0


def test_resume_cursor_is_set_scoped(monkeypatch):
    monkeypatch.setattr(backfill, "resolve_tracked_set_ids", _tracked)
    client = Client()
    report = backfill.run_backfill(
        client, commit=True, batch_size=1, resume_after="set-a:legacy-variant",
    )
    assert client.writes == [["set-b"], ["set-c"]]
    assert report["resume_cursor"] == "set-c"
    assert backfill.decode_cursor("set-a:legacy-variant") == "set-a"


def test_exclude_covered_uses_v2_coverage(monkeypatch):
    monkeypatch.setattr(backfill, "resolve_tracked_set_ids", _tracked)
    client = Client()
    report = backfill.run_backfill(
        client, commit=False, batch_size=10, exclude_covered=True,
    )
    assert report["sets_attempted"] == 2


def test_failed_batch_does_not_advance_cursor(monkeypatch):
    monkeypatch.setattr(backfill, "resolve_tracked_set_ids", _tracked)
    client = Client()
    original_rpc = client.rpc

    def rpc(name, params):
        query = original_rpc(name, params)
        if "set-b" in params["p_set_ids"]:
            def fail():
                raise RuntimeError("statement timeout")
            query.execute = fail
        return query

    client.rpc = rpc
    report = backfill.run_backfill(client, commit=True, batch_size=1)
    assert client.writes == [["set-a"]]
    assert report["failures"] == 1
    assert report["resume_cursor"] == "set-a"
