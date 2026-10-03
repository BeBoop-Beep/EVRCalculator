from __future__ import annotations

import copy
from datetime import date

import pytest

from backend.scripts import index_fair_value_shadow_ledger_v1 as ledger_mod
from backend.scripts import run_index_fair_value_forward_outcomes_v1 as forward


class Result:
    def __init__(self, data=None):
        self.data = data or []


class Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters = db, table, []

    def select(self, *_a, **_k): return self
    def eq(self, k, v):
        self.filters.append(lambda r, k=k, v=v: str(r.get(k)) == str(v)); return self
    def in_(self, k, vals):
        vals={str(v) for v in vals}; self.filters.append(lambda r,k=k,vals=vals: str(r.get(k)) in vals); return self
    def gte(self, k, v):
        self.filters.append(lambda r,k=k,v=v: str(r.get(k)) >= str(v)); return self
    def lte(self, k, v):
        self.filters.append(lambda r,k=k,v=v: str(r.get(k)) <= str(v)); return self
    def order(self, *_a, **_k): return self
    def insert(self, payload):
        self.db.inserts.append((self.table, copy.deepcopy(payload))); return self
    def limit(self, *_a): return self

    def execute(self):
        self.db.executions.append(self.table)
        rows=[copy.deepcopy(r) for r in self.db.tables.get(self.table,[]) if all(f(r) for f in self.filters)]
        return Result(rows)


class DB:
    def __init__(self,tables):
        self.tables=tables; self.inserts=[]; self.executions=[]
    def table(self,name): return Query(self,name)


def pub():
    return {
        "publication_id":"11111111-1111-1111-1111-111111111111",
        "canonical_card_id":"22222222-2222-2222-2222-222222222222",
        "card_variant_id":"33333333-3333-3333-3333-333333333333",
        "evaluation_date":"2026-10-02",
        "median":"110.0000",
        "status":"ANCHORED",
        "evidence_status":"PROSPECTIVE_AS_KNOWN_AT_CUTOFF",
    }


def h0(price=100.0):
    return {
        "publication_id":pub()["publication_id"],"horizon_days":0,"comparison_date":"2026-10-02",
        "comparison_market_price_usd":price,"comparison_price_source":"TCGPlayer","outcome_status":"COMPLETE",
    }


def obs(day,price,condition="44444444-4444-4444-4444-444444444444"):
    return {
        "card_variant_id":pub()["card_variant_id"],"condition_id":condition,"market_price":price,
        "captured_at":day,"source":"TCGPlayer","currency":"USD",
    }


def binding():
    return {
        "publication_id": pub()["publication_id"],
        "schema_version": forward.BINDING_SCHEMA_VERSION,
        "canonical_card_id": pub()["canonical_card_id"],
        "card_variant_id": pub()["card_variant_id"],
        "condition_id": "44444444-4444-4444-4444-444444444444",
        "baseline_date": "2026-10-02",
        "baseline_market_price_usd": 100.0,
        "price_source": "TCGPlayer",
        "currency": "USD",
        "binding_method": forward.BINDING_METHOD,
    }


def batch(day, status="complete"):
    return {"market_date": day, "status": status}


def test_unique_h0_binding_is_frozen_and_future_price_uses_same_condition():
    db=DB({"card_variant_price_observations":[obs("2026-10-02",100),obs("2026-10-03",105)]})
    binding=forward.derive_binding(db,pub(),h0())
    assert binding["condition_id"]=="44444444-4444-4444-4444-444444444444"
    assert binding["baseline_market_price_usd"]==100
    assert forward.read_bound_price(db,binding,date(2026,10,3))["market_price_usd"]==105


def test_h0_binding_ambiguity_fails_closed():
    db=DB({"card_variant_price_observations":[
        obs("2026-10-02",100,"44444444-4444-4444-4444-444444444444"),
        obs("2026-10-02",100,"55555555-5555-5555-5555-555555555555"),
    ]})
    with pytest.raises(forward.ForwardOutcomeError,match="CARDINALITY_2"):
        forward.derive_binding(db,pub(),h0())


def test_bound_future_price_ambiguity_fails_closed():
    binding={
        "card_variant_id":pub()["card_variant_id"],"condition_id":"44444444-4444-4444-4444-444444444444",
        "price_source":"TCGPlayer","baseline_market_price_usd":100,
    }
    db=DB({"card_variant_price_observations":[obs("2026-10-03",105),obs("2026-10-03",106)]})
    with pytest.raises(forward.ForwardOutcomeError,match="BOUND_PRICE_AMBIGUOUS"):
        forward.read_bound_price(db,binding,date(2026,10,3))


def test_binding_adapter_is_idempotent_and_conflict_safe(monkeypatch):
    monkeypatch.setattr(ledger_mod,"WRITE_ENABLED",True)
    class AdapterDB(DB):
        pass
    db=AdapterDB({"fair_value_shadow_market_bindings_v1":[]})
    adapter=ledger_mod.SupabaseShadowLedger(db)
    rec={
        "publication_id":pub()["publication_id"],"schema_version":forward.BINDING_SCHEMA_VERSION,
        "canonical_card_id":pub()["canonical_card_id"],"card_variant_id":pub()["card_variant_id"],
        "condition_id":"44444444-4444-4444-4444-444444444444","baseline_date":"2026-10-02",
        "baseline_market_price_usd":100.0,"price_source":"TCGPlayer","currency":"USD",
        "binding_method":forward.BINDING_METHOD,
    }
    assert adapter.append_market_binding(rec)=="INSERTED"
    stored_fp = ledger_mod._canonical_fingerprint(rec)
    db.tables["fair_value_shadow_market_bindings_v1"] = [{
        "publication_id": rec["publication_id"],
        "content_fingerprint": stored_fp,
    }]
    assert adapter.append_market_binding(rec)=="IDEMPOTENT_NOOP"


def test_bindings_only_dry_run_never_evaluates_forward_horizons():
    p = pub()
    db = DB({
        "fair_value_shadow_anchor_publications_v1": [p],
        "fair_value_shadow_evaluation_outcomes_v1": [h0()],
        "fair_value_shadow_market_bindings_v1": [],
        "card_variant_price_observations": [
            obs("2026-10-02", 100),
            obs("2026-10-03", 105),
        ],
    })
    result = forward.collect(
        db=db,
        ledger=ledger_mod.InMemoryShadowLedger(),
        today=date(2026, 10, 3),
        dry_run=True,
        bindings_only=True,
    )
    assert result["bindings_only"] is True
    assert result["binding_statuses"] == {"WOULD_INSERT": 1}
    assert result["outcome_statuses"] == {}
    assert result["binding_failures"] == []
    assert result["outcome_failures"] == []


def test_due_horizon_defers_until_authoritative_batch_is_complete():
    p = pub()
    b = binding()
    db = DB({
        "fair_value_shadow_anchor_publications_v1": [p],
        "fair_value_shadow_evaluation_outcomes_v1": [h0()],
        "fair_value_shadow_market_bindings_v1": [b],
        "card_variant_price_observations": [obs("2026-10-03", 105)],
        "pokemon_scrape_batches": [],
    })
    result = forward.collect(
        db=db,
        ledger=ledger_mod.InMemoryShadowLedger(),
        today=date(2026, 10, 3),
        dry_run=True,
    )
    assert result["outcome_statuses"] == {"DEFERRED_BATCH_NOT_COMPLETE": 1}
    assert result["outcome_failures"] == []


def test_due_horizon_uses_bound_price_after_authoritative_batch_complete():
    p = pub()
    b = binding()
    db = DB({
        "fair_value_shadow_anchor_publications_v1": [p],
        "fair_value_shadow_evaluation_outcomes_v1": [h0()],
        "fair_value_shadow_market_bindings_v1": [b],
        "card_variant_price_observations": [obs("2026-10-03", 105)],
        "pokemon_scrape_batches": [batch("2026-10-03")],
    })
    result = forward.collect(
        db=db,
        ledger=ledger_mod.InMemoryShadowLedger(),
        today=date(2026, 10, 3),
        dry_run=True,
    )
    assert result["outcome_statuses"] == {"WOULD_INSERT_COMPLETE": 1}
    assert result["outcome_failures"] == []


def test_market_missing_is_only_recorded_after_authoritative_batch_complete():
    p = pub()
    b = binding()
    db = DB({
        "fair_value_shadow_anchor_publications_v1": [p],
        "fair_value_shadow_evaluation_outcomes_v1": [h0()],
        "fair_value_shadow_market_bindings_v1": [b],
        "card_variant_price_observations": [],
        "pokemon_scrape_batches": [batch("2026-10-03")],
    })
    result = forward.collect(
        db=db,
        ledger=ledger_mod.InMemoryShadowLedger(),
        today=date(2026, 10, 3),
        dry_run=True,
    )
    assert result["outcome_statuses"] == {"WOULD_INSERT_MARKET_MISSING": 1}
    assert result["outcome_failures"] == []


def test_bound_price_batching_scales_by_chunks_not_outcomes():
    due = []
    observations = []
    for i in range(101):
        variant = f"variant-{i:03d}"
        condition = f"condition-{i:03d}"
        binding_row = {
            "card_variant_id": variant,
            "condition_id": condition,
            "price_source": "TCGPlayer",
        }
        due.append((binding_row, date(2026, 10, 3)))
        observations.append({
            "card_variant_id": variant,
            "condition_id": condition,
            "market_price": 10 + i,
            "captured_at": "2026-10-03",
            "source": "TCGPlayer",
            "currency": "USD",
        })
    db = DB({"card_variant_price_observations": observations})
    prices, ambiguous, requests = forward.fetch_bound_prices_batch(db, due, chunk_size=50)
    assert len(prices) == 101
    assert not ambiguous
    assert requests == 3
    assert db.executions.count("card_variant_price_observations") == 3


def test_collect_uses_batched_bound_price_reads_for_due_outcomes():
    pubs = []
    h0s = []
    bindings = []
    observations = []
    for i in range(3):
        pid = f"00000000-0000-0000-0000-{i+1:012d}"
        cid = f"10000000-0000-0000-0000-{i+1:012d}"
        variant = f"20000000-0000-0000-0000-{i+1:012d}"
        condition = f"30000000-0000-0000-0000-{i+1:012d}"
        pubs.append({
            "publication_id": pid,
            "canonical_card_id": cid,
            "card_variant_id": variant,
            "evaluation_date": "2026-10-02",
            "median": "110.0",
            "status": "ANCHORED",
            "evidence_status": "PROSPECTIVE_AS_KNOWN_AT_CUTOFF",
        })
        h0s.append({
            "publication_id": pid,
            "horizon_days": 0,
            "comparison_date": "2026-10-02",
            "comparison_market_price_usd": 100.0,
            "comparison_price_source": "TCGPlayer",
            "outcome_status": "COMPLETE",
        })
        bindings.append({
            "publication_id": pid,
            "schema_version": forward.BINDING_SCHEMA_VERSION,
            "canonical_card_id": cid,
            "card_variant_id": variant,
            "condition_id": condition,
            "baseline_date": "2026-10-02",
            "baseline_market_price_usd": 100.0,
            "price_source": "TCGPlayer",
            "currency": "USD",
            "binding_method": forward.BINDING_METHOD,
        })
        observations.append({
            "card_variant_id": variant,
            "condition_id": condition,
            "market_price": 105.0 + i,
            "captured_at": "2026-10-03",
            "source": "TCGPlayer",
            "currency": "USD",
        })
    db = DB({
        "fair_value_shadow_anchor_publications_v1": pubs,
        "fair_value_shadow_evaluation_outcomes_v1": h0s,
        "fair_value_shadow_market_bindings_v1": bindings,
        "card_variant_price_observations": observations,
        "pokemon_scrape_batches": [batch("2026-10-03")],
    })
    result = forward.collect(
        db=db,
        ledger=ledger_mod.InMemoryShadowLedger(),
        today=date(2026, 10, 3),
        dry_run=True,
    )
    assert result["outcome_statuses"] == {"WOULD_INSERT_COMPLETE": 3}
    assert result["bound_price_select_requests"] == 1
