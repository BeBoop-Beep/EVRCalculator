from types import SimpleNamespace

import pytest

from backend.db.services import pokemon_market_historical_root_value as svc


class Query:
    def __init__(self, client, name, rows): self.client, self.name, self.rows, self.changes, self.selected = client, name, list(rows), None, None
    def select(self, fields="*", *_a): self.selected = None if fields == "*" else fields.split(","); return self
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
        rows = self.rows
        if self.selected is not None:
            rows = [{key: row.get(key) for key in self.selected} for row in rows]
        return SimpleNamespace(data=rows)


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
        svc.ROLLOUT_VIEW: [{"set_id": root, "enabled": True,
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
    assert client.tables[svc.HISTORY_TABLE][0]["linked_card_count"] == 1
    assert client.tables[svc.HISTORY_TABLE][1]["linked_card_count"] == 10
    assert client.tables[svc.HISTORY_TABLE][0]["set_value"] == "1.00"
    assert client.tables[svc.HISTORY_TABLE][1]["set_value"] == "2.00"


def test_normalization_postread_missing_linked_count_fails_closed(monkeypatch):
    old = {
        "id": "s", "set_id": "root", "snapshot_date": "2026-09-10",
        "value_scope": "standard", "set_value": "1.00", "priced_card_count": 1,
        "total_card_count": 1, "canonical_card_count": 1, "linked_card_count": 1,
        "included_card_count": 1, "coverage_pct": "100.00", "source": "generic",
    }
    planned = {
        **old, "source": svc.STANDARD_SOURCE, "action": "normalize_provenance",
        "existing_row_id": "s", "existing_source": "generic",
        "existing_material": {key: old[key] for key in (
            "set_id", "snapshot_date", "value_scope", "set_value", "priced_card_count",
            "total_card_count", "canonical_card_count", "linked_card_count",
            "included_card_count", "coverage_pct",
        )},
    }

    class MissingLinkedQuery(Query):
        def execute(self):
            result = super().execute()
            if self.selected is not None and self.selected and self.selected[0] == "id":
                result.data = [{key: value for key, value in row.items()
                                if key != "linked_card_count"} for row in result.data]
            return result

    class MissingLinkedClient(Client):
        def table(self, name): return MissingLinkedQuery(self, name, self.tables.get(name, []))

    client = MissingLinkedClient({svc.HISTORY_TABLE: [old]}, {})
    monkeypatch.setattr(svc, "plan_historical_root_backfill", lambda *_a, **_k: [planned])
    with pytest.raises(RuntimeError, match="provenance normalization postcondition failed"):
        svc.execute_historical_root_backfill(
            client, ["root"], "2026-09-10", "2026-09-10",
            commit=True, normalize_provenance=True,
        )


def repair_projection(standard="427.72", top10="295.20", count=91):
    return {
        "coverage_pct": "100.00", "member_set_ids": ["root"],
        "standard": {"value_scope": "standard", "set_value": standard,
                     "priced_card_count": count, "total_card_count": count,
                     "canonical_card_count": count, "linked_card_count": count,
                     "included_card_count": count, "constituent_card_ids": [],
                     "source": svc.STANDARD_SOURCE},
        "top10": {"value_scope": "top10", "set_value": top10,
                  "priced_card_count": 10, "total_card_count": 10,
                  "canonical_card_count": 10, "linked_card_count": 10,
                  "included_card_count": 10, "constituent_card_ids": [],
                  "source": svc.TOP10_SOURCE},
    }


def history_row(scope, value, count, source, day="2026-09-11", row_id=None):
    return {
        "id": row_id or scope, "set_id": "root", "snapshot_date": day,
        "value_scope": scope, "set_value": value, "priced_card_count": count,
        "total_card_count": count, "canonical_card_count": count,
        "linked_card_count": count, "included_card_count": count,
        "coverage_pct": "100.00", "source": source,
    }


def install_anchor(client, projection):
    client.tables[svc.HISTORY_TABLE].extend([
        history_row("standard", projection["standard"]["set_value"],
                    projection["standard"]["priced_card_count"], "approved",
                    day=svc.ROOT_AUTHORITY_CUTOVER, row_id="anchor-s"),
        history_row("top10", projection["top10"]["set_value"], 10, "approved",
                    day=svc.ROOT_AUTHORITY_CUTOVER, row_id="anchor-t"),
    ])


def test_pokemon_go_91_card_root_repairs_only_in_explicit_mode(monkeypatch):
    client = fixture_client()
    projection = repair_projection()
    install_anchor(client, projection)
    client.tables[svc.HISTORY_TABLE].extend([
        history_row("standard", "381.24", 88, svc.LEGACY_GENERIC_SOURCES["standard"]),
        history_row("top10", "277.77", 10, svc.LEGACY_GENERIC_SOURCES["top10"]),
    ])
    monkeypatch.setattr(svc, "calculate_root_as_of", lambda *_a, **_k: projection)
    with pytest.raises(RuntimeError, match="conflicting approved history"):
        svc.plan_historical_root_backfill(client, ["root"], "2026-09-11", "2026-09-11")
    with pytest.raises(ValueError, match="requires normalize_provenance"):
        svc.plan_historical_root_backfill(client, ["root"], "2026-09-11", "2026-09-11",
                                          repair_conflicting_generic=True)
    plan = svc.plan_historical_root_backfill(
        client, ["root"], "2026-09-11", "2026-09-11",
        normalize_provenance=True, repair_conflicting_generic=True,
    )
    assert {row["action"] for row in plan} == {"repair_conflicting_generic"}
    assert plan[0]["activation_anchor"]["passed"] is True
    assert plan[0]["old_material"]["priced_card_count"] == 88
    assert plan[0]["new_material"]["priced_card_count"] == 91
    assert plan[0]["new_material"]["coverage_pct"] == "100.00"


@pytest.mark.parametrize("old,new", [("514.08", "515.63"), ("2276.61", "2276.35")])
def test_stale_same_cardinality_aggregate_requires_economic_repair(monkeypatch, old, new):
    client = fixture_client(); projection = repair_projection(standard=new)
    install_anchor(client, projection)
    client.tables[svc.HISTORY_TABLE].append(
        history_row("standard", old, 91, svc.LEGACY_GENERIC_SOURCES["standard"])
    )
    monkeypatch.setattr(svc, "calculate_root_as_of", lambda *_a, **_k: projection)
    with pytest.raises(RuntimeError, match="conflicting approved history"):
        svc.plan_historical_root_backfill(client, ["root"], "2026-09-11", "2026-09-11",
                                          normalize_provenance=True)
    plan = svc.plan_historical_root_backfill(
        client, ["root"], "2026-09-11", "2026-09-11",
        normalize_provenance=True, repair_conflicting_generic=True,
    )
    assert plan[0]["action"] == "repair_conflicting_generic"
    assert plan[0]["old_material"]["set_value"] == old
    assert plan[0]["new_material"]["set_value"] == new


@pytest.mark.parametrize("source", sorted(svc.PROTECTED_ROOT_SOURCES))
def test_conflicting_canonical_sources_are_never_repaired(monkeypatch, source):
    client = fixture_client(); projection = repair_projection(); install_anchor(client, projection)
    client.tables[svc.HISTORY_TABLE].append(history_row("standard", "1.00", 91, source))
    monkeypatch.setattr(svc, "calculate_root_as_of", lambda *_a, **_k: projection)
    with pytest.raises(RuntimeError, match="refusing conflicting canonical-root"):
        svc.plan_historical_root_backfill(client, ["root"], "2026-09-11", "2026-09-11",
            normalize_provenance=True, repair_conflicting_generic=True)


def test_unknown_source_non_rollout_and_failed_anchor_are_rejected(monkeypatch):
    projection = repair_projection()
    monkeypatch.setattr(svc, "calculate_root_as_of", lambda *_a, **_k: projection)
    client = fixture_client(); install_anchor(client, projection)
    client.tables[svc.HISTORY_TABLE].append(history_row("standard", "1.00", 91, "unknown"))
    with pytest.raises(RuntimeError, match="unknown conflict source"):
        svc.plan_historical_root_backfill(client, ["root"], "2026-09-11", "2026-09-11",
            normalize_provenance=True, repair_conflicting_generic=True)
    client = fixture_client(); install_anchor(client, projection); client.tables[svc.ROLLOUT_VIEW] = []
    client.tables[svc.HISTORY_TABLE].append(history_row("standard", "1.00", 91, svc.LEGACY_GENERIC_SOURCES["standard"]))
    with pytest.raises(RuntimeError, match="non-rollout"):
        svc.plan_historical_root_backfill(client, ["root"], "2026-09-11", "2026-09-11",
            normalize_provenance=True, repair_conflicting_generic=True)
    client = fixture_client()
    client.tables[svc.HISTORY_TABLE].extend([
        history_row("standard", "1.00", 91, "approved", day="2026-09-10", row_id="anchor-s"),
        history_row("top10", "295.20", 10, "approved", day="2026-09-10", row_id="anchor-t"),
        history_row("standard", "1.00", 91, svc.LEGACY_GENERIC_SOURCES["standard"]),
    ])
    with pytest.raises(RuntimeError, match="activation anchor mismatch"):
        svc.plan_historical_root_backfill(client, ["root"], "2026-09-11", "2026-09-11",
            normalize_provenance=True, repair_conflicting_generic=True)


def test_pre_cutover_and_non_authority_repairs_are_rejected(monkeypatch):
    client = fixture_client(); projection = repair_projection()
    client.tables["pokemon_market_root_authority"][0]["activated_market_date"] = "2026-09-09"
    client.tables[svc.HISTORY_TABLE].append(history_row(
        "standard", "1.00", 91, svc.LEGACY_GENERIC_SOURCES["standard"], day="2026-09-09"))
    monkeypatch.setattr(svc, "calculate_root_as_of", lambda *_a, **_k: projection)
    with pytest.raises(RuntimeError, match="before root-authority cutover"):
        svc.plan_historical_root_backfill(client, ["root"], "2026-09-09", "2026-09-09",
            normalize_provenance=True, repair_conflicting_generic=True)
    client = fixture_client(); client.tables["pokemon_market_root_authority"] = []
    with pytest.raises(ValueError, match="non-authority"):
        svc.plan_historical_root_backfill(client, ["root"], "2026-09-11", "2026-09-11",
            normalize_provenance=True, repair_conflicting_generic=True)


def test_economic_repair_uses_strict_cas_and_preserves_identity(monkeypatch):
    client = fixture_client(); projection = repair_projection(); install_anchor(client, projection)
    old = history_row("standard", "381.24", 88, svc.LEGACY_GENERIC_SOURCES["standard"], row_id="repair-id")
    old["created_at"] = "kept"
    client.tables[svc.HISTORY_TABLE].append(old)
    monkeypatch.setattr(svc, "calculate_root_as_of", lambda *_a, **_k: projection)
    svc.execute_historical_root_backfill(client, ["root"], "2026-09-11", "2026-09-11", commit=True,
        normalize_provenance=True, repair_conflicting_generic=True)
    assert old["id"] == "repair-id" and old["created_at"] == "kept"
    assert old["set_value"] == "427.72" and old["source"] == svc.STANDARD_SOURCE
    assert "updated_at" in old


def test_concurrent_old_row_mismatch_aborts_repair(monkeypatch):
    projection = repair_projection()
    planned = {**projection["standard"], "set_id": "root", "snapshot_date": "2026-09-11",
               "coverage_pct": "100.00", "action": "repair_conflicting_generic",
               "existing_row_id": "repair-id", "existing_source": svc.LEGACY_GENERIC_SOURCES["standard"],
               "existing_material": (_old := history_row("standard", "381.24", 88,
                   svc.LEGACY_GENERIC_SOURCES["standard"], row_id="repair-id"))}
    client = fixture_client()
    client.tables[svc.HISTORY_TABLE] = [{**_old, "set_value": "changed concurrently"}]
    monkeypatch.setattr(svc, "plan_historical_root_backfill", lambda *_a, **_k: [planned])
    with pytest.raises(RuntimeError, match="concurrent economic repair mismatch"):
        svc.execute_historical_root_backfill(client, ["root"], "2026-09-11", "2026-09-11", commit=True,
            normalize_provenance=True, repair_conflicting_generic=True)


# ---- frozen Set Value leaf roster ----
from backend.domain.pokemon.market_index import MARKET_INDEX_METHODOLOGY_VERSION as _MIV


class _RpcRecorder(Client):
    def __init__(self, *a, fail=False):
        super().__init__(*a); self.rpc_calls = []; self.fail = fail
    def rpc(self, name, args):
        if name == "replace_pokemon_market_set_value_constituents_v1":
            self.rpc_calls.append(args)
            if self.fail:
                raise RuntimeError("SET_VALUE_CONSTITUENT_VALUE_MISMATCH")
            return SimpleNamespace(execute=lambda: SimpleNamespace(data={"status": "READY"}))
        return super().rpc(name, args)


def _recorder(**kw):
    base = fixture_client()
    return _RpcRecorder(base.tables, base.prices, **kw)


def test_freeze_passes_exact_in_memory_rows_and_canonical_version():
    client = _recorder()
    plan = svc.execute_historical_root_backfill(client, ["root"], "2026-09-10", "2026-09-10",
                                                commit=True, freeze_constituents=True)
    assert len(client.rpc_calls) == 1
    call = client.rpc_calls[0]
    std = [r for r in plan if r["value_scope"] == "standard"][0]
    assert call["p_root_set_id"] == "root" and call["p_market_date"] == "2026-09-10"
    assert call["p_methodology_version"] == _MIV
    assert call["p_expected_card_count"] == len(call["p_items"]) == std["included_card_count"] == 12
    assert sum(float(i["marketPrice"]) for i in call["p_items"]) == float(std["set_value"]) == float(call["p_expected_set_value"])
    assert {i["setId"] for i in call["p_items"]} == {"root", "child"}
    assert all(i["cardVariantId"] == "v" + i["canonicalCardId"] for i in call["p_items"])


def test_dry_run_and_default_do_zero_freeze_calls():
    client = _recorder()
    svc.execute_historical_root_backfill(client, ["root"], "2026-09-10", "2026-09-10", freeze_constituents=True)
    svc.execute_historical_root_backfill(client, ["root"], "2026-09-10", "2026-09-10", commit=True)
    assert client.rpc_calls == []


def test_freeze_rpc_failure_propagates_without_retry():
    from backend.db.services.pokemon_set_value_constituent_freeze import SetValueConstituentFreezeError
    client = _recorder(fail=True)
    with pytest.raises(SetValueConstituentFreezeError, match="VALUE_MISMATCH"):
        svc.execute_historical_root_backfill(client, ["root"], "2026-09-10", "2026-09-10",
                                             commit=True, freeze_constituents=True)
    assert len(client.rpc_calls) == 1


def test_freeze_does_not_repair_inconsistent_roster():
    from backend.db.services import pokemon_set_value_constituent_freeze as f
    client = _recorder()
    items = [{"canonicalCardId": "a", "cardVariantId": "va", "setId": "s", "marketPrice": "1.00"}]
    with pytest.raises(f.SetValueConstituentFreezeError, match="SUM_MISMATCH"):
        f.freeze_set_value_constituents(client, root_set_id="root", market_date="2026-09-10",
                                        set_value="2.00", items=items, commit=True)
    assert client.rpc_calls == []
