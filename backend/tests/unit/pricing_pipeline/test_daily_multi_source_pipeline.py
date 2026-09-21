import json
import os
import re
import subprocess
import urllib.parse
from datetime import date
from pathlib import Path

import pytest

from backend.pricing_pipeline import builder, collector, estimates, evidence, health, targets
from backend.pricing_pipeline.budget import DbBudgetLedger, SqliteBudgetLedger
from backend.pricing_pipeline.contracts import (
    DAILY_REQUEST_LIMIT, NM_CONDITION_ID, PipelineError, STAGES, assert_policy_contract, phoenix_day,
)
from backend.pricing_pipeline.locking import AlreadyRunning, SingleInstance
from backend.pricing_pipeline.orchestrator import Orchestrator
from backend.pricing_pipeline.store import MemoryStore
from backend.pricing_pipeline.variants import resolve_default_variants
from backend.scripts import pokemon_multi_source_card_price_v1 as policy
from backend.scripts.index_fair_value_ebay_evidence_collector import BudgetExhausted, RequestOutcome

ROOT = Path(__file__).resolve().parents[4]
MD = "2026-09-20"
MIGRATIONS = ["20260921000000_p6_pipeline_runs_and_browse_budget_ledger.sql",
              "20260921010000_p5b_multi_source_card_prices_shadow_v1.sql",
              "20260921020000_p6_restrict_ebay_estimate_privileges.sql"]


# ----------------------------------------------------------------------------------------- fixtures / fakes
@pytest.fixture(autouse=True)
def matcher_high_confidence(monkeypatch):
    monkeypatch.setattr("backend.scripts.ebay_d3_matcher_v5.classify_listing", lambda *_: {"identity_state": "HIGH_CONFIDENCE", "reason": "test"})


def cid(n):
    return f"00000000-0000-0000-0000-{n:012d}"


def make_world(store, *, priced=6, missing=3, fresh=True, price_base=30.0):
    cards, prices, links, legacy, variants = [], [], [], [], []
    for i in range(priced + missing):
        card = {"id": cid(i), "set_id": "s1", "name": f"Card{i}", "number": str(i), "printed_number": str(i), "rarity": "Rare Holo",
                "catalog_role": "main", "opening_eligible": True, "set_value_eligible": True, "canonical_review_status": "approved",
                "pokemon_tcg_api_card_id": f"api-{i}"}
        cards.append(card)
        legacy.append({"id": cid(1000 + i), "set_id": "s1", "name": f"Card{i}", "card_number": str(i), "pokemon_tcg_api_id": f"api-{i}"})
        variants.append({"id": cid(2000 + i), "card_id": cid(1000 + i), "printing_type": "holo", "special_type": None, "pokemon_tcg_api_id": None})
        if i < priced:
            prices.append({"canonical_card_id": cid(i), "card_variant_id": cid(2000 + i), "market_price": price_base + i,
                           "captured_at": MD if fresh else "2026-08-01", "source": "TCGPlayer"})
    store.catalog = (cards, [{"id": "s1", "name": "Set One", "era_id": "e1"}], [{"id": "e1", "name": "Modern", "sort_order": 1}], prices)
    store.identity_inputs = {"links": links, "cards": legacy, "variants": variants}
    store.batches[MD] = "complete"


class FakeLedger:
    def __init__(self, limit=1000, used=0):
        self.limit, self.count = limit, used
        self.reserved = 0

    def reserve(self, market_date=None):
        if self.count >= self.limit:
            raise BudgetExhausted("exhausted")
        self.count += 1
        self.reserved += 1

    def remaining(self):
        return self.limit - self.count


class FakeHttp:
    """Serves 8 distinct-seller English NM listings per card; increments counters like BrowseHTTP."""

    def __init__(self, ledger, sellers=8, fail_after=None, base=lambda name: 10.0):
        self.ledger, self.sellers, self.fail_after, self.base = ledger, sellers, fail_after, base
        self.calls = []

    def get(self, url, counters):
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise RuntimeError("simulated crash")
        if counters.remaining_run_budget <= 0:
            raise BudgetExhausted("run budget")
        self.ledger.reserve()
        counters.requests_attempted += 1
        counters.remaining_run_budget -= 1
        counters.requests_successful += 1
        self.calls.append(url)
        if "item_summary/search" in url:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"][0]
            name = re.search(r"Card\d+", q).group(0)
            items = [{"itemId": f"v1|{name}|{i}", "title": f"{name} Pokemon", "seller": {"username": f"{name}-s{i}"},
                     "price": {"value": f"{self.base(name) + i:.2f}", "currency": "USD"}, "buyingOptions": ["FIXED_PRICE"],
                     "shippingOptions": [{"shippingCost": {"value": "1.00", "currency": "USD"}}]} for i in range(self.sellers)]
            return RequestOutcome(ok=True, data={"itemSummaries": items})
        item_id = urllib.parse.unquote(url.rsplit("/", 1)[1])
        name, i = item_id.split("|")[1], int(item_id.split("|")[2])
        detail = {"itemId": item_id, "title": f"{name} Pokemon", "seller": {"username": f"{name}-s{i}"}, "condition": "Ungraded",
                  "price": {"value": f"{self.base(name) + i:.2f}", "currency": "USD"}, "buyingOptions": ["FIXED_PRICE"],
                  "shippingOptions": [{"shippingCost": {"value": "1.00", "currency": "USD"}}],
                  "localizedAspects": [{"name": "Language", "value": "English"}],
                  "conditionDescriptors": [{"name": "Card Condition", "values": [{"content": "Near mint or better"}]}],
                  "itemWebUrl": f"https://www.ebay.com/itm/{i}", "image": {"imageUrl": "https://i.ebayimg.com/x.jpg"}}
        return RequestOutcome(ok=True, data=detail)


def orchestrator(tmp_path, store, ledger=None, http=None, **kw):
    ledger = ledger or FakeLedger()
    http = http or FakeHttp(ledger)
    return Orchestrator(store, ledger, tmp_path, http_factory=lambda led: http, **kw), ledger, http


# ----------------------------------------------------------------------------------------------- 1. schema
def test_migrations_are_mirrored_and_shadow_only():
    for name in MIGRATIONS:
        a, b = ROOT / "backend/db/migrations" / name, ROOT / "supabase/migrations" / name
        assert a.read_bytes() == b.read_bytes(), name
        sql = re.sub(r"--.*", "", a.read_text(encoding="utf-8")).lower()
        for forbidden in ("card_variant_price_observations", "card_variant_price_events_v2", "card_variant_price_current_v2",
                          "pokemon_canonical_card_market_prices_latest", "create view", "create or replace view"):
            assert forbidden not in sql, (name, forbidden)


def test_run_table_stage_contract_matches_code():
    sql = (ROOT / "backend/db/migrations" / MIGRATIONS[0]).read_text(encoding="utf-8")
    assert set(re.findall(r"'([A-Z_]+)'", sql.split("stage text not null check (stage in (")[1].split("))")[0])) == set(STAGES)


def test_p4c_privilege_migration_is_select_insert_only():
    sql = re.sub(r"--.*", "", (ROOT / "backend/db/migrations" / MIGRATIONS[2]).read_text(encoding="utf-8")).lower()
    assert "revoke all on public.ebay_active_ask_price_estimates_v1 from public, anon, authenticated, service_role" in sql
    assert "grant select, insert on public.ebay_active_ask_price_estimates_v1 to service_role" in sql
    assert not re.search(r"grant[^;]*(update|delete|truncate)", sql)


def test_shadow_table_matches_frozen_policy_states():
    sql = (ROOT / "backend/db/migrations" / MIGRATIONS[1]).read_text(encoding="utf-8")
    assert all(f"'{s}'" in sql for s in policy.DECISION_STATES)
    assert "blended" not in sql.lower() and "pipeline_run_id" in sql and "ebay_estimate_id" in sql


@pytest.mark.skipif(not os.environ.get("PGLITE_PACKAGE"), reason="PGLITE_PACKAGE not set")
def test_disposable_postgres_integration():
    result = subprocess.run(["node", "backend/tests/integration/p6_disposable_postgres.mjs"], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr[-2000:]


# ----------------------------------------------------------------------------------------- 2. budget authority
def test_sqlite_budget_persists_across_processes_and_never_exceeds_cap(tmp_path):
    day = date(2026, 9, 20)
    first = SqliteBudgetLedger(tmp_path / "b.sqlite3", day=day, limit=1000)
    for _ in range(400):
        first.reserve()
    second = SqliteBudgetLedger(tmp_path / "b.sqlite3", day=day, limit=1000)  # "restarted process"
    assert second.used() == 400 and second.remaining() == 600
    for _ in range(600):
        second.reserve()
    with pytest.raises(BudgetExhausted):
        second.reserve()
    assert SqliteBudgetLedger(tmp_path / "b.sqlite3", day=day, limit=5000).limit == DAILY_REQUEST_LIMIT
    assert SqliteBudgetLedger(tmp_path / "b.sqlite3", day=date(2026, 9, 21)).used() == 0  # next Phoenix day


class RpcClient:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def rpc(self, name, params):
        self.calls.append((name, params))
        outer = self

        class Q:
            def execute(self):
                if outer.error:
                    raise Exception(outer.error)
        return Q()


def test_db_budget_ledger_reserves_through_rpc_and_fails_closed():
    client = RpcClient()
    DbBudgetLedger(client, day=date(2026, 9, 20)).reserve()
    assert client.calls == [("reserve_ebay_browse_request_v1", {"p_day": "2026-09-20", "p_limit": 1000})]
    with pytest.raises(BudgetExhausted):
        DbBudgetLedger(RpcClient("EBAY_BROWSE_BUDGET_EXHAUSTED"), day=date(2026, 9, 20)).reserve()
    with pytest.raises(PipelineError) as exc:
        DbBudgetLedger(RpcClient("connection refused"), day=date(2026, 9, 20)).reserve()
    assert exc.value.code == "BUDGET_AUTHORITY_UNAVAILABLE"


def test_phoenix_day_boundary_is_utc_minus_seven():
    from datetime import datetime, timezone
    assert phoenix_day(datetime(2026, 9, 21, 6, 59, tzinfo=timezone.utc)) == date(2026, 9, 20)
    assert phoenix_day(datetime(2026, 9, 21, 7, 0, tzinfo=timezone.utc)) == date(2026, 9, 21)


# ----------------------------------------------------------------------------------------- 3. targets
def test_selector_is_deterministic_prioritized_and_budget_bound():
    store = MemoryStore()
    make_world(store, priced=20, missing=6)
    cards, sets, eras, prices = store.catalog
    from backend.scripts import p5b_cohort_builder as cb
    universe = cb.build_universe(cards, sets, eras, prices, date(2026, 9, 20))
    resolved = resolve_default_variants([c for c in cards if c["id"] not in {p["canonical_card_id"] for p in prices}], store.identity_inputs)
    a = targets.plan_targets(universe, date(2026, 9, 20), remaining_requests=140, cost_per_target=7.0, resolved_variants=resolved)
    b = targets.plan_targets(universe, date(2026, 9, 20), remaining_requests=140, cost_per_target=7.0, resolved_variants=resolved)
    assert a == b and targets.verify_manifest(a) and a["target_count"] == a["planned_capacity"] == 18
    assert a["cards"][0]["priority_tier"] == 1 and {c["tcg_status"] for c in a["cards"] if c["priority_tier"] == 1} == {"missing"}
    assert a["target_count"] * a["cost_per_target"] <= 140
    assert targets.plan_capacity(5000, 7.0) == 128  # never plans beyond the 1000/day cap


def test_unresolvable_missing_promos_are_never_targeted():
    store = MemoryStore()
    make_world(store, priced=2, missing=2)
    store.identity_inputs = {"links": [], "cards": [], "variants": []}  # nothing resolves
    cards, sets, eras, prices = store.catalog
    from backend.scripts import p5b_cohort_builder as cb
    universe = cb.build_universe(cards, sets, eras, prices, date(2026, 9, 20))
    resolved = resolve_default_variants(cards[2:], store.identity_inputs)
    manifest = targets.plan_targets(universe, date(2026, 9, 20), remaining_requests=700, cost_per_target=7.0, resolved_variants=resolved)
    assert all(c["tcg_status"] != "missing" for c in manifest["cards"])


def test_measured_cost_model_uses_history():
    assert targets.measured_requests_per_target([]) == 7.0
    assert targets.measured_requests_per_target([{"requests_attempted": 300, "target_count": 50}, {"requests_attempted": 500, "target_count": 50}]) == 8.0


# ---------------------------------------------------------------------------------------- 4. end-to-end state machine
def test_full_run_completes_and_publishes_shadow_rows(tmp_path):
    store = MemoryStore()
    make_world(store, priced=6, missing=3)
    orch, ledger, http = orchestrator(tmp_path, store)
    receipt = orch.run(date(2026, 9, 20))
    run = store.get_run(MD)
    assert run["status"] == "COMPLETE" and run["stage"] == "COMPLETE" and run["finished_at"]
    assert receipt["policy_version"] == "pokemon_multi_source_card_price_v1" and receipt["target_count"] == 9
    assert ledger.reserved == len(http.calls) == receipt["requests_attempted"] <= 1000
    counts = receipt["multi_source"]["decision_counts"]
    assert counts["EBAY_ACTIVE_ASK_FALLBACK"] == 3 and sum(counts.values()) == 9 == len(store.shadow)
    assert receipt["estimates"]["depth_counts"]["SUFFICIENT"] == 9
    assert (tmp_path / MD / "receipt.json").exists()
    assert all(r["policy_version"] == policy.POLICY_VERSION for r in store.shadow.values())


def test_fresh_tcg_stays_primary_and_ebay_only_corroborates_or_flags(tmp_path):
    store = MemoryStore()
    make_world(store, priced=4, missing=0, price_base=10.0)
    orch, _, _ = orchestrator(tmp_path, store, http=None)
    orch.run(date(2026, 9, 20))
    for row in store.shadow.values():
        assert row["selected_price_source"] == "TCGPLAYER" and row["selected_price"] == row["tcgplayer_price"]
        assert row["decision_state"].startswith("TCGPLAYER_PRIMARY")


def test_stale_tcg_is_retained_never_replaced(tmp_path):
    store = MemoryStore()
    make_world(store, priced=4, missing=0, fresh=False, price_base=10.0)
    orch, _, _ = orchestrator(tmp_path, store)
    orch.run(date(2026, 9, 20))
    assert {r["decision_state"] for r in store.shadow.values()} == {"TCGPLAYER_STALE_RETAINED"}
    assert all(r["selected_price_source"] == "TCGPLAYER" for r in store.shadow.values())


def test_thin_ebay_never_fills_a_missing_price_and_no_blend(tmp_path):
    store = MemoryStore()
    make_world(store, priced=2, missing=3)
    ledger = FakeLedger()
    orch, _, _ = orchestrator(tmp_path, store, ledger=ledger, http=FakeHttp(ledger, sellers=4))
    orch.run(date(2026, 9, 20))
    missing = [r for r in store.shadow.values() if r["tcgplayer_freshness_state"] == "MISSING"]
    assert missing and all(r["decision_state"] == "UNPRICED" and r["selected_price"] is None and r["ebay_depth_state"] == "THIN" for r in missing)
    assert store.estimates == {}  # THIN never gets a numeric estimate row
    for r in store.shadow.values():
        assert r["selected_price_source"] in (None, "TCGPLAYER") and r["selected_price"] in (None, r["tcgplayer_price"])


def test_todays_depth_is_persisted_without_carry_forward(tmp_path):
    store = MemoryStore()
    make_world(store, priced=0, missing=3)
    ledger = FakeLedger()
    o1 = Orchestrator(store, ledger, tmp_path, http_factory=lambda l: FakeHttp(ledger, sellers=8))
    o1.run(date(2026, 9, 20))
    assert {r["decision_state"] for r in store.shadow.values()} == {"EBAY_ACTIVE_ASK_FALLBACK"}
    store.batches["2026-09-21"] = "complete"
    o2 = Orchestrator(store, FakeLedger(), tmp_path, http_factory=lambda l: FakeHttp(l, sellers=4))  # fragile 5-seller supply flickers to THIN
    o2.run(date(2026, 9, 21))
    day2 = [r for r in store.shadow.values() if r["market_date"] == "2026-09-21"]
    assert day2 and {r["decision_state"] for r in day2} == {"UNPRICED"} and {r["ebay_depth_state"] for r in day2} == {"THIN"}
    assert all(r["market_date"] == "2026-09-21" or r["decision_state"] == "EBAY_ACTIVE_ASK_FALLBACK" for r in store.shadow.values())


# ---------------------------------------------------------------------------------------- 5. resume / crash / idempotency
def test_crash_mid_collection_resumes_without_repeating_work_or_resetting_budget(tmp_path):
    store = MemoryStore()
    make_world(store, priced=6, missing=3)
    ledger = FakeLedger()
    crashing = FakeHttp(ledger, fail_after=40)
    orch1 = Orchestrator(store, ledger, tmp_path, http_factory=lambda l: crashing)
    with pytest.raises(RuntimeError):
        orch1.run(date(2026, 9, 20))
    spent_before = ledger.count
    assert store.get_run(MD)["status"] == "FAILED" and store.get_run(MD)["failure_code"] == "UNEXPECTED_ERROR"
    assert store.get_run(MD)["stage"] == "COLLECTION_RUNNING" and spent_before == 40  # counter survived the crash
    done_before = set(collector.CollectionCheckpoint(tmp_path / MD).completed())
    resumed = FakeHttp(ledger)
    orch2 = Orchestrator(store, ledger, tmp_path, http_factory=lambda l: resumed)
    receipt = orch2.run(date(2026, 9, 20))
    assert store.get_run(MD)["status"] == "COMPLETE" and receipt["target_count"] == 9
    touched = {re.search(r"Card\d+", urllib.parse.unquote(u)).group(0) for u in resumed.calls}
    assert not touched & {f"Card{int(cid_[-4:], 10)}" for cid_ in done_before}  # no completed target was re-fetched
    assert ledger.count <= 1000 and ledger.count == spent_before + len(resumed.calls)


def test_completed_market_date_replay_makes_no_calls_and_no_writes(tmp_path):
    store = MemoryStore()
    make_world(store, priced=5, missing=2)
    orch, ledger, http = orchestrator(tmp_path, store)
    first = orch.run(date(2026, 9, 20))
    snapshot = ({k: dict(v) for k, v in store.shadow.items()}, dict(store.estimates), len(store.evidence), len(store.writes), len(http.calls))
    second = orch.run(date(2026, 9, 20))
    assert second["idempotent_replay"] is True and second["receipt_fingerprint"] == first["receipt_fingerprint"]
    assert (dict(store.estimates), len(store.evidence), len(store.writes), len(http.calls)) == snapshot[1:]
    assert {k: dict(v) for k, v in store.shadow.items()} == snapshot[0]


def test_resume_from_each_incomplete_stage_is_idempotent(tmp_path):
    for stop_stage in ("COLLECTION_COMPLETE", "EVIDENCE_PERSISTED", "ESTIMATES_BUILT", "MULTI_SOURCE_BUILT"):
        store = MemoryStore()
        make_world(store, priced=5, missing=2)
        ledger = FakeLedger()
        base_dir = tmp_path / stop_stage
        orch = Orchestrator(store, ledger, base_dir, http_factory=lambda l: FakeHttp(l))
        orch.run(date(2026, 9, 20))
        reference = {k: v["decision_fingerprint"] for k, v in store.shadow.items()}
        run = store.get_run(MD)
        # rewind the state machine to a mid-pipeline stage to simulate a crash right after `stop_stage` started work
        store.update_run(run["run_id"], {"stage": stop_stage, "status": "FAILED", "finished_at": None, "receipt": None})
        calls_before, used_before = ledger.count, len(store.writes)
        Orchestrator(store, ledger, base_dir, http_factory=lambda l: FakeHttp(l)).run(date(2026, 9, 20))
        assert ledger.count == calls_before  # completed network work is never repeated
        assert {k: v["decision_fingerprint"] for k, v in store.shadow.items()} == reference and len(store.shadow) == len(reference)
        assert store.get_run(MD)["status"] == "COMPLETE"


def test_evidence_persistence_is_idempotent_and_changed_replay_fails_closed(tmp_path):
    store = MemoryStore()
    make_world(store, priced=3, missing=1)
    orch, _, _ = orchestrator(tmp_path, store)
    orch.run(date(2026, 9, 20))
    run = store.get_run(MD)
    manifest = run["manifest"]
    prepared = orch._prepare_evidence(run, manifest, MD)
    again = evidence.persist(store, prepared)
    assert again["replayed"] is True and len(store.evidence) == len(prepared["evidence"])
    tampered = dict(prepared, run=dict(prepared["run"], run_fingerprint="0" * 64))
    with pytest.raises(PipelineError) as exc:
        evidence.persist(store, tampered)
    assert exc.value.code == "EVIDENCE_RUN_CONTRACT_CHANGED"


def test_estimates_are_deterministic_reproducible_and_append_only(tmp_path):
    store = MemoryStore()
    make_world(store, priced=3, missing=0)
    orch, _, _ = orchestrator(tmp_path, store)
    orch.run(date(2026, 9, 20))
    run = store.get_run(MD)
    ev, sm = store.get_evidence(run["ebay_pricing_run_id"]), store.get_summaries(run["ebay_pricing_run_id"])
    a = estimates.build(ev, sm, run["manifest"], pricing_run_id=run["ebay_pricing_run_id"], market_date=MD, evidence_digest="a" * 64)
    b = estimates.build(ev, sm, run["manifest"], pricing_run_id=run["ebay_pricing_run_id"], market_date=MD, evidence_digest="a" * 64)
    assert a == b and all(estimates.verify_replay(r, ev) for r in a["rows"])
    row = a["rows"][0]
    assert len(row["contributing_evidence"]) >= 5 and all(c["evidence_row_id"] for c in row["contributing_evidence"])
    assert row["estimator_version"] == "ebay_active_ask_lower3_seller_median_v1" and row["estimated_price"] == row["selected_ask_2"]
    with pytest.raises(PipelineError):
        store.insert_estimates([dict(row, estimator_fingerprint="9" * 64)])
    assert store.insert_estimates([row]) == (0, 1)


def test_shadow_publication_conflicting_replay_fails_closed(tmp_path):
    store = MemoryStore()
    make_world(store, priced=2, missing=1)
    orch, _, _ = orchestrator(tmp_path, store)
    orch.run(date(2026, 9, 20))
    row = next(iter(store.shadow.values()))
    assert store.insert_shadow_rows([dict(row)]) == (0, 1)
    with pytest.raises(PipelineError) as exc:
        store.insert_shadow_rows([dict(row, decision_fingerprint="f" * 64)])
    assert exc.value.code == "SHADOW_ROW_CONFLICT"


# ----------------------------------------------------------------------------------------- 6. fail-closed gates
def test_missing_migration_stops_before_any_work(tmp_path):
    store = MemoryStore()
    make_world(store)
    store.schema_ok = False
    orch, ledger, http = orchestrator(tmp_path, store)
    with pytest.raises(PipelineError) as exc:
        orch.run(date(2026, 9, 20))
    assert exc.value.code == "MIGRATION_MISSING" and not http.calls and not store.runs


def test_waits_for_tcg_batch_and_makes_no_ebay_calls(tmp_path):
    store = MemoryStore()
    make_world(store)
    store.batches.clear()
    orch, ledger, http = orchestrator(tmp_path, store)
    with pytest.raises(PipelineError) as exc:
        orch.run(date(2026, 9, 20))
    assert exc.value.code == "TCG_BATCH_NOT_COMPLETE" and exc.value.status == "WAITING"
    assert store.get_run(MD)["status"] == "WAITING" and not http.calls
    store.batches[MD] = "complete"  # the batch lands; the next invocation resumes the same run
    orch.run(date(2026, 9, 20))
    assert store.get_run(MD)["status"] == "COMPLETE"


def test_budget_exhausted_blocks_collection(tmp_path):
    store = MemoryStore()
    make_world(store)
    orch, ledger, http = orchestrator(tmp_path, store, ledger=FakeLedger(limit=1000, used=1000))
    with pytest.raises(PipelineError) as exc:
        orch.run(date(2026, 9, 20))
    assert exc.value.code == "BUDGET_EXHAUSTED" and not http.calls


def test_partial_budget_run_never_exceeds_remaining_requests(tmp_path):
    store = MemoryStore()
    make_world(store, priced=10, missing=5)
    ledger = FakeLedger(limit=1000, used=900)  # only 100 requests remain today
    orch, _, http = orchestrator(tmp_path, store, ledger=ledger)
    receipt = orch.run(date(2026, 9, 20))
    assert ledger.count <= 1000 and len(http.calls) <= 100 and receipt["target_count"] <= 12


def test_tampered_manifest_fails_closed(tmp_path):
    store = MemoryStore()
    make_world(store)
    orch, _, http = orchestrator(tmp_path, store)
    run = store.create_run({"run_id": "r1", "market_date": MD, "policy_version": policy.POLICY_VERSION, "pipeline_version": "x",
                            "status": "RUNNING", "stage": "INIT", "request_cap": 1000, "started_at": "2026-09-20T00:00:00+00:00"})
    orch._init(run, MD)
    run["manifest"]["cards"][0]["tcgplayer_market_price"] = 1.0
    with pytest.raises(PipelineError) as exc:
        orch._verify_manifest(run)
    assert exc.value.code == "TARGET_FINGERPRINT_MISMATCH"


def test_collector_partial_beyond_policy_stops_before_persistence(tmp_path):
    store = MemoryStore()
    make_world(store, priced=10, missing=0)
    ledger = FakeLedger(limit=1000, used=985)  # 15 requests: far fewer than the manifest needs
    orch = Orchestrator(store, ledger, tmp_path, http_factory=lambda l: FakeHttp(l), max_requests=1000)
    real_plan = targets.plan_capacity
    try:
        targets.plan_capacity = lambda *a, **k: 10
        with pytest.raises(PipelineError) as exc:
            orch.run(date(2026, 9, 20))
    finally:
        targets.plan_capacity = real_plan
    assert exc.value.code == "COLLECTOR_PARTIAL_BEYOND_POLICY" and store.get_run(MD)["status"] == "PARTIAL"
    assert not store.evidence and not store.estimates and not store.shadow


def test_estimator_or_policy_drift_is_detected(monkeypatch):
    assert_policy_contract()
    monkeypatch.setattr("backend.pricing_pipeline.contracts.POLICY_FINGERPRINT", "0" * 64)
    with pytest.raises(PipelineError) as exc:
        assert_policy_contract()
    assert exc.value.code == "POLICY_FINGERPRINT_DRIFT"


def test_non_tcg_source_in_current_pricing_blocks_validation(tmp_path):
    store = MemoryStore()
    make_world(store, priced=4, missing=0)
    store.non_tcg_current = 1
    orch, _, _ = orchestrator(tmp_path, store)
    with pytest.raises(PipelineError) as exc:
        orch.run(date(2026, 9, 20))
    assert exc.value.code == "SOURCE_LOCK_AUTHORITY_MISMATCH" and store.get_run(MD)["stage"] == "MULTI_SOURCE_BUILT"


# ------------------------------------------------------------------- 7. canonical / provider tables untouched
def test_pipeline_never_writes_provider_or_canonical_tables():
    banned = ("card_variant_price_observations", "card_variant_price_events_v2", "card_variant_price_current_v2",
              "pokemon_canonical_card_market_prices_latest", "pokemon_set_value", "simulation")
    for path in (ROOT / "backend/pricing_pipeline").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"\.table\(\"([a-z0-9_]+)\"\)([^\n]*)", text):
            table, rest = m.group(1), m.group(2)
            if any(b in table for b in banned):
                assert not re.search(r"\.(insert|upsert|update|delete)\(", rest), (path.name, table)


def test_memory_store_tracks_only_pipeline_owned_writes(tmp_path):
    store = MemoryStore()
    make_world(store)
    orchestrator(tmp_path, store)[0].run(date(2026, 9, 20))
    assert set(store.writes) <= {"create_run", "update_run", "upsert_pricing_run", "insert_evidence", "upsert_summaries",
                                 "insert_estimates", "insert_shadow_rows"}
    assert store.catalog[3][0]["source"] == "TCGPlayer"  # canonical price authority object was never replaced


# ----------------------------------------------------------------------------------- 8. locking / scheduler / health
def test_single_instance_lock_blocks_a_second_run(tmp_path):
    lock = tmp_path / "daily.lock"
    with SingleInstance(lock):
        with pytest.raises(AlreadyRunning):
            with SingleInstance(lock):
                pass
    with SingleInstance(lock):  # released after exit
        pass


def test_cron_entry_uses_phoenix_tz_flock_and_no_pg_cron():
    text = (ROOT / "infra/oracle/multi-source-pricing.crontab").read_text(encoding="utf-8")
    assert "CRON_TZ=America/Phoenix" in text and "flock -n" in text and "run_daily_multi_source_card_pricing" in text
    active = " ".join(l for l in text.splitlines() if not l.lstrip().startswith("#")).lower()
    assert "pg_cron" not in active and "cron.schedule" not in active
    assert re.search(r"^\d+ \d+ \* \* \* ", text, re.M)
    assert "--json" in text and ">>" in text  # durable log


def _snapshot(**over):
    from datetime import datetime, timezone
    base = {"now": datetime(2026, 9, 21, 16, 0, tzinfo=timezone.utc),  # 09:00 Phoenix on the 21st
            "run": {"market_date": "2026-09-21", "status": "COMPLETE", "stage": "COMPLETE", "failure_code": None, "target_fingerprint": "a" * 64},
            "evidence": {"market_date": "2026-09-21", "status": "COMPLETE", "finished_at": "2026-09-21T11:30:00+00:00"},
            "estimate": {"market_date": "2026-09-21", "estimator_version": "ebay_active_ask_lower3_seller_median_v1"},
            "shadow": {"market_date": "2026-09-21", "policy_version": policy.POLICY_VERSION},
            "ledger": {"requests_reserved": 700, "daily_limit": 1000}, "shadow_policies": [policy.POLICY_VERSION],
            "non_tcg_current": 0, "non_tcg_canonical": 0}
    base.update(over)
    return base


def test_health_all_green():
    results = health.assess(_snapshot())
    assert {r["status"] for r in results} == {"ok"} and health.overall(results)["multi_source_coverage"] == "healthy"


def test_ebay_failure_degrades_multi_source_not_canonical_pricing():
    results = health.assess(_snapshot(run={"market_date": "2026-09-19", "status": "FAILED", "stage": "COLLECTION_RUNNING",
                                           "failure_code": "BUDGET_EXHAUSTED", "target_fingerprint": "a" * 64}, evidence=None, estimate=None, shadow=None))
    summary = health.overall(results)
    assert summary["canonical_pricing_healthy"] is True and summary["multi_source_coverage"] == "degraded"
    assert not summary["critical_checks"] and "pricing.multi_source.run_freshness" in summary["degraded_checks"]
    from backend.sentinel.models import Severity
    sentinel = {r.check_key: r for r in health.sentinel_results(_snapshot(run=None, shadow=None, evidence=None, estimate=None))}
    assert all(r.severity != Severity.CRITICAL for r in sentinel.values())


def test_non_tcg_source_or_policy_drift_is_flagged():
    guard = health.overall(health.assess(_snapshot(non_tcg_current=1)))
    assert guard["canonical_pricing_healthy"] is False and guard["critical_checks"] == ["pricing.canonical.source_guard"]
    drift = health.assess(_snapshot(shadow_policies=["some_other_policy"]))
    assert next(r for r in drift if r["check"] == "pricing.multi_source.policy_drift")["status"] != "ok"


def test_health_expected_date_uses_phoenix_deadline():
    from datetime import datetime, timezone
    assert health.expected_market_date(datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)) == date(2026, 9, 20)  # 03:00 Phoenix: not yet due
    assert health.expected_market_date(datetime(2026, 9, 21, 16, 0, tzinfo=timezone.utc)) == date(2026, 9, 21)  # 09:00 Phoenix: due
