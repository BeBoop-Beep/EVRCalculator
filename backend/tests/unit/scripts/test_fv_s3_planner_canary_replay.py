from __future__ import annotations

import copy
import inspect
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from backend.scripts import plan_core_panel_catchup as planner
from backend.scripts import run_core_panel_daily_increment as inc
from backend.scripts import run_core_panel_provider_semantics_canary as canary
from backend.scripts import run_index_fair_value_shadow_v1 as shadow_run
from backend.scripts import run_index_fair_value_sold_clearing_anchor_v1 as s2

ROOT = Path(__file__).resolve().parents[4]
ACTIVATION = date(2026, 10, 8)


# ------------------------------------------------------------------ planner (pure)
def _state(n=1, *, frontier="2026-09-28T00:00:00Z", ready=True, identity=True, partial=True):
    meta = {"core_panel_incremental_watermark": frontier, "phase1_ready": ready,
            "core_panel_backfill_complete": not partial, "core_panel_backfill_cursor": "keep" if partial else None}
    sync = {"provider_card_id": 1000 + n, "canonical_card_id": f"c{n}", "status": "PARTIAL" if partial else "CURRENT",
            "last_ingested_at": None, "metadata": meta}
    return {"target": {"canonical_card_id": f"c{n}"}, "identity": {"provider_card_id": 1000 + n} if identity else None,
            "sync": sync, "phase1_ready": ready, "panel_index": n}


def test_planner_states_and_arithmetic():
    # frontier 10 days before activation, 30 rows in the 30d velocity window -> 1/day -> 10 expected, 20 conservative.
    low = planner.plan_card(_state(1, frontier="2026-09-28T00:00:00Z"), {"rows_ingested_in_velocity_window": 30},
                            intended_activation=ACTIVATION)
    assert low["catchup_interval_days"] == 10.0 and low["estimated_new_rows"] == 10.0
    assert low["conservative_new_rows"] == 20.0 and low["likely_needs_more_than_one_page"] is False
    assert low["state"] == "READY"
    high = planner.plan_card(_state(2), {"rows_ingested_in_velocity_window": 90}, intended_activation=ACTIVATION)
    assert high["state"] == "POTENTIAL_OVERFLOW" and high["estimated_pages_conservative"] == 3
    assert high["estimated_days_to_clear_at_page_cap"] == 1
    big = planner.plan_card(_state(3), {"rows_ingested_in_velocity_window": 900}, intended_activation=ACTIVATION)
    assert big["estimated_pages_conservative"] == 30 and big["estimated_days_to_clear_at_page_cap"] == 8


@pytest.mark.parametrize("kwargs,reason", [({"identity": False}, "NO_CACHED_IDENTITY"), ({"ready": False}, "PHASE1_NOT_READY"),
                                           ({"frontier": None}, "NO_FRONTIER")])
def test_planner_blocks_ineligible_cards(kwargs, reason):
    st = _state(1, **{k: v for k, v in kwargs.items() if k != "frontier"})
    if "frontier" in kwargs:
        st["sync"]["metadata"].pop("core_panel_incremental_watermark")
    plan = planner.plan_card(st, {}, intended_activation=ACTIVATION)
    assert plan["state"] == "BLOCKED" and plan["block_reason"] == reason


def test_verified_since_semantics_make_one_page_cards_ready(monkeypatch):
    assert planner.SINCE_SEMANTICS_VERIFIED is True
    cards = [planner.plan_card(_state(i), {"rows_ingested_in_velocity_window": 3}, intended_activation=ACTIVATION)
             for i in range(1, 6)]
    assert {c["state"] for c in cards} == {"READY"}
    assert planner.summarize(cards)["ready_is_unreachable_until_canary"] is False
    monkeypatch.setattr(planner, "SINCE_SEMANTICS_VERIFIED", False)
    assert planner.plan_card(_state(1), {"rows_ingested_in_velocity_window": 3}, intended_activation=ACTIVATION)["state"] == "NEEDS_CANARY_SEMANTICS"


def test_planner_credit_projection_is_capped_by_the_daily_ceiling():
    cards = [planner.plan_card(_state(i), {"rows_ingested_in_velocity_window": 900}, intended_activation=ACTIVATION)
             for i in range(1, 151)]
    summary = planner.summarize(cards)
    assert summary["first_day_credit_demand_uncapped"] == 150 * inc.MAX_PAGES_PER_CARD_DAY * inc.PAGE_SIZE
    assert summary["first_day_credit_ceiling_if_activated"] == inc.DAILY_INCREMENT_CREDIT_CAP


class _FakeResult:
    def __init__(self, data):
        self.data, self.count = data, len(data)


class _FakeQuery:
    def __init__(self, db, table):
        self.db, self.table, self.filters = db, table, []

    def select(self, *a, **k):
        self.db.ops.append(("select", self.table))
        return self

    def eq(self, key, value):
        self.filters.append(lambda r, k=key, v=value: str(r.get(k)) == str(v))
        return self

    def in_(self, key, values):
        self.filters.append(lambda r, k=key, v=values: r.get(k) in v)
        return self

    def __getattr__(self, name):
        if name in {"order", "range", "limit", "gte", "lte"}:
            return lambda *a, **k: self
        raise AttributeError(name)

    def execute(self):
        rows = [r for r in self.db.tables.get(self.table, []) if all(f(r) for f in self.filters)]
        return _FakeResult(copy.deepcopy(rows))


class _FakeDB:
    def __init__(self, tables):
        self.tables, self.ops = tables, []

    def table(self, name):
        return _FakeQuery(self, name)


def test_planner_io_is_select_only_and_makes_no_provider_call(monkeypatch):
    panel = s2.load_panel()
    first = sorted(panel["rows"], key=lambda r: str(r["canonical_card_id"]))[0]
    cid = str(first["canonical_card_id"])
    db = _FakeDB({
        "pkmnprices_card_identity_v1": [{"provider_card_id": 77, "canonical_card_id": cid, "language": "English",
                                         "tcgplayer_product_id": "1"}],
        "pkmnprices_sold_sync_state_v1": [{"provider_card_id": 77, "canonical_card_id": cid, "status": "PARTIAL",
                                           "metadata": {"phase1_ready": True,
                                                        "core_panel_incremental_watermark": "2026-09-25T00:00:00Z"}}],
        "pkmnprices_ebay_sold_evidence_v1": [{"provider_card_id": 77, "provider_listing_id": 1,
                                              "ingested_at": "2026-09-24T00:00:00Z", "sold_at": "2026-09-23"}],
    })
    ro = s2.ReadOnlyClient(db)
    states = planner.fetch_states(ro, panel)
    assert len(states) == 207 and states[0]["identity"]["provider_card_id"] == 77
    persisted = planner.fetch_persisted(ro, states[0])
    assert persisted["latest_sold_at"] == "2026-09-23" and persisted["rows_ingested_in_velocity_window"] == 1
    assert persisted["canary_probe_since"] is None
    assert {op for op, _ in db.ops} == {"select"}
    source = inspect.getsource(planner)
    for forbidden in ("PkmnPricesClient", "pkmnprices_client", "load_pkmnprices_credentials", "upsert",
                      "create_service_role_client", "requests.", "subprocess"):
        assert forbidden not in source, forbidden
    assert not re.search(r"\)\s*\.(insert|update|upsert|delete|rpc)\(", source)


def test_planner_derives_replay_probe_one_microsecond_before_known_frontier_batch():
    st = _state(1, frontier="2026-09-25T00:00:00Z")
    db = _FakeDB({
        "pkmnprices_ebay_sold_evidence_v1": [
            {"provider_card_id": 1001, "provider_listing_id": 1, "ingested_at": "2026-09-25T00:00:00Z",
             "sold_at": "2026-09-24", "graded": False, "grader": None, "grade": None},
            {"provider_card_id": 1001, "provider_listing_id": 2, "ingested_at": "2026-09-25T00:00:00Z",
             "sold_at": "2026-09-23", "graded": True, "grader": "PSA", "grade": "9"},
            {"provider_card_id": 1001, "provider_listing_id": 3, "ingested_at": "2026-09-25T00:00:00Z",
             "sold_at": "2026-09-22", "graded": False, "grader": None, "grade": None},
        ],
    })
    persisted = planner.fetch_persisted(db, st)
    assert persisted["frontier_batch_rows"] == 3
    assert persisted["frontier_batch_graded_rows"] == 1
    assert persisted["frontier_batch_ungraded_rows"] == 2
    assert persisted["canary_probe_since"] == "2026-09-24T23:59:59.999999Z"


# ------------------------------------------------------------------ canary
def _plan(n=6):
    rows = []
    batch_rows = [0, 5, 9, 12, 19, 10]
    graded_rows = [0, 0, 1, 0, 1, 1]
    for i in range(n):
        batch = batch_rows[i % 6]
        graded = graded_rows[i % 6]
        rows.append({
            "canonical_card_id": f"card-{i:02d}",
            "provider_card_id": 100 + i,
            "state": "POTENTIAL_OVERFLOW",
            "frontier_ingested_at": "2026-09-25T00:00:00Z",
            "canary_probe_since": "2026-09-24T23:59:59.999999Z" if batch else None,
            "frontier_batch_rows": batch,
            "frontier_batch_graded_rows": graded,
            "frontier_batch_ungraded_rows": batch - graded,
            "estimated_new_rows": [5, 12, 19, 21, 40, 20][i % 6],
        })
    return rows


def test_selection_is_deterministic_rule_based_and_not_hardcoded():
    plan = _plan()
    picked = canary.select_canary_card(plan)
    assert picked["canonical_card_id"] == "card-05"
    assert picked["frontier_batch_rows"] == 10
    assert picked["frontier_batch_graded_rows"] == 1
    assert picked["frontier_batch_ungraded_rows"] == 9
    assert picked["probe_since"] == "2026-09-24T23:59:59.999999Z"
    assert canary.select_canary_card(list(reversed(plan))) == picked
    tie = [{**plan[2], "canonical_card_id": "b"}, {**plan[2], "canonical_card_id": "a"}]
    assert canary.select_canary_card(tie)["canonical_card_id"] == "a"
    blocked = [{**plan[5], "state": "BLOCKED"}]
    with pytest.raises(canary.CanaryRefused, match="NO_REPLAYABLE"):
        canary.select_canary_card(blocked)
    with pytest.raises(canary.CanaryRefused):
        canary.select_canary_card([{**plan[0]}])  # no replayable frontier batch
    assert "umbreon" not in inspect.getsource(canary).lower()


def _payload(rows, has_more=False, cursor=None):
    return {"data": rows, "pagination": {"has_more": has_more, "next_cursor": cursor}}


def _r(i, sold, ing, **kw):
    return {"id": i, "sold_at": sold, "ingested_at": ing, "grader": None, "grade": None, **kw}


FLOOR = "2026-09-25T00:00:00Z"


def _analyze(rows, *, has_more=False, cursor=None, before=0, after=None, persisted=frozenset()):
    return canary.analyze_canary_response(
        since=FLOOR, limit=20, payload=_payload(rows, has_more, cursor), credits_before=before,
        credits_after=len(rows) if after is None else after, persisted_listing_ids=set(persisted))


def test_canary_confirms_a_clean_per_item_billed_page():
    rows = [_r(i, f"2026-09-{29 - i:02d}", f"2026-09-{29 - i:02d}T12:00:00Z") for i in range(5)]
    rows[1]["grader"], rows[1]["grade"] = "PSA", "9"
    out = _analyze(rows)
    c = out["checks"]
    assert out["verdict"] == "SEMANTICS_CONFIRMED" and c["6_billing_model"] == "PER_RETURNED_ITEM"
    assert c["1_date_desc_by_sold_at"] and c["2_since_filter_honoured"] and c["3_stops_at_frontier"]
    assert c["7_combined_stream_has_graded_rows"] and c["7_graded_row_count"] == 1 and c["7_ungraded_row_count"] == 4
    assert c["8_rows_already_persisted"] == 0 and c["5_credits_charged_delta"] == 5


def test_canary_distinguishes_billing_models():
    rows = [_r(i, "2026-09-28", "2026-09-28T00:00:00Z") for i in range(5)]
    assert _analyze(rows, after=20)["checks"]["6_billing_model"] == "PER_REQUESTED_LIMIT"
    assert _analyze(rows, after=1)["checks"]["6_billing_model"] == "FLAT_PER_REQUEST"
    assert _analyze(rows, after=9)["checks"]["6_billing_model"] == "OTHER"
    full = [_r(i, "2026-09-28", "2026-09-28T00:00:00Z") for i in range(20)]
    amb = _analyze(full, has_more=True, cursor="c", after=20)
    assert amb["checks"]["6_billing_model"] == "AMBIGUOUS_PER_ITEM_OR_PER_LIMIT_FULL_PAGE"
    assert amb["verdict"] == "SEMANTICS_NOT_CONFIRMED"
    assert _analyze([], after=0)["checks"]["6_billing_model"] == "INCONCLUSIVE_EMPTY_PAGE"


def test_canary_detects_since_ordering_pagination_and_ceiling_problems():
    bad_since = _analyze([_r(1, "2026-09-28", "2026-09-24T00:00:00Z")])
    assert bad_since["checks"]["2_since_filter_honoured"] is False and "2_since_filter_honoured" in bad_since["failed_checks"]
    inclusive = _analyze([_r(1, "2026-09-28", FLOOR)])
    assert inclusive["checks"]["2_since_inclusive_of_floor"] is True and inclusive["checks"]["2_rows_at_or_before_floor"] == 1
    unordered = _analyze([_r(1, "2026-09-20", "2026-09-28T00:00:00Z"), _r(2, "2026-09-28", "2026-09-28T00:00:00Z")])
    assert unordered["checks"]["1_date_desc_by_sold_at"] is False
    assert _analyze([_r(1, "2026-09-28", "2026-09-28T00:00:00Z")], has_more=True, cursor=None)["checks"]["4_pagination_consistent"] is False
    assert _analyze([_r(1, "2026-09-28", "2026-09-28T00:00:00Z")], cursor="x")["checks"]["4_pagination_consistent"] is False
    over = _analyze([_r(1, "2026-09-28", "2026-09-28T00:00:00Z")], after=21)
    assert over["checks"]["5_within_ceiling"] is False and over["verdict"] == "SEMANTICS_NOT_CONFIRMED"


def test_canary_reports_dedupe_overlap_with_persisted_rows():
    rows = [_r(1, "2026-09-28", "2026-09-28T00:00:00Z"), _r(2, "2026-09-27", "2026-09-27T00:00:00Z")]
    assert _analyze(rows, persisted={2, 99})["checks"]["8_rows_already_persisted"] == 1


class _Locker:
    def __init__(self, log):
        self.log = log

    def acquire_in_order(self, paths):
        log = self.log

        class Ctx:
            def __enter__(s):
                log.append(("lock", tuple(paths)))

            def __exit__(s, *a):
                log.append(("unlock",))

        return Ctx()


class _Provider:
    credits_charged = 0

    def __init__(self, log, rows):
        self.log, self.rows = log, rows

    def ebay_sold_page(self, provider_id, **kw):
        self.log.append(("call", provider_id, kw))
        self.credits_charged += len(self.rows)
        return _payload(self.rows)


def _run(monkeypatch, *, enabled=True, **over):
    monkeypatch.setattr(canary, "CANARY_ENABLED", enabled)
    log: list[Any] = []
    plan = _plan()
    args = dict(provider=_Provider(log, [_r(1, "2026-09-28", "2026-09-28T00:00:00Z")]), plan_cards=plan,
                canonical_card_id="card-05", ticket="FVCANARY-20261010-AB12", persisted_ids_loader=lambda pid: set(),
                locker=_Locker(log), hold_present=lambda: False, is_interactive=True)
    args.update(over)
    return canary.run_canary(**args), log


def test_canary_disable_guard_refuses_before_anything(monkeypatch, capsys, tmp_path):
    assert canary.CANARY_ENABLED is True  # reviewed one-shot activation branch
    monkeypatch.setattr(canary, "CANARY_ENABLED", False)
    with pytest.raises(canary.CanaryDisabled):
        canary.run_canary(provider=None, plan_cards=[], canonical_card_id="", ticket="", persisted_ids_loader=None,
                          locker=None, hold_present=lambda: False, is_interactive=True)
    missing_plan = tmp_path / "does-not-exist.json"  # proves the plan is not even read
    assert canary.main(["--plan", str(missing_plan), "--commit"]) == 78
    assert '"provider_requests": 0' in capsys.readouterr().out


def test_enabled_canary_makes_exactly_one_bounded_call_and_no_db_write(monkeypatch):
    result, log = _run(monkeypatch)
    calls = [e for e in log if e[0] == "call"]
    assert len(calls) == 1 and calls[0][1] == 105
    kw = calls[0][2]
    assert (kw["graded"], kw["sort"], kw["limit"], kw["cursor"], kw["since"]) == (None, "date_desc", 20, None, "2026-09-24T23:59:59.999999Z")
    assert log[0] == ("lock", canary.LOCK_ORDER) and log[-1] == ("unlock",)
    assert result["provider_requests"] == 1 and result["database_writes"] == 0
    assert result["provider_credits_ceiling"] == 20 == canary.CANARY_CREDIT_CEILING


@pytest.mark.parametrize("over,message", [
    ({"is_interactive": False}, "INTERACTIVE"),
    ({"ticket": "ok"}, "TICKET"),
    ({"ticket": ""}, "TICKET"),
    ({"canonical_card_id": "card-01"}, "DETERMINISTIC_SELECTION"),
    ({"hold_present": lambda: True}, "DB_SAFETY_HOLD"),
])
def test_enabled_canary_refuses_unsafe_invocations_before_any_provider_call(monkeypatch, over, message):
    log: list[Any] = []
    provider = _Provider(log, [])
    with pytest.raises(canary.CanaryRefused, match=message):
        _run(monkeypatch, provider=provider, locker=_Locker(log), **over)
    assert not [e for e in log if e[0] == "call"]


def test_hold_appearing_after_locks_still_refuses(monkeypatch):
    seq = iter([False, True])
    log: list[Any] = []
    with pytest.raises(canary.CanaryRefused, match="HOLD"):
        _run(monkeypatch, provider=_Provider(log, []), locker=_Locker(log), hold_present=lambda: next(seq))
    assert not [e for e in log if e[0] == "call"]


def test_canary_credit_ceiling_blocks_a_second_use(monkeypatch):
    provider = _Provider([], [])
    provider.credits_charged = 1
    with pytest.raises(canary.CanaryRefused, match="CEILING"):
        _run(monkeypatch, provider=provider)


def test_canary_is_not_schedulable_and_shares_the_b5_lock_order():
    assert not list((ROOT / "infra/oracle").glob("*canary*"))
    assert not list((ROOT / ".github/workflows").glob("*canary*semantic*"))
    b5 = (ROOT / "infra/oracle/run_market_microstructure_bucket_b5.sh").read_text(encoding="utf-8")
    assert tuple(re.findall(r"/tmp/[a-z-]+\.lock", b5)) == canary.LOCK_ORDER
    source = inspect.getsource(canary)
    for forbidden in ("cards_by_tcgplayer_id", "cards_by_name_number", "ebay_sold_collection", "upsert_identity",
                      "insert_evidence", "upsert_sync_state"):
        assert forbidden not in source
    assert not re.search(r"\)\s*\.(insert|update|upsert|delete)\(", source)
    # activation-time DB access is wrapped select-only
    assert "s2.ReadOnlyClient(create_service_role_client())" in source


def test_offline_selection_prints_the_future_operator_command(tmp_path, capsys):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"cards": _plan()}), encoding="utf-8")
    assert canary.main(["--plan", str(path), "--dry-run"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["provider_requests"] == 0 and out["provider_credits_used"] == 0
    assert "--commit" in out["operator_command"] and "card-05" in out["operator_command"]
    assert out["would_call"]["credit_ceiling"] == 20 and out["would_call"]["params"]["limit"] == 20


# ------------------------------------------------------------------ replay runner
def _synthetic_snapshot(panel, collected: str):
    ev, ids, prices, obs, n = [], [], [], [], 0
    for i, pr in enumerate(panel["rows"]):
        cid = pr["canonical_card_id"]
        ids.append({"provider_card_id": 1000 + i, "canonical_card_id": cid, "tcgplayer_product_id": "1", "language": "English"})
        for k in range(12):
            n += 1
            ev.append({"provider_listing_id": n, "provider_card_id": 1000 + i, "canonical_card_id": cid,
                       "title": f"{pr['card_name']} {pr['card_number']}/131 NM", "price": f"{20 + k}.00", "currency": "USD",
                       "grader": None, "grade": None, "graded": False, "attribution": "exact", "identity_state": "EXACT",
                       "sold_at": f"2026-09-{20 + k % 9:02d}", "ingested_at": "2026-09-25T00:00:00+00:00",
                       "collected_at": collected, "fair_value_signal_eligible": True})
        prices.append({"canonical_card_id": cid, "card_variant_id": pr["card_variant_id"], "condition_id": "nm",
                       "market_price": 25.0, "captured_at": "2026-09-30", "source": "TCGPlayer"})
        obs.append({"card_variant_id": pr["card_variant_id"], "condition_id": "nm", "market_price": 25.0,
                    "captured_at": "2026-09-30", "source": "TCGPlayer", "currency": "USD"})
    return {"panel_fingerprint": panel["panel_fingerprint"], "identities": ids, "evidence": ev, "prices": prices,
            "observation_prices": obs, "fetched_at_utc": "x"}


def _replay(snapshot, panel):
    cutoff = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return shadow_run.replay(snapshot, panel, evaluation_date=date(2026, 9, 30), information_cutoff=cutoff,
                             generated_at=cutoff, snapshot_sha256="s")


def test_replay_is_deterministic_labelled_and_applies_the_availability_gate():
    panel = s2.load_panel()
    known = _synthetic_snapshot(panel, "2026-09-29T00:00:00+00:00")
    a, b = _replay(known, panel), _replay(copy.deepcopy(known), panel)
    assert a == b and a["label"] == "RETROSPECTIVE_AS_KNOWN_REPLAY_NOT_A_PUBLICATION"
    assert a["evidence_status"] == "AS_KNOWN_AT_CUTOFF_REPLAY_NOT_PROSPECTIVE"
    assert a["anchored_as_known"] == 207 and a["provider_calls"] == 0 and a["database_writes"] == 0
    leaked = _replay(_synthetic_snapshot(panel, "2026-10-02T00:00:00+00:00"), panel)  # collected AFTER the cutoff
    assert leaked["anchored_as_known"] == 0 and leaked["exclusion_totals"]["NOT_COLLECTED_AT_CUTOFF"] == 207 * 12


def test_replay_keeps_components_separate_and_never_blends():
    panel = s2.load_panel()
    result = _replay(_synthetic_snapshot(panel, "2026-09-29T00:00:00+00:00"), panel)
    card = result["cards"][0]
    assert {"anchor_usd", "market_usd", "structural_usd", "anchor_minus_market_pct", "structural_minus_market_pct",
            "anchor_minus_structural_pct"} <= set(card)
    assert not any("blend" in k or k == "fair_value" for k in card)
