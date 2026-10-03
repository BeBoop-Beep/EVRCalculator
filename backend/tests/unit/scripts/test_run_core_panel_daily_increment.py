from __future__ import annotations

import copy
import inspect
import re
from pathlib import Path
from typing import Any

import pytest

from backend.pricing_pipeline.pkmnprices_store import PkmnPricesStore
from backend.scripts import run_core_panel_daily_increment as inc

REAL_PROVIDER_DAILY_CREDIT_EXHAUSTED = inc._provider_daily_credit_exhausted_today
ROOT = Path(__file__).resolve().parents[4]
FLOOR = "2026-09-20T00:00:00+00:00"


# ------------------------------------------------------------------ fakes
class FakeProvider:
    """Scripted sold pages keyed by (provider_id, cursor). Has NO identity-lookup method."""

    credits_limit: int | None = 75000

    def __init__(self, pages: dict[tuple[int, str | None], dict[str, Any]], charge: str = "items") -> None:
        self.pages, self.calls, self.charge = pages, [], charge
        self.credits_charged = 0
        self.request_attempt_count = 0

    def ebay_sold_page(self, provider_id, **kwargs):
        self.calls.append({"provider_id": provider_id, **kwargs})
        self.request_attempt_count += 1
        payload = self.pages[(provider_id, kwargs.get("cursor"))]
        if isinstance(payload, BaseException):
            raise payload
        self.credits_charged += len(payload["data"]) if self.charge == "items" else kwargs["limit"]
        return payload


class FakeStore:
    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.evidence: dict[tuple[int, int], dict[str, Any]] = {}
        self.sync: dict[int, dict[str, Any]] = {}
        self.sync_writes = 0

    def create_run(self, row):
        self.runs[row["run_id"]] = dict(row)

    def update_run(self, run_id, fields):
        self.runs[run_id].update(fields)

    def insert_evidence(self, rows):
        inserted = skipped = 0
        for row in rows:
            key = (int(row["provider_card_id"]), int(row["provider_listing_id"]))
            if key in self.evidence:
                skipped += 1
            else:
                self.evidence[key] = dict(row)
                inserted += 1
        return inserted, skipped, 0

    def upsert_sync_state(self, row):
        self.sync_writes += 1
        self.sync[int(row["provider_card_id"])] = copy.deepcopy(row)


def _target(n: int) -> dict[str, Any]:
    return {"canonical_card_id": f"card-{n}", "card_variant_id": f"var-{n}", "tcgplayer_product_id": str(n),
            "edition": None, "printing_type": "holo"}


def _state(n: int, *, frontier: str | None = FLOOR, extra_meta: dict[str, Any] | None = None,
           complete: bool = True, identity: bool = True, ready: bool = True) -> dict[str, Any]:
    meta = {"core_panel_backfill_complete": complete, "core_panel_backfill_in_progress": False,
            "core_panel_backfill_cursor": None, "phase1_ready": ready, "panel_fingerprint": "pf",
            **(extra_meta or {})}
    if frontier:
        meta["core_panel_incremental_watermark"] = frontier
    sync = {"provider_card_id": 1000 + n, "canonical_card_id": f"card-{n}", "last_ingested_at": frontier,
            "last_sold_at": "2026-09-19", "status": "CURRENT", "rows_seen": 400, "rows_inserted": 399,
            "consecutive_failures": 0, "metadata": meta}
    return {"target": _target(n), "identity": {"provider_card_id": 1000 + n, "tcgplayer_product_id": str(n)} if identity else None,
            "sync": sync, "phase1_ready": ready, "panel_index": n}


def _raw(listing_id: int, ingested: str, **kw) -> dict[str, Any]:
    base = {"id": listing_id, "title": "x NM", "price": "10.00", "currency": "USD", "sold_at": "2026-09-25",
            "attribution": "exact", "ingested_at": ingested, "variant": "holo", "grader": None,
            "grade": None, "listing_url": None}
    base.update(kw)
    return base


def _page(rows, has_more=False, next_cursor=None):
    return {"data": rows, "pagination": {"has_more": has_more, "next_cursor": next_cursor}}


def _run(states, provider, store=None, **kw):
    store = store or FakeStore()
    for st in states:
        store.sync[st["sync"]["provider_card_id"]] = copy.deepcopy(st["sync"])
    kw.setdefault("credit_cap", inc.DAILY_INCREMENT_CREDIT_CAP)
    result = inc.run_increment(
        db=object(), provider=provider, store=store, expected_date="2026-10-02", states=states,
        pause_check=kw.pop("pause_check", lambda db: None), **kw)
    return result, store


@pytest.fixture(autouse=True)
def _activate_for_unit_tests(monkeypatch):
    monkeypatch.setattr(inc, "ACTIVATION_ENABLED", True)
    monkeypatch.setattr(inc, "_credits_used_today_by_mode", lambda db, day: {})
    monkeypatch.setattr(inc, "_provider_daily_credit_exhausted_today", lambda db, day: False)


# ------------------------------------------------------------------ dormancy
def test_dormant_by_default(monkeypatch):
    monkeypatch.setattr(inc, "ACTIVATION_ENABLED", False)
    with pytest.raises(inc.IncrementDormant):
        inc.run_increment(db=object(), provider=FakeProvider({}), expected_date="2026-10-02", states=[])


def test_commit_refuses_before_credentials_or_database(monkeypatch, capsys):
    monkeypatch.setattr(inc, "ACTIVATION_ENABLED", False)
    monkeypatch.setattr(inc.sys, "argv", ["x", "--commit"])
    import sys
    import types

    def touched():
        raise AssertionError("database touched while dormant")

    fake = types.ModuleType("backend.db.clients.supabase_client")
    fake.create_service_role_client = touched
    monkeypatch.setitem(sys.modules, "backend.db.clients.supabase_client", fake)
    assert inc.main() == 78
    assert '"database_writes": 0' in capsys.readouterr().out


def test_shipped_activation_flag_is_true_and_managed_schedule_present():
    source = (ROOT / "backend/scripts/run_core_panel_daily_increment.py").read_text(encoding="utf-8")
    assert re.search(r"^ACTIVATION_ENABLED = True$", source, re.M)
    cron = (ROOT / "infra/oracle/core-panel-daily-increment.crontab").read_text(encoding="utf-8")
    live = [l for l in cron.splitlines() if l.strip() and not l.lstrip().startswith("#") and not l.startswith("CRON_TZ")]
    assert len(live) == 1
    assert live[0].startswith("2,17,32,47 17 * * * ")
    assert "run_core_panel_daily_increment_guarded.sh" in live[0]
    installer = ROOT / "infra/oracle/install_core_panel_daily_increment_cron.sh"
    assert installer.exists()
    disabled = (ROOT / "infra/oracle/core-panel-daily-increment.crontab.DISABLED").read_text(encoding="utf-8")
    disabled_live = [l for l in disabled.splitlines() if l.strip() and not l.lstrip().startswith("#") and not l.startswith("CRON_TZ")]
    assert disabled_live == []


# ------------------------------------------------------------------ budget contract
def test_budget_contract_coexists_with_b5_and_active_supply():
    c = inc.budget_contract()
    assert c["account_daily_credit_limit"] == 75000
    assert c["b5_daily_cap"] == 55000
    assert c["active_supply_c_daily_cap"] == 4500
    assert c["core_panel_increment_daily_cap"] == 8000
    assert c["one_page_pass_credits"] == 207 * 20 == 4140
    assert c["total_committed"] == 55000 + 4500 + 600 + 8000 == 68100
    assert c["unallocated_headroom"] == c["scheduled_unallocated_headroom"] == 6900 >= inc.MIN_UNALLOCATED_HEADROOM
    assert c["headroom_scope"] == "AUDITED_SCHEDULED_CONSUMERS_ONLY"
    assert c["account_wide_remaining_credits_known"] is False
    assert c["unscheduled_research_consumers_may_share_account"] is True
    assert c["provider_exhaustion_authority"] == "HTTP_429_credit_limit_exceeded"
    assert c["worst_case_credits_enforced"] == 8000 < c["uncapped_worst_case_credits"] == 16560


def test_no_unaccounted_scheduled_provider_consumer_exists_on_current_develop():
    # Any workflow with a cron that drives PkmnPrices must be the audited daily vintage-gap one.
    scheduled = []
    for wf in sorted((ROOT / ".github/workflows").glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        if re.search(r"^\s*-?\s*cron:", text, re.M) and re.search(r"pkmnprices|PkmnPrices|sold_evidence|ebay_sold", text):
            scheduled.append(wf.name)
    assert scheduled == ["pkmnprices-sold-evidence-daily.yml"], scheduled
    # Any live (uncommented) VM crontab entry that runs a provider-credit job must be an audited one.
    live = set()
    for cron in sorted((ROOT / "infra/oracle").glob("*.crontab")):
        for line in cron.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and re.search(
                    r"microstructure_bucket|active_supply_panel\.sh|pkmnprices|core_panel", line):
                live.add(cron.name)
    assert live == {"market-microstructure-b4.crontab", "market-microstructure-b5.crontab",
                    "active-supply-panel.crontab", "core-panel-daily-increment.crontab"}, live
    assert len(inc.AUDITED_SCHEDULED_PROVIDER_CONSUMERS) == 5


def test_current_source_caps_have_not_drifted_from_the_audited_values():
    from backend.scripts import run_market_active_supply_snapshot as c
    from backend.scripts import run_market_microstructure_bucket_b5 as b5

    assert (inc.ACCOUNT_DAILY_CREDIT_LIMIT, b5.DAILY_B5_CREDIT_CAP, c.FULL_PANEL_CREDIT_CAP) == (75000, 55000, 4500)
    assert inc.B4_DAILY_CREDIT_CAP == 55000 and inc.CANARY_ONE_TIME_CREDIT_CEILING == 20
    assert inc.budget_contract()["canary_one_time_credit_ceiling"] == 20


def test_vintage_gap_cap_matches_the_workflow_it_cites():
    workflow = (ROOT / ".github/workflows/pkmnprices-sold-evidence-daily.yml").read_text(encoding="utf-8")
    assert f"--item-credit-cap {inc.VINTAGE_GAP_DAILY_CREDIT_CAP}" in workflow


def test_budget_contract_fails_if_it_would_break_the_account_ceiling(monkeypatch):
    monkeypatch.setattr(inc, "DAILY_INCREMENT_CREDIT_CAP", 15000)
    with pytest.raises(RuntimeError, match="HEADROOM"):
        inc.budget_contract()
    monkeypatch.setattr(inc, "DAILY_INCREMENT_CREDIT_CAP", 1000)
    with pytest.raises(RuntimeError, match="BELOW_ONE_PAGE_PASS"):
        inc.budget_contract()


def test_invocation_budget_accounts_prior_spend_and_other_consumers():
    fresh = inc.invocation_budget({}, 8000)
    assert fresh["invocation_credit_cap"] == 8000
    assert fresh["local_ledger_room_upper_bound_credits"] == fresh["account_room_credits"]
    assert fresh["account_wide_remaining_credits_known"] is False
    assert inc.invocation_budget({}, 8000)["invocation_credit_cap"] == 8000
    assert inc.invocation_budget({inc.MODE: 3000}, 8000)["invocation_credit_cap"] == 5000
    assert inc.invocation_budget({inc.MODE: 8000}, 8000)["invocation_credit_cap"] == 0
    # An out-of-contract consumer shrinks the room instead of breaching the ceiling.
    shrunk = inc.invocation_budget({"bucket_b5": 66000}, 8000)
    assert shrunk["invocation_credit_cap"] == 75000 - 2000 - 4500 - 66000 == 2500
    with pytest.raises(ValueError):
        inc.invocation_budget({}, 8001)


# ------------------------------------------------------------------ eligibility / no backfill / no lookup
@pytest.mark.parametrize("kwargs,reason", [
    ({"identity": False}, "NO_CACHED_IDENTITY"),
    ({"ready": False}, "PHASE1_NOT_READY"),
    ({"frontier": None}, "NO_FRONTIER"),
])
def test_ineligible_cards_are_skipped_never_fetched(kwargs, reason):
    state = _state(1, **kwargs)
    assert inc.card_eligibility(state) == (False, reason)
    provider = FakeProvider({})
    result, store = _run([state], provider)
    assert provider.calls == [] and result["skipped"] == {reason: 1}
    assert store.evidence == {}


def test_phase1_ready_card_with_partial_lifetime_cursor_is_eligible_and_cursor_is_untouched():
    # This is the real B4 shape for most Core Panel cards: 180d horizon reached, lifetime cursor still open.
    state = _state(1, complete=False, extra_meta={"core_panel_backfill_in_progress": True,
                                                  "core_panel_backfill_cursor": "OLD-CURSOR-123"})
    state["sync"]["status"] = "PARTIAL"
    assert inc.card_eligibility(state) == (True, "ELIGIBLE")
    original = copy.deepcopy(state["sync"])
    provider = FakeProvider({(1001, None): _page([_raw(1, "2026-09-25T00:00:00+00:00")])})
    result, store = _run([state], provider)
    written = copy.deepcopy(store.sync[1001])
    del written["metadata"][inc.STATE_KEY]
    assert written == original and written["metadata"]["core_panel_backfill_cursor"] == "OLD-CURSOR-123"
    assert all(c["cursor"] is None for c in provider.calls)  # the historical cursor is never used


def test_module_never_performs_identity_lookup_or_backfill():
    source = inspect.getsource(inc)
    for forbidden in ("cards_by_tcgplayer_id", "cards_by_name_number", "sets_by_name", "upsert_identity",
                      "ebay_sold_collection", "core_panel_backfill_cursor\"]", "initial_cursor"):
        assert forbidden not in source, forbidden


# ------------------------------------------------------------------ collection behaviour
def test_happy_path_since_frontier_combined_stream_and_state_preservation():
    state = _state(1, extra_meta={"core_panel_backfill_cursor": None, "phase1_oldest_sold_at": "2026-04-01"})
    original_sync = copy.deepcopy(state["sync"])
    provider = FakeProvider({(1001, None): _page([_raw(1, "2026-09-25T00:00:00+00:00"),
                                                  _raw(2, "2026-09-26T00:00:00Z", grader="PSA", grade="9")])})
    result, store = _run([state], provider)
    call = provider.calls[0]
    assert (call["graded"], call["sort"], call["since"], call["limit"], call["cursor"]) == (None, "date_desc", FLOOR, 20, None)
    assert result["status"] == "COMPLETE" and result["outcomes"] == {"FRONTIER_REACHED": 1}
    # raw + graded both preserved, with sold_at/ingested_at/collected_at present
    rows = list(store.evidence.values())
    assert {r["graded"] for r in rows} == {False, True}
    assert all(r["sold_at"] and r["ingested_at"] and r["collected_at"] for r in rows)
    written = store.sync[1001]
    assert written["metadata"][inc.STATE_KEY]["frontier_ingested_at"] == "2026-09-26T00:00:00Z"
    assert written["metadata"][inc.STATE_KEY]["open_gap"] is None
    # Everything except the namespaced key is byte-identical to what B4 left behind.
    stripped = copy.deepcopy(written)
    del stripped["metadata"][inc.STATE_KEY]
    assert stripped == original_sync


def test_frontier_comparison_is_timestamp_not_string_based():
    # '+00:00' vs 'Z' vs fractional seconds must not confuse "newer than the floor".
    state = _state(1, frontier="2026-09-20T00:00:00.500000+00:00")
    provider = FakeProvider({(1001, None): _page([_raw(1, "2026-09-20T00:00:01Z")])})
    result, store = _run([state], provider)
    assert result["outcomes"] == {"FRONTIER_REACHED": 1}


def test_overflow_page_entirely_newer_continues_until_the_since_set_is_exhausted():
    full = [_raw(i, f"2026-09-2{1 + i % 5}T00:00:00+00:00") for i in range(1, 21)]
    tail = [_raw(100 + i, "2026-09-23T00:00:00+00:00") for i in range(3)]
    provider = FakeProvider({(1001, None): _page(full, True, "c1"), (1001, "c1"): _page(tail)})
    result, store = _run([_state(1)], provider)
    assert [c["cursor"] for c in provider.calls] == [None, "c1"]
    assert all(c["since"] == FLOOR for c in provider.calls)
    receipt = store.runs[result["run_id"]]["metadata"]["receipts"][0]
    assert receipt["overflow"] is True and receipt["pages"] == 2 and receipt["outcome"] == "FRONTIER_REACHED"
    assert len(store.evidence) == 23
    assert store.runs[result["run_id"]]["metadata"]["overflow_cards"] == 1


def test_bounded_overflow_opens_gap_and_never_advances_frontier_then_resumes_first():
    def full(prefix: int) -> list[dict[str, Any]]:
        return [_raw(prefix * 100 + i, "2026-09-25T00:00:00+00:00") for i in range(20)]

    pages = {(1001, None): _page(full(1), True, "c1"), (1001, "c1"): _page(full(2), True, "c2"),
             (1001, "c2"): _page(full(3), True, "c3"), (1001, "c3"): _page(full(4), True, "c4")}
    state = _state(1)
    result, store = _run([state], FakeProvider(pages))
    assert result["outcomes"] == {"GAP_OPEN_BOUNDED_OVERFLOW": 1}
    saved = store.sync[1001]["metadata"][inc.STATE_KEY]
    assert saved["frontier_ingested_at"] == FLOOR  # NOT advanced past the unfetched span
    assert saved["open_gap"]["floor_ingested_at"] == FLOOR
    assert saved["open_gap"]["resume_cursor"] == "c4"
    assert len(store.evidence) == 80 and result["credits_used"] == 80

    # Next day: the open-gap card is served first, from its cursor, with the SAME floor.
    next_state = _state(1)
    next_state["sync"] = copy.deepcopy(store.sync[1001])
    other = _state(2)
    resume_provider = FakeProvider({(1001, "c4"): _page([_raw(900, "2026-09-26T00:00:00+00:00")]),
                                    (1002, None): _page([])})
    result2, store2 = _run([other, next_state], resume_provider)
    assert resume_provider.calls[0]["provider_id"] == 1001
    assert resume_provider.calls[0]["cursor"] == "c4" and resume_provider.calls[0]["since"] == FLOOR
    closed = store2.sync[1001]["metadata"][inc.STATE_KEY]
    assert closed["open_gap"] is None and closed["frontier_ingested_at"].startswith("2026-09-26")


def test_since_filter_not_honoured_fails_closed():
    # A row at/older than the floor means the provider ignored `since`: do not advance.
    provider = FakeProvider({(1001, None): _page([_raw(1, "2026-09-10T00:00:00+00:00")])})
    result, store = _run([_state(1)], provider)
    assert result["outcomes"] == {"GAP_OPEN_SINCE_FILTER_NOT_HONOURED": 1}
    saved = store.sync[1001]["metadata"][inc.STATE_KEY]
    assert saved["frontier_ingested_at"] == FLOOR and saved["open_gap"]["floor_ingested_at"] == FLOOR


def test_hard_cap_is_never_exceeded_and_unvisited_cards_are_untouched():
    states = [_state(n) for n in range(1, 6)]
    provider = FakeProvider({(1000 + n, None): _page([_raw(n * 10 + i, "2026-09-25T00:00:00+00:00") for i in range(20)])
                             for n in range(1, 6)})
    result, store = _run(states, provider, credit_cap=45)  # room for two 20-credit pages only
    assert provider.credits_charged <= 45
    assert len(provider.calls) == 2 and result["halted_reason"] == "BUDGET_EXHAUSTED"
    assert result["unvisited_cards"] == 3 and result["status"] == "PARTIAL"
    assert store.sync_writes == 2  # cards never fetched are not written


def test_worst_case_credit_bound_holds_with_conservative_accounting():
    n = 207
    states = [_state(i) for i in range(1, n + 1)]
    pages: dict[tuple[int, str | None], dict[str, Any]] = {}
    for i in range(1, n + 1):
        for k in range(inc.MAX_PAGES_PER_CARD_DAY + 1):
            cursor = None if k == 0 else f"c{k}"
            rows = [_raw(i * 1000 + k * 20 + j, "2026-09-25T00:00:00+00:00") for j in range(20)]
            pages[(1000 + i, cursor)] = _page(rows, True, f"c{k + 1}")
    provider = FakeProvider(pages, charge="limit")  # provider bills the requested limit
    result, store = _run(states, provider)
    assert provider.credits_charged <= inc.DAILY_INCREMENT_CREDIT_CAP == 8000
    # Pass 1 alone (one page for every card) is the 4,140 contract number.
    assert provider.credits_charged >= inc.ONE_PAGE_PASS_CREDITS
    assert max(sum(1 for c in provider.calls if c["provider_id"] == 1000 + i) for i in range(1, n + 1)) <= inc.MAX_PAGES_PER_CARD_DAY
    assert result["status"] == "PARTIAL"
    gaps = [r for r in store.runs[result["run_id"]]["metadata"]["receipts"] if r["outcome"].startswith("GAP_OPEN")]
    assert len(gaps) == len(store.runs[result["run_id"]]["metadata"]["receipts"])  # nothing silently dropped


def test_operational_pause_stops_mid_run():
    states = [_state(1), _state(2)]
    provider = FakeProvider({(1001, None): _page([]), (1002, None): _page([])})
    calls = {"n": 0}

    def pause(db):
        calls["n"] += 1
        return {"reason": "SCRAPE_BATCH_ACTIVE"} if calls["n"] >= 3 else None

    result, _ = _run(states, provider, pause_check=pause)
    assert result["halted_reason"] == "OPERATIONAL_PAUSE" and len(provider.calls) == 1


def test_provider_credit_ceiling_mismatch_halts():
    provider = FakeProvider({(1001, None): _page([])})
    provider.credits_limit = 100000
    result, _ = _run([_state(1)], provider)
    assert result["halted_reason"] == "ACCOUNT_CREDIT_LIMIT_MISMATCH" and provider.calls == []


def test_blocked_without_budget_or_when_paused():
    result, store = _run([_state(1)], FakeProvider({}), pause_check=lambda db: {"reason": "C_CONTINUITY_WINDOW"})
    assert result["status"] == "BLOCKED" and result["reason"] == "C_CONTINUITY_WINDOW" and store.runs == {}


def test_run_receipt_is_an_increment_run_with_no_lookups_and_no_nm_authority():
    provider = FakeProvider({(1001, None): _page([_raw(1, "2026-09-25T00:00:00+00:00")])})
    result, store = _run([_state(1)], provider)
    run = store.runs[result["run_id"]]
    assert run["metadata"]["mode"] == inc.MODE and run["provider_card_lookup_count"] == 0
    assert run["set_value_nm_eligible_count"] == 0 and run["manifest_fingerprint"] == inc.PANEL_FINGERPRINT
    assert run["metadata"]["identity_lookups_allowed"] is False and run["credits_used"] <= run["item_credit_cap"]


# ------------------------------------------------------------------ immutability / drift (real store)
class _Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.insert_rows = db, table, [], None

    def select(self, *_):
        return self

    def eq(self, k, v):
        self.filters.append((k, lambda x, v=v: str(x) == str(v)))
        return self

    def in_(self, k, vs):
        self.filters.append((k, lambda x, vs=vs: x in vs))
        return self

    def insert(self, rows):
        self.insert_rows = rows
        return self

    def execute(self):
        if self.insert_rows is not None:
            self.db.rows[self.table].extend(copy.deepcopy(self.insert_rows))
            self.db.writes += len(self.insert_rows)
            return type("R", (), {"data": self.insert_rows})()
        data = [r for r in self.db.rows[self.table] if all(f(r.get(k)) for k, f in self.filters)]
        return type("R", (), {"data": copy.deepcopy(data)})()


class _MemDB:
    def __init__(self):
        self.rows = {"pkmnprices_ebay_sold_evidence_v1": []}
        self.writes = 0

    def table(self, name):
        return _Query(self, name)


def test_original_evidence_is_immutable_and_provider_enrichment_drift_is_only_reported():
    db = _MemDB()
    store = PkmnPricesStore(db)
    target = _target(1)
    first = inc._normalize(_raw(7, "2026-09-25T00:00:00+00:00", title="Eevee NM 167/131"), target, 1001, "run1", "2026-10-02T00:00:00+00:00")
    assert store.insert_evidence([first]) == (1, 0, 0)
    snapshot = copy.deepcopy(db.rows["pkmnprices_ebay_sold_evidence_v1"])
    # Provider later reclassifies the same transaction as TAG 9.
    drifted = inc._normalize(_raw(7, "2026-09-25T00:00:00+00:00", title="Eevee NM 167/131", grader="TAG", grade="9"),
                             target, 1001, "run2", "2026-10-03T00:00:00+00:00")
    assert store.insert_evidence([drifted]) == (0, 1, 1)
    assert db.rows["pkmnprices_ebay_sold_evidence_v1"] == snapshot  # not rewritten, not duplicated
    assert db.rows["pkmnprices_ebay_sold_evidence_v1"][0]["graded"] is False


def test_collector_uses_only_append_dedupe_store_for_evidence():
    source = inspect.getsource(inc)
    assert "insert_evidence" in source
    assert not re.search(r"\)\s*\.(insert|update|delete)\(", source)
    assert "pkmnprices_ebay_sold_evidence_v1" not in source.replace('"""', "")  # never touches evidence directly


# ------------------------------------------------------------------ preflight + scheduler artefacts
def test_preflight_makes_zero_provider_calls_and_zero_writes(monkeypatch):
    states = [_state(1), _state(2, ready=False)]
    monkeypatch.setattr(inc, "panel_states", lambda db: states)
    monkeypatch.setattr(inc, "operational_pause_reason", lambda db: None)
    monkeypatch.setattr(inc, "ACTIVATION_ENABLED", False)

    class ReadOnlyDB:
        def __getattr__(self, name):
            raise AssertionError(f"preflight touched db.{name}")

    result = inc.preflight(ReadOnlyDB(), expected_date="2026-10-02")
    assert result["provider_requests"] == 0 and result["provider_credits_used"] == 0 and result["database_writes"] == 0
    assert result["dormant"] is True and result["eligible_cards"] == 1
    assert result["eligibility"] == {"ELIGIBLE": 1, "PHASE1_NOT_READY": 1}
    assert result["budget_contract"]["total_committed"] == 68100


def test_wrapper_preserves_b5_lock_and_hold_ordering():
    wrapper = (ROOT / "infra/oracle/run_core_panel_daily_increment.sh").read_text(encoding="utf-8")
    b5 = (ROOT / "infra/oracle/run_market_microstructure_bucket_b5.sh").read_text(encoding="utf-8")
    markers = ["db-safety/hold.json", "release.sha", "/tmp/active-supply-panel.lock",
               "/tmp/pokemon-scrape-dispatcher.lock", "/tmp/pkmnprices-api.lock",
               "/tmp/pokemon-post-scrape-publication.lock"]
    positions = [wrapper.index(m) for m in markers]
    assert positions == sorted(positions)
    assert wrapper.count("DB_SAFETY_HOLD") == 2 and wrapper.rindex("DB_SAFETY_HOLD") > wrapper.index("publication.lock")
    assert wrapper.index("DB_SAFETY_HOLD", wrapper.index("publication.lock")) < wrapper.index("exec \"$PY\"")
    # Same lock files, in the same order, as B5.
    order = lambda text: re.findall(r"/tmp/[a-z-]+\.lock", text)  # noqa: E731
    assert order(wrapper) == order(b5)
    assert "run_core_panel_daily_increment --commit" in wrapper and "BUCKET_B5" not in wrapper


def test_managed_installer_is_verify_first_and_sha_pinned():
    installer = (ROOT / "infra/oracle/install_core_panel_daily_increment_cron.sh").read_text(encoding="utf-8")
    assert 'if [ "${1:-}" != "--apply" ]' in installer
    assert "run_core_panel_daily_increment --preflight" in installer
    assert 'worktree add --detach "$RUNTIME" "$SHA"' in installer
    assert 'release.sha.tmp' in installer and 'mv "$STATE/release.sha.tmp" "$STATE/release.sha"' in installer
    assert 'core-panel-daily-increment.crontab' in installer
    assert 'run_core_panel_daily_increment.sh' in installer
    assert 'run_core_panel_daily_increment_guarded.sh' in installer
    assert "grep -q 'run_core_panel_daily_increment'" in installer


def test_guarded_scheduler_wrapper_uses_db_workload_guard():
    guarded = (ROOT / "infra/oracle/run_core_panel_daily_increment_guarded.sh").read_text(encoding="utf-8")
    assert "/home/ubuntu/state/db-safety/db_workload_guard.py" in guarded
    assert "--run-encoded" in guarded
    assert "--wait-lock-seconds 300" in guarded
    assert "run_core_panel_daily_increment.sh" in guarded


def test_provider_daily_credit_exhaustion_halts_after_first_429_and_preserves_recoverability():
    first = _state(1)
    second = _state(2)
    third = _state(3)
    page = [_raw(i, "2026-09-25T00:00:00+00:00") for i in range(20)]
    provider = FakeProvider({
        (1001, None): _page(page, True, "c1"),
        (1002, None): inc.PkmnPricesAPIError(429, "credit_limit_exceeded", "daily credits spent"),
    })
    result, store = _run([first, second, third], provider)
    assert result["status"] == "PARTIAL"
    assert result["halted_reason"] == inc.PROVIDER_DAILY_CREDIT_HALT
    assert len(provider.calls) == 2
    assert len(result["failures"]) == 1
    assert result["unvisited_cards"] == 2
    saved = store.sync[1001]["metadata"][inc.STATE_KEY]
    assert saved["frontier_ingested_at"] == FLOOR
    assert saved["open_gap"]["reason"] == "BOUNDED_OVERFLOW"
    assert inc.STATE_KEY not in store.sync[1002]["metadata"]
    assert inc.STATE_KEY not in store.sync[1003]["metadata"]


def test_prior_provider_daily_credit_exhaustion_blocks_without_provider_call(monkeypatch):
    monkeypatch.setattr(inc, "_provider_daily_credit_exhausted_today", lambda db, day: True)
    provider = FakeProvider({})
    result, store = _run([_state(1)], provider)
    assert result["status"] == "BLOCKED"
    assert result["reason"] == inc.PROVIDER_DAILY_CREDIT_HALT
    assert result["provider_daily_credit_exhausted"] is True
    assert result["invocation_budget"]["invocation_credit_cap"] == 0
    assert provider.calls == []
    assert store.runs == {}


def test_provider_daily_credit_exhaustion_detection_supports_legacy_failure_receipt():
    class Result:
        data = [{
            "error_code": "PkmnPricesAPIError",
            "started_at": "2026-10-02T20:28:20Z",
            "metadata": {
                "failures": [{
                    "message": "PkmnPrices API error status=429 code=credit_limit_exceeded"
                }]
            },
        }]

    class Query:
        def select(self, *_args):
            return self
        def gte(self, *_args):
            return self
        def lt(self, *_args):
            return self
        def execute(self):
            return Result()

    class DB:
        def table(self, name):
            assert name == "pkmnprices_sold_runs_v1"
            return Query()

    assert REAL_PROVIDER_DAILY_CREDIT_EXHAUSTED(DB(), "2026-10-02") is True


def test_same_day_retry_skips_closed_cards_and_only_resumes_open_gap():
    closed = _state(1, extra_meta={
        inc.STATE_KEY: {
            "last_run_date": "2026-10-02",
            "frontier_ingested_at": "2026-09-26T00:00:00Z",
            "open_gap": None,
        }
    })
    gap = _state(2, extra_meta={
        inc.STATE_KEY: {
            "last_run_date": "2026-10-02",
            "frontier_ingested_at": FLOOR,
            "open_gap": {
                "floor_ingested_at": FLOOR,
                "head_ingested_at": "2026-09-25T00:00:00Z",
                "resume_cursor": "resume",
                "opened_on": "2026-10-02",
                "reason": "BOUNDED_OVERFLOW",
            },
        }
    })
    provider = FakeProvider({(1002, "resume"): _page([])})
    result, _ = _run([closed, gap], provider)
    assert result["status"] == "COMPLETE"
    assert result["skipped"] == {"ALREADY_CURRENT_TODAY": 1}
    assert len(provider.calls) == 1
    assert provider.calls[0]["provider_id"] == 1002
    assert provider.calls[0]["cursor"] == "resume"


def test_same_day_retry_with_every_card_current_makes_zero_provider_calls():
    state = _state(1, extra_meta={
        inc.STATE_KEY: {
            "last_run_date": "2026-10-02",
            "frontier_ingested_at": "2026-09-26T00:00:00Z",
            "open_gap": None,
        }
    })
    provider = FakeProvider({})
    result, store = _run([state], provider)
    assert result["status"] == "COMPLETE"
    assert result["skipped"] == {"ALREADY_CURRENT_TODAY": 1}
    assert provider.calls == []
    run = store.runs[result["run_id"]]
    assert run["target_count"] == 0 and run["credits_used"] == 0
