from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest

from backend.scripts import index_fair_value_shadow_ledger_v1 as ledger_mod
from backend.scripts import run_index_fair_value_prospective_shadow_v1 as publisher
from backend.scripts import run_index_fair_value_sold_clearing_anchor_v1 as s2


class Result:
    def __init__(self, data=None, count=None):
        self.data = data or []
        self.count = len(self.data) if count is None else count


class Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.filters = []

    def select(self, *a, **k):
        self.db.events.append(("select", self.table))
        return self

    def insert(self, payload):
        self.db.events.append(("insert", self.table, copy.deepcopy(payload)))
        return self

    def eq(self, key, value):
        self.filters.append(lambda r, k=key, v=value: str(r.get(k)) == str(v))
        return self

    def in_(self, key, values):
        values = {str(v) for v in values}
        self.filters.append(lambda r, k=key, v=values: str(r.get(k)) in v)
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def range(self, start, end):
        self.slice = (start, end)
        return self

    def execute(self):
        rows = [copy.deepcopy(r) for r in self.db.tables.get(self.table, []) if all(f(r) for f in self.filters)]
        if hasattr(self, "slice"):
            start, end = self.slice
            rows = rows[start:end + 1]
        return Result(rows)


class FakeDB:
    def __init__(self, tables):
        self.tables = tables
        self.events = []

    def table(self, name):
        return Query(self, name)


class RecordingLedger(ledger_mod.InMemoryShadowLedger):
    def __init__(self, events):
        super().__init__()
        self.events = events

    def append_publication(self, publication):
        self.events.append(("append_publication", publication["canonical_card_id"]))
        return super().append_publication(publication)

    def append_component(self, observation):
        self.events.append(("append_component", observation["canonical_card_id"]))
        return super().append_component(observation)

    def append_outcome(self, outcome):
        self.events.append(("append_outcome", outcome["publication_id"]))
        return super().append_outcome(outcome)


def _tables():
    panel = s2.load_panel()
    identities = []
    evidence = []
    for i, target in enumerate(panel["rows"], 1):
        cid = str(target["canonical_card_id"])
        pid = 50000 + i
        identities.append({
            "provider_card_id": pid,
            "canonical_card_id": cid,
            "language": "English",
            "tcgplayer_product_id": str(900000 + i),
        })
        for n in range(10):
            evidence.append({
                "provider_listing_id": pid * 100 + n,
                "provider_card_id": pid,
                "canonical_card_id": cid,
                "title": f'{target["card_name"]} {target["card_number"]} NM Near Mint',
                "price": str(20 + n),
                "currency": "USD",
                "grader": None,
                "grade": None,
                "graded": False,
                "provider_variant": None,
                "attribution": "exact",
                "sold_at": "2026-09-30",
                "ingested_at": "2026-10-01T12:00:00+00:00",
                "collected_at": "2026-10-01T12:00:00+00:00",
                "identity_state": "EXACT",
                "fair_value_signal_eligible": True,
                "exclusion_reason": None,
                "run_id": "00000000-0000-0000-0000-000000000001",
            })
    return {
        "pkmnprices_card_identity_v1": identities,
        "pkmnprices_ebay_sold_evidence_v1": evidence,
        "pokemon_canonical_card_market_prices_latest": [],
        "card_variant_price_observations": [],
    }


def test_prospective_publisher_appends_every_anchor_before_any_price_read():
    db = FakeDB(_tables())
    ledger = RecordingLedger(db.events)
    out = publisher.publish(
        db=db,
        ledger=ledger,
        source_commit="abc1234",
        now=datetime(2026, 10, 1, 22, 0, tzinfo=timezone.utc),
        dry_run=False,
    )
    price_tables = {"pokemon_canonical_card_market_prices_latest", "card_variant_price_observations"}
    first_price = next(i for i, event in enumerate(db.events) if event[0] == "select" and event[1] in price_tables)
    publication_positions = [i for i, event in enumerate(db.events) if event[0] == "append_publication"]
    assert len(publication_positions) == 207
    assert max(publication_positions) < first_price
    assert out["panel_count"] == 207
    assert out["provider_calls"] == 0 and out["provider_credits_used"] == 0
    assert out["public_price_writes"] == 0 and out["blended_values_produced"] == 0


class RpcQuery:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return Result(self.result)


class AdapterDB:
    def __init__(self):
        self.rpc_calls = []
        self.tables = {}
        self.inserted = []

    def rpc(self, name, params):
        self.rpc_calls.append((name, copy.deepcopy(params)))
        return RpcQuery(["INSERTED"])

    def table(self, name):
        db = self

        class Q:
            def __init__(self):
                self.filters = []

            def select(self, *a, **k):
                return self

            def eq(self, key, value):
                self.filters.append((key, value))
                return self

            def limit(self, *a, **k):
                return self

            def insert(self, payload):
                db.inserted.append((name, copy.deepcopy(payload)))
                return self

            def execute(self):
                rows = db.tables.get(name, [])
                for key, value in self.filters:
                    rows = [r for r in rows if str(r.get(key)) == str(value)]
                return Result(copy.deepcopy(rows))
        return Q()


def test_supabase_adapter_uses_atomic_publication_rpc(monkeypatch):
    monkeypatch.setattr(ledger_mod, "WRITE_ENABLED", True)
    db = AdapterDB()
    adapter = ledger_mod.SupabaseShadowLedger(db)
    publication = {
        "publication_id": "00000000-0000-0000-0000-000000000001",
        "rule_version": "r",
        "canonical_card_id": "00000000-0000-0000-0000-000000000002",
        "evaluation_date": "2026-10-01",
        "information_cutoff": "2026-10-02T00:00:00+00:00",
        "content_fingerprint": "a" * 64,
        "members": [{"provider_card_id": 1, "provider_listing_id": 2}],
    }
    assert adapter.append_publication(publication) == "INSERTED"
    assert len(db.rpc_calls) == 1
    name, params = db.rpc_calls[0]
    assert name == "publish_fair_value_shadow_anchor_v1"
    assert "members" not in params["p_publication"]
    assert params["p_members"] == publication["members"]
    assert not db.inserted


def test_component_and_outcome_adapter_are_idempotent_and_conflict_safe(monkeypatch):
    monkeypatch.setattr(ledger_mod, "WRITE_ENABLED", True)
    db = AdapterDB()
    adapter = ledger_mod.SupabaseShadowLedger(db)

    component = {"publication_id": "p1", "schema_version": "v", "value": 1}
    assert adapter.append_component(component) == "INSERTED"
    fp = ledger_mod._canonical_fingerprint(component)
    db.tables[adapter.COMPONENTS] = [{"publication_id": "p1", "content_fingerprint": fp}]
    assert adapter.append_component(component) == "IDEMPOTENT_NOOP"
    with pytest.raises(ledger_mod.ShadowLedgerConflict):
        adapter.append_component({**component, "value": 2})

    outcome = {"publication_id": "p1", "horizon_days": 7, "schema_version": "v", "value": 3}
    assert adapter.append_outcome(outcome) == "INSERTED"
    fp2 = ledger_mod._canonical_fingerprint(outcome)
    db.tables[adapter.OUTCOMES] = [{"publication_id": "p1", "horizon_days": 7, "content_fingerprint": fp2}]
    assert adapter.append_outcome(outcome) == "IDEMPOTENT_NOOP"
    with pytest.raises(ledger_mod.ShadowLedgerConflict):
        adapter.append_outcome({**outcome, "value": 4})


def test_fixed_cutoff_retry_ignores_post_cutoff_evidence_for_identity():
    panel = s2.load_panel()
    target = copy.deepcopy(panel["rows"][0])
    cid = str(target["canonical_card_id"])
    provider_id = 77777
    base_rows = []
    for n in range(10):
        base_rows.append({
            "provider_listing_id": 900000 + n,
            "provider_card_id": provider_id,
            "canonical_card_id": cid,
            "title": f'{target["card_name"]} {target["card_number"]} NM Near Mint',
            "price": str(50 + n),
            "currency": "USD",
            "grader": None,
            "grade": None,
            "graded": False,
            "provider_variant": None,
            "attribution": "exact",
            "sold_at": "2026-10-02",
            "ingested_at": "2026-10-02T23:30:00+00:00",
            "collected_at": "2026-10-02T23:30:00+00:00",
            "identity_state": "EXACT",
            "fair_value_signal_eligible": True,
            "exclusion_reason": None,
            "run_id": "00000000-0000-0000-0000-000000000001",
        })
    cutoff = datetime(2026, 10, 3, 1, 0, tzinfo=timezone.utc)
    p = {"panel_fingerprint": panel["panel_fingerprint"], "rows": [target]}
    first = publisher.build_publications(
        panel=p,
        provider_by_card={cid: provider_id},
        evidence_by_card={cid: base_rows},
        evaluation_date=cutoff.astimezone(publisher.PHOENIX).date(),
        information_cutoff=cutoff,
        generated_at=cutoff,
        source_commit="abc1234",
    )[0]
    later = {
        **base_rows[0],
        "provider_listing_id": 999999,
        "price": "999.99",
        "sold_at": "2026-10-02",
        "ingested_at": "2026-10-03T01:05:00+00:00",
        "collected_at": "2026-10-03T01:05:00+00:00",
    }
    retry = publisher.build_publications(
        panel=p,
        provider_by_card={cid: provider_id},
        evidence_by_card={cid: base_rows + [later]},
        evaluation_date=cutoff.astimezone(publisher.PHOENIX).date(),
        information_cutoff=cutoff,
        generated_at=cutoff,
        source_commit="abc1234",
    )[0]
    assert retry["content_fingerprint"] == first["content_fingerprint"]
    assert retry["publication_id"] == first["publication_id"]
    assert retry["rows_offered"] == first["rows_offered"] == 10
    assert retry["input_fingerprints"]["evidence_rowset"] == first["input_fingerprints"]["evidence_rowset"]


def test_information_cutoff_parser_requires_timezone_and_normalizes_utc():
    parsed = publisher.parse_information_cutoff("2026-10-02T18:00:00-07:00")
    assert parsed == datetime(2026, 10, 3, 1, 0, tzinfo=timezone.utc)
    with pytest.raises(Exception):
        publisher.parse_information_cutoff("2026-10-02T18:00:00")


def test_future_information_cutoff_refuses_before_database_access():
    class UntouchedDB:
        def table(self, name):
            raise AssertionError(f"database touched: {name}")
    with pytest.raises(publisher.ProspectiveShadowError, match="INFORMATION_CUTOFF_IN_FUTURE"):
        publisher.publish(
            db=UntouchedDB(),
            ledger=ledger_mod.InMemoryShadowLedger(),
            source_commit="abc1234",
            now=datetime(2099, 1, 1, tzinfo=timezone.utc),
            dry_run=True,
        )


def test_naive_programmatic_cutoff_is_rejected():
    with pytest.raises(publisher.ProspectiveShadowError, match="timezone-aware"):
        publisher.publish(
            db=object(),
            ledger=ledger_mod.InMemoryShadowLedger(),
            source_commit="abc1234",
            now=datetime(2026, 10, 2, 18, 0),
            dry_run=True,
        )
