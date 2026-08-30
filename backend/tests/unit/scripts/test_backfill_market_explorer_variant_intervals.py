from backend.scripts.backfill_market_explorer_variant_intervals import (
    decode_cursor,
    run_backfill,
)


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

    def select(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def in_(self, field, values):
        self.filters[field] = list(values)
        return self

    def range(self, start, end):
        self.start, self.end = start, end
        return self

    def execute(self):
        if self.kind == "rpc" and self.name == "get_pokemon_canonical_card_variant_authority":
            set_id = self.params["p_set_ids"][0]
            rows = [{"card_variant_id": value} for value in self.client.authority.get(set_id, [])]
        elif self.kind == "rpc":
            batch = self.params["p_card_variant_ids"]
            self.client.writes.append(list(batch))
            rows = sum(len(self.client.intervals.get(value, [])) for value in batch)
            return Response(rows)
        elif self.name == "sets":
            rows = [{"id": value} for value in self.client.set_ids]
        else:
            requested = self.filters["card_variant_id"]
            rows = [
                {"observation_id": observation, "card_variant_id": variant}
                for variant in requested for observation in self.client.intervals.get(variant, [])
            ]
        return Response(rows[self.start:self.end + 1])


class Client:
    def __init__(self):
        self.set_ids = ["set-a", "set-b"]
        self.authority = {"set-a": ["v1", "v2", "v3"], "set-b": ["v4"]}
        self.intervals = {"v1": ["o1", "o2"], "v2": [], "v3": ["o3"], "v4": ["o4"]}
        self.writes = []

    def rpc(self, name, params):
        return Query(self, "rpc", name, params)

    def table(self, name):
        return Query(self, "table", name)


def test_dry_run_plans_deterministically_and_performs_no_writes():
    client = Client()
    report = run_backfill(client, commit=False, batch_size=2)
    assert client.writes == []
    assert report["variants_attempted"] == 4
    assert report["variants_succeeded"] == 4
    assert report["batches_succeeded"] == 3
    assert report["interval_rows_created"] == 0
    assert report["dry_run"] is True


def test_commit_reports_interval_and_empty_history_reconciliation():
    client = Client()
    report = run_backfill(client, commit=True, batch_size=2, set_ids=["set-a"])
    assert client.writes == [["v1", "v2"], ["v3"]]
    assert report["interval_rows_created"] == 3
    assert report["empty_history_variants"] == 1
    assert report["variants_with_history"] == 2
    assert report["variants_with_history"] + report["empty_history_variants"] == report["variants_succeeded"]
    assert report["failures"] == 0


def test_resume_cursor_skips_completed_batches_without_global_delete():
    client = Client()
    report = run_backfill(
        client, commit=True, batch_size=2, resume_after="set-a:v2",
    )
    assert client.writes == [["v3"], ["v4"]]
    assert report["variants_attempted"] == 2
    assert decode_cursor(report["resume_cursor"]) == ("set-b", "v4")


def test_rerunning_the_same_batch_is_idempotent_from_the_operator_view():
    client = Client()
    first = run_backfill(client, commit=True, batch_size=10, set_ids=["set-a"])
    second = run_backfill(client, commit=True, batch_size=10, set_ids=["set-a"])
    assert first["interval_rows_created"] == second["interval_rows_created"] == 3
    assert client.writes == [["v1", "v2", "v3"], ["v1", "v2", "v3"]]


def test_failed_batch_does_not_advance_cursor_past_the_failure():
    client = Client()
    original_rpc = client.rpc

    def rpc(name, params):
        query = original_rpc(name, params)
        if name == "refresh_pokemon_card_variant_market_price_intervals" and "v3" in params["p_card_variant_ids"]:
            def fail():
                raise RuntimeError("statement timeout")
            query.execute = fail
        return query

    client.rpc = rpc
    report = run_backfill(client, commit=True, batch_size=2)
    assert client.writes == [["v1", "v2"]]
    assert report["failures"] == 1
    assert report["resume_cursor"] == "set-a:v2"
    assert report["variants_succeeded"] == 2
