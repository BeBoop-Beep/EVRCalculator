from backend.scripts.publish_market_explorer_daily_projection import (
    load_approved_dates,
    run_publish,
)


class Response:
    def __init__(self, data):
        self.data = data


class Query:
    """Minimal chainable fake mirroring the supabase-py query builder surface
    this script actually calls: select/eq/in_/gt/lte/order/limit/range/execute,
    plus upsert for writes.
    """

    def __init__(self, client, kind, name, params=None):
        self.client = client
        self.kind = kind
        self.name = name
        self.params = params or {}
        self.eq_filters: dict = {}
        self.in_filters: dict = {}
        self.gt_value = None
        self.lte_filters: dict = {}
        self.start = None
        self.end = None
        self._upsert_rows = None

    def select(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self.end = (self.start or 0) + n - 1
        return self

    def eq(self, field, value):
        self.eq_filters[field] = value
        return self

    def in_(self, field, values):
        self.in_filters[field] = list(values)
        return self

    def gt(self, field, value):
        self.gt_value = (field, value)
        return self

    def lte(self, field, value):
        self.lte_filters[field] = value
        return self

    def range(self, start, end):
        self.start, self.end = start, end
        return self

    def upsert(self, rows, on_conflict=None):
        self._upsert_rows = rows
        self.client.writes.append(("upsert", self.name, list(rows)))
        return self

    def execute(self):
        if self._upsert_rows is not None:
            return Response(self._upsert_rows)

        if self.kind == "rpc":
            set_id = self.params["p_set_ids"][0]
            rows = [{"card_variant_id": v} for v in self.client.authority.get(set_id, [])]
            return Response(self._slice(rows))

        if self.name == "sets":
            rows = [{"id": v} for v in self.client.set_ids]
            return Response(self._slice(rows))

        if self.name == "pokemon_market_explorer_variant_merge_ledger":
            requested = self.in_filters.get("predecessor_variant_id", [])
            rows = [{"predecessor_variant_id": v} for v in self.client.retired if v in requested]
            return Response(self._slice(rows))

        if self.name == "pokemon_market_date_quality":
            rows = [{"market_date": d} for d in self.client.approved_dates]
            if self.gt_value:
                _, value = self.gt_value
                rows = [r for r in rows if r["market_date"] > value]
            if "market_date" in self.lte_filters:
                value = self.lte_filters["market_date"]
                rows = [r for r in rows if r["market_date"] <= value]
            return Response(self._slice(rows))

        if self.name == "pokemon_market_explorer_card_daily_coverage":
            set_id = self.eq_filters.get("set_id")
            row = self.client.coverage.get(set_id)
            rows = [dict(row)] if row else []
            return Response(self._slice(rows))

        if self.name == "pokemon_card_variant_market_price_intervals":
            requested = self.in_filters.get("card_variant_id", [])
            market_date = self.lte_filters.get("valid_from")
            rows = []
            for variant_id in requested:
                for interval in self.client.intervals.get(variant_id, []):
                    if interval["valid_from"] <= market_date and (
                        interval["valid_to"] is None or market_date < interval["valid_to"]
                    ):
                        rows.append({
                            "card_variant_id": variant_id,
                            "market_price": interval["market_price"],
                            "valid_from": interval["valid_from"],
                            "valid_to": interval["valid_to"],
                        })
            return Response(self._slice(rows))

        if self.name == "pokemon_market_explorer_card_daily_states":
            set_id = self.eq_filters.get("set_id")
            market_date = self.eq_filters.get("market_date")
            rows = [dict(r) for r in self.client.daily_states
                    if r["set_id"] == set_id and (market_date is None or r["market_date"] == market_date)]
            return Response(self._slice(rows))

        raise AssertionError(f"unexpected table {self.name}")

    def _slice(self, rows):
        if self.start is None:
            return rows
        return rows[self.start:self.end + 1]


class Client:
    def __init__(self):
        self.set_ids = ["set-a", "set-b"]
        self.authority = {"set-a": ["v1", "v2"], "set-b": ["v3"]}
        self.retired: list[str] = []
        self.approved_dates = ["2026-04-07", "2026-04-08", "2026-04-09"]
        self.coverage: dict = {}
        self.intervals = {
            "v1": [{"valid_from": "2026-04-07", "valid_to": None, "market_price": 10.0}],
            "v2": [{"valid_from": "2026-04-08", "valid_to": None, "market_price": 5.0}],
            "v3": [{"valid_from": "2026-04-07", "valid_to": "2026-04-09", "market_price": 2.0}],
        }
        self.daily_states: list[dict] = []
        self.writes: list = []

    def rpc(self, name, params):
        return Query(self, "rpc", name, params)

    def table(self, name):
        return Query(self, "table", name)

    # Test-only helper mirroring what a real upsert would durably do, so
    # subsequent reads (count/bounds) reflect committed writes.
    def apply_writes(self):
        for kind, table, rows in self.writes:
            if table == "pokemon_market_explorer_card_daily_states":
                for row in rows:
                    self.daily_states = [
                        r for r in self.daily_states
                        if not (r["set_id"] == row["set_id"] and r["market_date"] == row["market_date"]
                                and r["card_variant_id"] == row["card_variant_id"])
                    ]
                    self.daily_states.append(row)
            elif table == "pokemon_market_explorer_card_daily_coverage":
                for row in rows:
                    self.coverage[row["set_id"]] = row


def commit_with_apply(client, **kwargs):
    """run_publish, applying writes to the fake store as they're issued so
    later reads within the same run (reconciliation, coverage recompute) see
    them -- mirrors real Postgres read-your-writes behavior.
    """
    original_execute = Query.execute

    def execute_and_apply(self):
        response = original_execute(self)
        if self._upsert_rows is not None:
            client.apply_writes()
        return response

    Query.execute = execute_and_apply
    try:
        return run_publish(client, commit=True, **kwargs)
    finally:
        Query.execute = original_execute


def test_dry_run_performs_no_writes():
    client = Client()
    report = run_publish(client, commit=False)
    assert client.writes == []
    assert report["dry_run"] is True
    assert report["sets_attempted"] == 2


def test_new_set_activation_reconciles_and_activates_coverage():
    client = Client()
    report = commit_with_apply(client, set_ids=["set-a"])
    assert report["sets_new"] == 1
    assert report["sets_reconciliation_failed"] == 0
    set_report = report["reports"][0]
    assert set_report["reconciled"] is True
    # v1 has price from 04-07, v2 only from 04-08 onward: 3 + 2 = 5 rows across 3 dates.
    assert set_report["rows_inserted"] == 5
    assert client.coverage["set-a"]["row_count"] == 5
    assert client.coverage["set-a"]["first_market_date"] == "2026-04-07"
    assert client.coverage["set-a"]["computed_through"] == "2026-04-09"


def test_exact_interval_to_state_parity():
    client = Client()
    report = commit_with_apply(client, set_ids=["set-b"])
    set_report = report["reports"][0]
    # v3's interval closes at 04-09 (exclusive) -- only 04-07, 04-08 qualify.
    assert set_report["expected_rows"] == set_report["actual_rows"] == 2
    assert set_report["rows_inserted"] == 2


def test_coverage_not_activated_when_reconciliation_fails():
    client = Client()

    original_execute = Query.execute

    def broken_execute(self):
        response = original_execute(self)
        if self.name == "pokemon_market_explorer_card_daily_states" and self._upsert_rows is not None:
            # Simulate a partial write: only the first row lands.
            client.apply_writes()
            if client.daily_states:
                client.daily_states.pop()
        elif self._upsert_rows is not None:
            client.apply_writes()
        return response

    Query.execute = broken_execute
    try:
        report = run_publish(client, commit=True, set_ids=["set-a"])
    finally:
        Query.execute = original_execute

    assert report["sets_reconciliation_failed"] == 1
    assert "set-a" not in client.coverage


def test_coverage_row_count_derived_from_actual_table_not_trusted_input():
    client = Client()
    # Simulate the known 48/50 defect: coverage exists with a stale row_count
    # but correct date bounds, and the set is already fully up to date.
    client.daily_states = [
        {"set_id": "set-a", "market_date": d, "card_variant_id": "v1"}
        for d in client.approved_dates
    ]
    client.coverage["set-a"] = {
        "set_id": "set-a", "first_market_date": "2026-04-07",
        "computed_through": "2026-04-09", "row_count": 1,  # stale/understated
    }
    report = commit_with_apply(client, set_ids=["set-a"])
    set_report = report["reports"][0]
    assert set_report["mode"] == "up_to_date"
    assert client.coverage["set-a"]["row_count"] == 3
    assert report["coverage_rows_repaired"] == 1


def test_staggered_start_uses_sets_own_first_market_date():
    client = Client()
    report = commit_with_apply(client, set_ids=["set-b"])
    # set-b's own first materialized date, not forced to the global earliest.
    assert client.coverage["set-b"]["first_market_date"] == "2026-04-07"
    assert report["reports"][0]["mode"] == "new"


def test_forward_append_for_already_covered_set():
    client = Client()
    client.daily_states = [{"set_id": "set-a", "market_date": "2026-04-07", "card_variant_id": "v1"}]
    client.coverage["set-a"] = {
        "set_id": "set-a", "first_market_date": "2026-04-07",
        "computed_through": "2026-04-07", "row_count": 1,
    }
    report = commit_with_apply(client, set_ids=["set-a"])
    set_report = report["reports"][0]
    assert set_report["mode"] == "append"
    assert set_report["approved_dates_considered"] == 2  # only 04-08, 04-09 are new
    assert client.coverage["set-a"]["computed_through"] == "2026-04-09"
    assert client.coverage["set-a"]["row_count"] == 5


def test_idempotent_rerun_produces_no_duplicate_state():
    client = Client()
    first = commit_with_apply(client, set_ids=["set-a"])
    second = commit_with_apply(client, set_ids=["set-a"])
    assert first["reports"][0]["mode"] == "new"
    assert second["reports"][0]["mode"] == "up_to_date"
    assert client.coverage["set-a"]["row_count"] == 5
    keys = [(r["set_id"], r["market_date"], r["card_variant_id"]) for r in client.daily_states]
    assert len(keys) == len(set(keys))  # no duplicate PK rows


def test_retired_predecessor_variant_excluded_from_projection():
    client = Client()
    client.retired = ["v2"]
    report = commit_with_apply(client, set_ids=["set-a"])
    set_report = report["reports"][0]
    assert set_report["predecessor_variants_excluded"] > 0
    assert all(r["card_variant_id"] != "v2" for r in client.daily_states)


def test_no_nm_variant_excluded_without_fabricating_a_row():
    client = Client()
    client.intervals["v1"] = []  # no qualifying interval state at all
    report = commit_with_apply(client, set_ids=["set-a"])
    set_report = report["reports"][0]
    assert set_report["no_nm_skips"] > 0
    assert all(r["card_variant_id"] != "v1" for r in client.daily_states)


def test_load_approved_dates_filters_status_and_range():
    client = Client()
    dates = load_approved_dates(client, through=__import__("datetime").date(2026, 4, 8))
    assert dates == ["2026-04-07", "2026-04-08"]
