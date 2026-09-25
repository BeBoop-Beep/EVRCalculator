from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.db.services import market_publication_sources as sources

DAY = "2026-09-25"


class Query:
    def __init__(self, client, table):
        self.client = client
        self.table_name = table
        self.filters = {}
        self.fields = None
        self.ids = []
        self.cap = None

    def select(self, fields):
        self.fields = fields
        return self

    def eq(self, name, value):
        self.filters[name] = value
        return self

    def in_(self, name, values):
        assert name == "set_id"
        self.ids = list(values)
        return self

    def limit(self, value):
        self.cap = value
        return self

    def execute(self):
        self.client.reads.append(self)
        if self.table_name == "sets":
            assert self.fields == "id" and self.cap == 1
            assert self.filters["counts_toward_parent_set_value"] is True
            return SimpleNamespace(data=[{"id": "subset"}] if self.client.composite else [])
        assert self.table_name == "pokemon_set_market_dashboard_snapshot_latest"
        return SimpleNamespace(data=[deepcopy(row) for row in self.client.rows if row["set_id"] in self.ids])


class Client:
    def __init__(self, rows=(), composite=False, receipt=None, error=None, freeze_receipt=None):
        self.rows = list(rows)
        self.composite = composite
        self.receipt = receipt
        self.error = error
        self.freeze_receipt = freeze_receipt
        self.reads = []
        self.rpcs = []

    def table(self, name):
        return Query(self, name)

    def rpc(self, name, args):
        self.rpcs.append((name, args))
        def execute():
            if self.error:
                raise self.error
            if name == sources.LEGACY_FREEZE_RPC:
                data = self.freeze_receipt
                if data is None:
                    data = {"status": "frozen", "setId": "root", "marketDate": DAY}
                return SimpleNamespace(data=data)
            return SimpleNamespace(data=self.receipt)
        return SimpleNamespace(execute=execute)


def compact_row(set_id="s", outer=DAY, inner=DAY, percent=0.0):
    return {"set_id": set_id, "window_key": "365d", "latest_market_date": outer,
            "index_as_of": inner, "index_value": 110.0, "index_base": 100.0,
            "index_movements": {"7d": {"available": True, "percent": percent,
                                      "startDate": "2026-09-18", "endDate": DAY}}}


def test_prepared_reads_are_compact_and_batched():
    ids = [f"s{i}" for i in range(43)]
    client = Client([compact_row(s) for s in ids])
    rows = sources.load_compact_market_index_summaries(client, ids + ids)
    assert len(rows) == 43
    assert [len(q.ids) for q in client.reads] == [20, 20, 3]
    for query in client.reads:
        assert query.filters == {"window_key": "365d"}
        assert "set_value_histories_json" not in query.fields
        assert "->history" not in query.fields
        assert "cardsMarket:payload_json->cardsMarket" not in query.fields
    assert rows[0]["cardsMarket"]["marketIndex"]["movements"]["7d"]["percent"] == 0.0


def test_empty_ids_do_not_read():
    client = Client()
    assert sources.load_compact_market_index_summaries(client, []) == []
    assert client.reads == []


@pytest.mark.parametrize("outer,inner", [(DAY, DAY), ("2026-09-24", DAY), (DAY, "2026-09-24"), (DAY, "2026-09-26")])
def test_projection_never_relabels_watermarks(outer, inner):
    client = Client([compact_row(outer=outer, inner=inner)])
    row = sources.load_compact_market_index_summaries(client, ["s"])[0]
    assert row["latest_market_date"] == outer
    assert row["cardsMarket"]["marketIndex"]["asOf"] == inner


@pytest.mark.parametrize("status,n", [("repaired", 2), ("already_current", 0)])
def test_composite_root_uses_canonical_rpc(status, n):
    receipt = {"status": status, "rowsUpserted": n, "setId": "root", "marketDate": DAY}
    client = Client(composite=True, receipt=receipt)
    assert sources.refresh_market_root_day(client, "root", DAY).data == receipt
    assert client.rpcs == [(sources.COMPOSITE_REPAIR_RPC, {"p_root_set_id": "root", "p_market_date": DAY})]


def test_ordinary_root_repairs_then_freezes_exact_legacy_roster():
    client = Client(receipt=2)
    assert sources.refresh_market_root_day(client, "root", DAY).data == 2
    assert client.rpcs == [
        (sources.LEGACY_REPAIR_RPC, {"p_set_id": "root", "p_start_date": DAY, "p_end_date": DAY}),
        (sources.LEGACY_FREEZE_RPC, {"p_root_set_id": "root", "p_market_date": DAY}),
    ]


@pytest.mark.parametrize("freeze_receipt", [
    None,
    {},
    {"status": "failed", "setId": "root", "marketDate": DAY},
    {"status": "frozen", "setId": "other", "marketDate": DAY},
])
def test_legacy_repair_fails_closed_when_roster_freeze_is_not_accepted(freeze_receipt):
    client = Client(receipt=2, freeze_receipt=freeze_receipt)
    if freeze_receipt is None:
        client.freeze_receipt = {}
    with pytest.raises(RuntimeError):
        sources.refresh_market_root_day(client, "root", DAY)
    assert [name for name, _ in client.rpcs] == [
        sources.LEGACY_REPAIR_RPC,
        sources.LEGACY_FREEZE_RPC,
    ]


@pytest.mark.parametrize("receipt", [None, 0, {}, {"status": "failed"}, {"status": "repaired", "setId": "other", "marketDate": DAY}])
def test_canonical_failure_does_not_fall_back(receipt):
    client = Client(composite=True, receipt=receipt)
    with pytest.raises(RuntimeError):
        sources.refresh_market_root_day(client, "root", DAY)
    assert len(client.rpcs) == 1 and client.rpcs[0][0] == sources.COMPOSITE_REPAIR_RPC


def test_canonical_exception_does_not_fall_back():
    client = Client(composite=True, error=RuntimeError("incomplete prices"))
    with pytest.raises(RuntimeError, match="incomplete prices"):
        sources.refresh_market_root_day(client, "root", DAY)
    assert len(client.rpcs) == 1


def test_repair_entrypoint_accepts_json_receipt(monkeypatch):
    from backend.scripts import repair_missing_market_set_value_history as repair
    client = Client(composite=True, receipt={"status": "repaired", "rowsUpserted": 2, "setId": "root", "marketDate": DAY})
    monkeypatch.setattr(repair, "run_supabase_with_transient_retry", lambda fn, **kw: fn(client, 1))
    assert repair._refresh_one("root", DAY) == 2
    assert client.rpcs[0][0] == sources.COMPOSITE_REPAIR_RPC


def test_post_cutover_builder_loads_only_standard_index_summaries(monkeypatch):
    from backend.scripts import build_pokemon_explore_set_value_snapshot as publisher
    sets = [{"id": "regular", "market_scope": "standard"},
            {"id": "vintage", "market_scope": "first_edition"}]
    seen = {}
    monkeypatch.setattr(publisher, "_load_sets", lambda *a, **kw: sets)
    monkeypatch.setattr(publisher, "_expand_market_scope_rows", lambda *a, **kw: sets)
    monkeypatch.setattr(publisher, "_load_canonical_histories", lambda *a, **kw: {})
    monkeypatch.setattr(publisher, "_attach_initial_selected_set_movers", lambda *a, **kw: None)
    monkeypatch.setattr(publisher, "publisher_build_sha", lambda: "test")
    def compact(client, ids):
        seen["ids"] = ids
        return [{"set_id": "regular"}]
    monkeypatch.setattr(sources, "load_compact_market_index_summaries", compact)
    def build(sets, dashboards, histories, **kwargs):
        seen["dashboards"] = dashboards
        return {"payload_json": {}}
    monkeypatch.setattr(publisher, "build_global_set_value_row", build)
    publisher.build(client=object(), market_date=DAY, commit=False, market_overview={})
    assert seen == {"ids": ["regular"], "dashboards": [{"set_id": "regular"}]}


def test_migration_mirrors_and_safety_contract():
    root = Path(__file__).resolve().parents[4]
    name = "20260925212955_bounded_composite_root_set_value_repair.sql"
    sql = (root / "supabase/migrations" / name).read_text()
    assert sql == (root / "backend/db/migrations" / name).read_text()
    for required in ["SECURITY INVOKER", "statement_timeout = '20s'", "lock_timeout = '2s'",
                     "pg_try_advisory_xact_lock", "counts_toward_parent_set_value=true",
                     "replace_pokemon_market_set_value_constituents_v1", "v_invalid<>0",
                     "FROM PUBLIC,anon,authenticated", "TO service_role"]:
        assert required in sql


def test_legacy_roster_freezer_migration_mirrors_and_is_bounded():
    root = Path(__file__).resolve().parents[4]
    name = "20260925234500_freeze_legacy_set_value_rosters_for_market_explorer_v2.sql"
    sql = (root / "supabase/migrations" / name).read_text()
    assert sql == (root / "backend/db/migrations" / name).read_text()
    for required in [
        "SECURITY INVOKER",
        "statement_timeout = '20s'",
        "statement_timeout = '90s'",
        "lock_timeout = '2s'",
        "pg_try_advisory_xact_lock",
        "LEGACY_SET_VALUE_ROSTER_RECONCILIATION_FAILED",
        "count(DISTINCT card_variant_id)",
        "replace_pokemon_market_set_value_constituents_v1",
        "p_limit>10",
        "FROM PUBLIC,anon,authenticated",
        "TO service_role",
    ]:
        assert required in sql
