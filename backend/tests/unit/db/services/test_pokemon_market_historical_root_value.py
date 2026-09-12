from types import SimpleNamespace

import pytest

from backend.db.services import pokemon_market_historical_root_value as svc


class Query:
    def __init__(self, client, name, rows): self.client, self.name, self.rows, self.changes = client, name, list(rows), None
    def select(self, *_a): return self
    def eq(self, key, value): self.rows = [r for r in self.rows if r.get(key) == value]; return self
    def lte(self, key, value): self.rows = [r for r in self.rows if str(r.get(key)) <= str(value)]; return self
    def in_(self, key, values): self.rows = [r for r in self.rows if r.get(key) in values]; return self
    def limit(self, value): self.rows = self.rows[:value]; return self
    def upsert(self, rows, **_kwargs): self.client.writes.extend(rows); return self
    def insert(self, rows): self.client.writes.extend(rows); return self
    def update(self, changes): self.changes = changes; return self
    def execute(self):
        if self.changes:
            for row in self.rows: row.update(self.changes)
            self.client.writes.extend({"id": row.get("id"), **self.changes} for row in self.rows)
        return SimpleNamespace(data=self.rows)


class Client:
    def __init__(self, tables, prices): self.tables, self.prices, self.writes = tables, prices, []
    def table(self, name): return Query(self, name, self.tables.get(name, []))
    def rpc(self, _name, args): return Query(self, "rpc", self.prices.get(args["target_set_id"], []))


def fixture_client(captured_at="2026-09-10"):
    root, child = "root", "child"
    cards = ([{"id": f"r{i:02}", "set_id": root, "set_value_eligible": True} for i in range(6)]
             + [{"id": f"c{i:02}", "set_id": child, "set_value_eligible": True} for i in range(6)])
    prices = {}
    for member in (root, child):
        prices[member] = [{"canonical_card_id": row["id"], "card_variant_id": "v"+row["id"],
                           "market_price": str(i+1), "captured_at": captured_at}
                          for i, row in enumerate([r for r in cards if r["set_id"] == member])]
    tables = {
        "sets": [{"id": root, "name": "Root", "parent_opening_set_id": None},
                 {"id": child, "name": "Gallery", "parent_opening_set_id": root,
                  "counts_toward_parent_set_value": True}],
        "pokemon_canonical_cards": cards,
        "pokemon_market_root_authority": [{"set_id": root, "enabled": True,
            "activated_market_date": "2026-09-10", "deactivated_market_date": None}],
        svc.HISTORY_TABLE: [],
    }
    return Client(tables, prices)


def test_reader_combines_root_and_child_and_ranks_top10_together():
    result = svc.calculate_root_as_of(fixture_client(), "root", "2026-09-10")
    assert result["member_set_ids"] == ["child", "root"]
    assert result["standard"]["priced_card_count"] == 12
    assert result["standard"]["set_value"] == "42.00"
    assert len(result["top10"]["constituent_card_ids"]) == 10
    assert set(result["top10"]["constituent_card_ids"]) != set(result["standard"]["constituent_card_ids"][:10])


def test_root_without_child_is_supported():
    client = fixture_client(); client.tables["sets"] = client.tables["sets"][:1]
    client.tables["pokemon_canonical_cards"] = [r for r in client.tables["pokemon_canonical_cards"] if r["set_id"] == "root"]
    client.prices["root"] += [{"canonical_card_id": f"x{i}", "card_variant_id": f"vx{i}", "market_price": "1", "captured_at": "2026-09-10"} for i in range(4)]
    client.tables["pokemon_canonical_cards"] += [{"id": f"x{i}", "set_id": "root", "set_value_eligible": True} for i in range(4)]
    assert svc.calculate_root_as_of(client, "root", "2026-09-10")["member_set_ids"] == ["root"]


def test_future_price_leakage_fails_closed():
    with pytest.raises(RuntimeError, match="future price"):
        svc.calculate_root_as_of(fixture_client("2026-09-11"), "root", "2026-09-10")


def test_incomplete_root_fails_closed():
    client = fixture_client(); client.prices["child"].pop()
    with pytest.raises(RuntimeError, match="unpriced"):
        svc.calculate_root_as_of(client, "root", "2026-09-10")


def test_writer_is_bounded_authority_checked_and_dry_run(monkeypatch):
    client = fixture_client()
    projection = {"coverage_pct": "100.00", "member_set_ids": ["root"],
        "standard": {"value_scope": "standard", "set_value": "1.00", "priced_card_count": 1,
                     "total_card_count": 1, "canonical_card_count": 1, "linked_card_count": 1, "included_card_count": 1,
                     "constituent_card_ids": [], "source": svc.STANDARD_SOURCE},
        "top10": {"value_scope": "top10", "set_value": "2.00", "priced_card_count": 10,
                  "total_card_count": 10, "canonical_card_count": 10, "linked_card_count": 10, "included_card_count": 10,
                  "constituent_card_ids": [], "source": svc.TOP10_SOURCE}}
    monkeypatch.setattr(svc, "calculate_root_as_of", lambda *_a, **_k: projection)
    rows = svc.execute_historical_root_backfill(client, ["root"], "2026-09-10", "2026-09-10")
    assert len(rows) == 2 and not client.writes
    assert {r["source"] for r in rows} == {svc.STANDARD_SOURCE, svc.TOP10_SOURCE}
    with pytest.raises(ValueError, match="non-authority"):
        svc.plan_historical_root_backfill(client, ["other"], "2026-09-10", "2026-09-10")
    with pytest.raises(ValueError, match="root count"):
        svc.plan_historical_root_backfill(client, [str(i) for i in range(11)], "2026-09-10", "2026-09-10")


def test_existing_conflict_fails_and_identical_is_idempotent(monkeypatch):
    client = fixture_client(); base={"coverage_pct":"100.00","member_set_ids":["root"]}
    base["standard"]={"value_scope":"standard","set_value":"1.00","priced_card_count":1,"total_card_count":1,"canonical_card_count":1,"linked_card_count":1,"included_card_count":1,"constituent_card_ids":[],"source":svc.STANDARD_SOURCE}
    base["top10"]={"value_scope":"top10","set_value":"2.00","priced_card_count":10,"total_card_count":10,"canonical_card_count":10,"linked_card_count":10,"included_card_count":10,"constituent_card_ids":[],"source":svc.TOP10_SOURCE}
    monkeypatch.setattr(svc,"calculate_root_as_of",lambda *_a,**_k:base)
    client.tables[svc.HISTORY_TABLE]=[{"set_id":"root","snapshot_date":"2026-09-10","value_scope":"standard","set_value":"1.00","priced_card_count":1,"total_card_count":1,"canonical_card_count":1,"included_card_count":1,"coverage_pct":"100.00"}]
    rows=svc.plan_historical_root_backfill(client,["root"],"2026-09-10","2026-09-10")
    assert rows[0]["action"] == "noop_identical"
    client.tables[svc.HISTORY_TABLE][0]["set_value"]="9.00"
    with pytest.raises(RuntimeError,match="conflicting approved history"):
        svc.plan_historical_root_backfill(client,["root"],"2026-09-10","2026-09-10")


def test_commit_inserts_only_missing_rows_with_guard_allowlisted_sources(monkeypatch):
    client = fixture_client(); projection={"coverage_pct":"100.00","member_set_ids":["root"]}
    projection["standard"]={"value_scope":"standard","set_value":"1.00","priced_card_count":1,"total_card_count":1,"canonical_card_count":1,"linked_card_count":1,"included_card_count":1,"constituent_card_ids":[],"source":svc.STANDARD_SOURCE}
    projection["top10"]={"value_scope":"top10","set_value":"2.00","priced_card_count":10,"total_card_count":10,"canonical_card_count":10,"linked_card_count":10,"included_card_count":10,"constituent_card_ids":[],"source":svc.TOP10_SOURCE}
    monkeypatch.setattr(svc,"calculate_root_as_of",lambda *_a,**_k:projection)
    svc.execute_historical_root_backfill(client,["root"],"2026-09-10","2026-09-10",commit=True)
    assert len(client.writes) == 2
    assert {row["source"] for row in client.writes} == {svc.STANDARD_SOURCE, svc.TOP10_SOURCE}


def test_guard_migration_allowlists_only_intended_backfill_sources():
    sql = open("supabase/migrations/20260908211701_price_storage_v2_serving_cutover.sql", encoding="utf-8").read()
    assert svc.STANDARD_SOURCE in sql and svc.TOP10_SOURCE in sql


def test_explicit_normalization_changes_only_exact_source(monkeypatch):
    client = fixture_client(); projection={"coverage_pct":"100.00","member_set_ids":["root"]}
    projection["standard"]={"value_scope":"standard","set_value":"1.00","priced_card_count":1,"total_card_count":1,"canonical_card_count":1,"linked_card_count":1,"included_card_count":1,"constituent_card_ids":[],"source":svc.STANDARD_SOURCE}
    projection["top10"]={"value_scope":"top10","set_value":"2.00","priced_card_count":10,"total_card_count":10,"canonical_card_count":10,"linked_card_count":10,"included_card_count":10,"constituent_card_ids":[],"source":svc.TOP10_SOURCE}
    monkeypatch.setattr(svc,"calculate_root_as_of",lambda *_a,**_k:projection)
    client.tables[svc.HISTORY_TABLE]=[
        {"id":"s","set_id":"root","snapshot_date":"2026-09-10","value_scope":"standard","set_value":"1.00","priced_card_count":1,"total_card_count":1,"canonical_card_count":1,"linked_card_count":1,"included_card_count":1,"coverage_pct":"100.00","source":"generic"},
        {"id":"t","set_id":"root","snapshot_date":"2026-09-10","value_scope":"top10","set_value":"2.00","priced_card_count":10,"total_card_count":10,"canonical_card_count":10,"linked_card_count":10,"included_card_count":10,"coverage_pct":"100.00","source":"candidate"},
    ]
    default=svc.execute_historical_root_backfill(client,["root"],"2026-09-10","2026-09-10",commit=True)
    assert {r["action"] for r in default} == {"noop_identical"} and not client.writes
    changed=svc.execute_historical_root_backfill(client,["root"],"2026-09-10","2026-09-10",commit=True,normalize_provenance=True)
    assert {r["action"] for r in changed} == {"normalize_provenance"}
    assert {r["source"] for r in client.tables[svc.HISTORY_TABLE]} == {svc.STANDARD_SOURCE,svc.TOP10_SOURCE}
    assert all(set(write) == {"id","source"} for write in client.writes)
