import json
from datetime import date, timedelta

import pytest
from postgrest.exceptions import APIError

from backend.db.services import pokemon_explore_set_value_service as svc
from backend.db.services import public_read_retry
from backend.db.services.pokemon_explore_set_value_service import (
    ExploreSetValueUnavailable,
    build_global_set_value_row,
    compute_window_movements,
    read_explore_set_value_snapshot,
    read_market_explorer_snapshot,
)


class _Result:
    def __init__(self, data): self.data = data


class _SnapshotQuery:
    def __init__(self, row): self.row = row
    def select(self, *_args): return self
    def eq(self, *_args): return self
    def limit(self, *_args): return self
    def execute(self): return _Result([self.row])


class _SnapshotClient:
    def __init__(self, row): self.row = row
    def table(self, _name): return _SnapshotQuery(self.row)


@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    public_read_retry._reset_public_read_circuit_breaker_for_tests()
    yield
    public_read_retry._reset_public_read_circuit_breaker_for_tests()


def _transient_error(code="PGRST002"):
    return APIError({"message": "schema cache unavailable", "code": code, "hint": None, "details": None})


def _row():
    return {
        "market_date": "2026-08-28", "updated_at": "now", "payload_size_bytes": 1,
        "payload_json": {"marketOverview": {"raw": {"indexValue": 100}}, "sets": [], "meta": {}},
    }


class _FlakyOnceClient:
    """Fails the first .execute() with a transient error, then succeeds."""

    def __init__(self, row):
        self.row = row
        self.calls = 0

    def table(self, _name):
        return self

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        self.calls += 1
        if self.calls == 1:
            raise _transient_error()
        return _Result([self.row])


class _AlwaysNonTransientClient:
    def __init__(self):
        self.calls = 0

    def table(self, _name):
        return self

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        self.calls += 1
        raise ValueError("not a Supabase/PostgREST error at all")


def test_no_client_path_retries_a_transient_failure_and_recovers(monkeypatch):
    """B: run_public_read_with_retry wraps the whole logical read when no explicit
    client is passed, so a first-attempt transient PostgREST error is retried on
    a fresh client and the retry's result is returned."""
    flaky = _FlakyOnceClient(_row())
    monkeypatch.setattr(svc, "service_read_client", flaky)
    real_retry = public_read_retry.run_public_read_with_retry
    monkeypatch.setattr(
        svc, "run_public_read_with_retry",
        lambda op, **kwargs: real_retry(op, client_factory=lambda: flaky, **kwargs),
    )
    result = read_explore_set_value_snapshot()
    assert result["marketOverview"]["raw"]["indexValue"] == 100
    assert flaky.calls == 2


def test_no_client_path_does_not_retry_a_non_transient_failure(monkeypatch):
    """E: a deterministic/non-Supabase error must not be retried."""
    client = _AlwaysNonTransientClient()
    monkeypatch.setattr(svc, "service_read_client", client)
    with pytest.raises(ValueError):
        read_explore_set_value_snapshot()
    assert client.calls == 1


def test_market_reader_stays_slim_while_explorer_reader_preserves_published_segments():
    row = {"market_date": "2026-08-28", "updated_at": "now", "payload_size_bytes": 1,
           "payload_json": {"marketOverview": {
               "raw": {"indexValue": 100},
               "cardSegments": {"raw": {"segments": {"sir": {"available": True}}}},
               "sealedSegments": {"segments": {"boosterBox": {"available": True}}},
           }, "sets": [], "meta": {}}}
    client = _SnapshotClient(row)
    market = read_explore_set_value_snapshot(client=client)
    explorer = read_market_explorer_snapshot(client=client)
    assert "cardSegments" not in market["marketOverview"]
    assert "sealedSegments" not in market["marketOverview"]
    assert explorer["marketOverview"]["cardSegments"]["raw"]["segments"]["sir"]["available"] is True
    assert explorer["marketOverview"]["sealedSegments"]["segments"]["boosterBox"]["available"] is True


def history(days=40, start=100.0, set_id="set-1"):
    first = date(2026, 1, 1)
    return [{"set_id": set_id, "snapshot_date": (first + timedelta(days=i)).isoformat(), "set_value": start + i} for i in range(days)]


def prepared(rows):
    return [{"date": row["snapshot_date"], "setValue": row["set_value"]} for row in rows]


def pokemon_set():
    return {"id": "set-1", "canonical_key": "alpha", "name": "Alpha", "logo_image_url": "logo"}


def test_window_semantics_keep_exact_selected_period_and_partial_status():
    # The series moves exactly $1 per calendar day, so a window's amount IS its
    # elapsed-day span. 7D must move 7.0, not the 6.0 the retired inclusive
    # `days - 1` count produced.
    points = history(15)
    windows = compute_window_movements(points)
    assert windows["7D"]["amount"] == 7.0
    assert windows["7D"]["coverage"] == "full"
    # Fifteen days of history cannot reach a 30-day target, so this falls back
    # to the Set's first observation and SAYS SO rather than presenting 14 days
    # of movement as a 30D return.
    assert windows["30D"]["amount"] == 14.0
    assert windows["30D"]["coverage"] == "partial"
    assert windows["30D"]["isSinceFirstAvailable"] is True
    assert windows["30D"]["targetStartDate"] == "2025-12-16"


def test_set_market_window_targets_match_the_canonical_resolver():
    """THE PINNED MATRIX, shared with the global Market and the frontend.

    The Set Market used to own a second date formula. It now calls
    `resolve_market_window_target`, so a 7D on /Market -> Set Market, a 7D on
    that Set's Cards Market Index and a 7D on the global Market are the same
    seven elapsed calendar days by construction.
    """
    from backend.domain.pokemon.market_index import resolve_market_window_target

    expected = {"7D": "2026-08-18", "30D": "2026-07-26", "3M": "2026-05-27",
                "6M": "2026-02-26", "1Y": "2025-08-25"}
    first = date(2025, 1, 1)
    points = [
        {"date": (first + timedelta(days=i)).isoformat(), "value": 100.0}
        for i in range((date(2026, 8, 25) - first).days + 1)
    ]
    windows = compute_window_movements(points)
    for key, target in expected.items():
        assert windows[key]["targetStartDate"] == target, key
        assert windows[key]["startDate"] == target, key
        assert windows[key]["coverage"] == "full", key
        # And it is literally the canonical resolver's answer, not a lookalike.
        assert resolve_market_window_target("2026-08-25", key) == target, key
    # 1D stays the previous OBSERVED close; lifetime stays the Set's own start.
    assert windows["1D"]["startDate"] == "2026-08-24"
    assert windows["lifetime"]["targetStartDate"] is None
    assert windows["lifetime"]["startDate"] == "2025-01-01"


def test_fresh_365d_snapshot_wins_over_stale_30d_row():
    rows = history()
    target_date = rows[-1]["snapshot_date"]
    dashboards = [
        {"set_id": "set-1", "window_key": "30d", "latest_market_date": "2025-12-01", "set_value_histories_json": {"standard": [{"date": "2025-12-01", "setValue": 9999}]}},
        {"set_id": "set-1", "window_key": "365d", "latest_market_date": target_date, "set_value_histories_json": {"standard": prepared(rows)}},
    ]
    result = build_global_set_value_row([pokemon_set()], dashboards, {"set-1": rows}, target_market_date=target_date)
    published = result["payload_json"]["sets"][0]
    assert published["currentSetValue"] == rows[-1]["set_value"]
    assert published["setValueAsOf"] == target_date
    assert published["windows"]["30D"]["amount"] == 30.0


def test_compact_snapshot_reuses_prepared_set_market_index_and_movements():
    rows = history()
    target_date = rows[-1]["snapshot_date"]
    dashboard = {
        "set_id": "set-1",
        "window_key": "365d",
        "latest_market_date": target_date,
        "set_value_histories_json": {"standard": prepared(rows)},
        "cardsMarket": {"marketIndex": {
            "currentValue": 92.88,
            "baseValue": 100.0,
            "asOf": target_date,
            "movements": {"7D": {"available": True, "percent": -0.8}},
            "history": [{"date": target_date, "indexValue": 92.88}],
        }},
    }
    result = build_global_set_value_row(
        [pokemon_set()], [dashboard], {"set-1": rows}, target_market_date=target_date
    )
    index = result["payload_json"]["sets"][0]["marketIndex"]
    assert index == {
        "currentValue": 92.88,
        "baseValue": 100.0,
        "asOf": target_date,
        "movements": {"7D": {"available": True, "percent": -0.8}},
    }
    assert "history" not in index
    assert result["_diagnostics"]["dashboardMarketIndexAvailableCount"] == 1
    assert result["_diagnostics"]["publishedMarketIndexCount"] == 1
    assert result["_diagnostics"]["missingMarketIndexSetIds"] == []


def test_available_dashboard_index_cannot_silently_disappear():
    rows = history()
    target_date = rows[-1]["snapshot_date"]
    dashboard = {
        "set_id": "set-1", "window_key": "365d", "latest_market_date": target_date,
        "set_value_histories_json": {"standard": prepared(rows)},
        "cardsMarket": {"available": True, "marketIndex": {
            "currentValue": None, "asOf": target_date, "movements": {"7D": {"available": True}}
        }},
    }
    with pytest.raises(ExploreSetValueUnavailable) as caught:
        build_global_set_value_row([pokemon_set()], [dashboard], {"set-1": rows}, target_market_date=target_date)
    assert caught.value.diagnostics["missingMarketIndexSetIds"] == ["set-1"]


def test_all_twenty_two_available_dashboard_indices_survive_publication():
    sets, dashboards, histories = [], [], {}
    for index in range(22):
        set_id = f"set-{index}"
        rows = history(set_id=set_id)
        target_date = rows[-1]["snapshot_date"]
        sets.append({"id": set_id, "canonical_key": set_id, "name": f"Set {index}"})
        histories[set_id] = rows
        dashboards.append({
            "set_id": set_id, "window_key": "365d", "latest_market_date": target_date,
            "set_value_histories_json": {"standard": prepared(rows)},
            "cardsMarket": {"available": True, "marketIndex": {
                "currentValue": 90.0 + index, "baseValue": 100.0, "asOf": target_date,
                "movements": {"7D": {"available": True, "percent": -1.0}},
            }},
        })
    result = build_global_set_value_row(
        sets, dashboards, histories, target_market_date=target_date, publisher_build_sha="test-sha"
    )
    published = result["payload_json"]["sets"]
    assert len(published) == 22
    assert sum(1 for row in published if row.get("marketIndex")) == 22
    assert result["_diagnostics"]["dashboardMarketIndexAvailableCount"] == 22
    assert result["_diagnostics"]["publishedMarketIndexCount"] == 22
    assert result["_diagnostics"]["missingMarketIndexSetIds"] == []


def test_legitimately_unavailable_dashboard_index_remains_unavailable():
    rows = history()
    target_date = rows[-1]["snapshot_date"]
    dashboard = {
        "set_id": "set-1", "window_key": "365d", "latest_market_date": target_date,
        "set_value_histories_json": {"standard": prepared(rows)},
        "cardsMarket": {"available": False, "marketIndex": None},
    }
    result = build_global_set_value_row([pokemon_set()], [dashboard], {"set-1": rows}, target_market_date=target_date)
    assert "marketIndex" not in result["payload_json"]["sets"][0]
    assert result["_diagnostics"]["dashboardMarketIndexAvailableCount"] == 0
    assert result["_diagnostics"]["publishedMarketIndexCount"] == 0


def test_ascended_heroes_true_elapsed_seven_day_target():
    first = date(2026, 8, 1)
    points = [{"date": (first + timedelta(days=i)).isoformat(), "value": 100 + i} for i in range(27)]
    windows = compute_window_movements(points)
    assert points[-1]["date"] == "2026-08-27"
    assert windows["7D"]["targetStartDate"] == "2026-08-20"
    assert windows["7D"]["startDate"] == "2026-08-20"


def test_compact_snapshot_rejects_a_set_index_from_another_market_date():
    rows = history()
    target_date = rows[-1]["snapshot_date"]
    dashboard = {
        "set_id": "set-1",
        "window_key": "365d",
        "latest_market_date": target_date,
        "set_value_histories_json": {"standard": prepared(rows)},
        "cardsMarket": {"marketIndex": {"currentValue": 92.88, "asOf": "2025-01-01"}},
    }
    with pytest.raises(ExploreSetValueUnavailable, match="incomplete or disagree"):
        build_global_set_value_row(
            [pokemon_set()], [dashboard], {"set-1": rows}, target_market_date=target_date
        )


def test_publication_fails_closed_when_set_market_and_canonical_history_disagree():
    rows = history()
    target_date = rows[-1]["snapshot_date"]
    wrong = prepared(rows)
    wrong[-1]["setValue"] += 1
    with pytest.raises(ExploreSetValueUnavailable, match="disagree"):
        build_global_set_value_row([pokemon_set()], [{"set_id": "set-1", "window_key": "365d", "latest_market_date": target_date, "set_value_histories_json": {"standard": wrong}}], {"set-1": rows}, target_market_date=target_date)


def test_compact_contract_is_not_raw_dashboard_history():
    rows = history(131)
    target_date = rows[-1]["snapshot_date"]
    result = build_global_set_value_row([pokemon_set()], [{"set_id": "set-1", "window_key": "365d", "latest_market_date": target_date, "set_value_histories_json": {"standard": prepared(rows)}}], {"set-1": rows}, target_market_date=target_date)
    published = result["payload_json"]["sets"][0]
    assert len(published["trend"]) <= 48
    assert "setValueHistoriesByScope" not in json.dumps(result["payload_json"])
    assert published["trend"][-1] == [target_date, rows[-1]["set_value"]]
    assert len(published["recentDailyTrend"]) == 30
    assert published["recentDailyTrend"] == [[row["snapshot_date"], row["set_value"]] for row in rows[-30:]]
    assert result["payload_json"]["meta"]["recentDailyTrendPointLimit"] == 30


def test_recent_daily_trend_preserves_real_missing_dates_without_fabrication():
    rows = history(35)
    missing_date = rows[-5]["snapshot_date"]
    rows = [row for row in rows if row["snapshot_date"] != missing_date]
    target_date = rows[-1]["snapshot_date"]
    result = build_global_set_value_row([pokemon_set()], [{"set_id": "set-1", "window_key": "365d", "latest_market_date": target_date, "set_value_histories_json": {"standard": prepared(rows)}}], {"set-1": rows}, target_market_date=target_date)
    recent = result["payload_json"]["sets"][0]["recentDailyTrend"]
    assert len(recent) == 30
    assert missing_date not in [point[0] for point in recent]
    assert recent == sorted(recent)
    assert recent[-1] == [target_date, rows[-1]["set_value"]]


def _published_row(days=40):
    rows = history(days)
    target_date = rows[-1]["snapshot_date"]
    dashboards = [
        {
            "set_id": "set-1",
            "window_key": "365d",
            "latest_market_date": target_date,
            "set_value_histories_json": {"standard": prepared(rows)},
        }
    ]
    built = build_global_set_value_row(
        [pokemon_set()], dashboards, {"set-1": rows}, target_market_date=target_date
    )
    return built, built["payload_json"]["sets"][0], rows


def test_every_client_selectable_window_survives_into_the_snapshot():
    """The /Market pills are pure client-side slices, so all seven must ship."""
    from backend.db.services.pokemon_explore_set_value_service import WINDOWS

    _, published, _ = _published_row(days=400)

    assert set(published["windows"]) == {key for key, _ in WINDOWS}
    assert len(published["windows"]) == 7
    for key, window in published["windows"].items():
        assert isinstance(window["amount"], float), key
        assert isinstance(window["percent"], float), key
        assert window["startDate"] <= window["endDate"], key


def test_current_set_value_matches_the_canonical_final_history_point():
    _, published, rows = _published_row()

    assert published["currentSetValue"] == rows[-1]["set_value"]
    assert published["setValueAsOf"] == rows[-1]["snapshot_date"]
    assert published["historyEndDate"] == rows[-1]["snapshot_date"]
    assert published["historyStartDate"] == rows[0]["snapshot_date"]
    assert published["historyPointCount"] == len(rows)


def test_priced_and_total_card_counts_are_not_published_as_null_fields():
    """_points() normalizes to {date, value}, so those keys could only ever be None.

    Publishing them anyway advertised two permanently-null fields on every row.
    They have no consumer, so the compact snapshot omits them entirely rather
    than shipping a misleading contract.
    """
    _, published, _ = _published_row()

    assert "pricedCardCount" not in published
    assert "totalCardCount" not in published
    # Every field the ladder actually renders must carry a real value. `era` and
    # `symbolUrl` are genuinely optional set identity, so they are excluded.
    for key in ("setId", "name", "currentSetValue", "setValueAsOf", "windows", "trend"):
        assert published[key] is not None, key


def test_prepared_history_metadata_cannot_leak_into_the_compact_row():
    """Even when the dashboard history CARRIES the counts, they are not republished."""
    rows = history()
    target_date = rows[-1]["snapshot_date"]
    rich = [
        {**point, "pricedCardCount": 111, "totalCardCount": 222}
        for point in prepared(rows)
    ]
    dashboards = [
        {
            "set_id": "set-1",
            "window_key": "365d",
            "latest_market_date": target_date,
            "set_value_histories_json": {"standard": rich},
        }
    ]
    built = build_global_set_value_row(
        [pokemon_set()], dashboards, {"set-1": rows}, target_market_date=target_date
    )
    published = built["payload_json"]["sets"][0]

    assert "pricedCardCount" not in published
    assert "totalCardCount" not in published
    assert 111 not in json.loads(json.dumps(published)).values()


def test_snapshot_row_carries_the_columns_the_table_requires():
    built, published, _ = _published_row()

    assert built["tcg"] == "pokemon"
    assert built["scope"] == "market"
    assert built["market_date"] == published["setValueAsOf"]
    assert built["set_count"] == len(built["payload_json"]["sets"])
    assert built["payload_size_bytes"] > 0
    assert len(built["source_generation_fingerprint"]) == 64
    assert built["payload_json"]["meta"]["snapshot"]["marketDate"] == built["market_date"]


def test_snapshot_records_publisher_build_identity():
    rows = history()
    target_date = rows[-1]["snapshot_date"]
    dashboard = {"set_id": "set-1", "window_key": "365d", "latest_market_date": target_date,
                 "set_value_histories_json": {"standard": prepared(rows)}}
    built = build_global_set_value_row([pokemon_set()], [dashboard], {"set-1": rows},
                                        target_market_date=target_date, publisher_build_sha="abc123")
    assert built["payload_json"]["meta"]["publisherBuildSha"] == "abc123"
    assert built["_diagnostics"]["publisherBuildSha"] == "abc123"


def test_fingerprint_tracks_the_source_generation():
    """Same sources => same fingerprint (no write); changed value => new one."""
    rows = history()
    target_date = rows[-1]["snapshot_date"]

    def _build(history_rows):
        dashboards = [
            {
                "set_id": "set-1",
                "window_key": "365d",
                "latest_market_date": target_date,
                "set_value_histories_json": {"standard": prepared(history_rows)},
            }
        ]
        return build_global_set_value_row(
            [pokemon_set()], dashboards, {"set-1": history_rows}, target_market_date=target_date
        )["source_generation_fingerprint"]

    assert _build(rows) == _build(rows)

    moved = [dict(row) for row in rows]
    moved[-1]["set_value"] = moved[-1]["set_value"] + 1.0
    assert _build(moved) != _build(rows)


def test_edition_scoped_markets_publish_distinct_market_identity_without_derived_index():
    unlimited = history(days=10, start=100.0)
    first = history(days=10, start=200.0)
    target_date = unlimited[-1]["snapshot_date"]
    sets = [
        {
            "id": "set-1", "canonical_key": "jungle", "name": "Jungle - Unlimited",
            "base_set_name": "Jungle", "era": "Base", "market_scope": "unlimited",
            "market_key": "set:set-1:unlimited", "market_publication_ready": True,
        },
        {
            "id": "set-1", "canonical_key": "jungle", "name": "Jungle - 1st Edition",
            "base_set_name": "Jungle", "era": "Base", "market_scope": "first_edition",
            "market_key": "set:set-1:first_edition", "market_publication_ready": True,
        },
    ]
    built = build_global_set_value_row(
        sets,
        [],
        {
            "set:set-1:unlimited": unlimited,
            "set:set-1:first_edition": first,
        },
        target_market_date=target_date,
    )
    rows = {row["marketKey"]: row for row in built["payload_json"]["sets"]}
    assert set(rows) == {"set:set-1:unlimited", "set:set-1:first_edition"}
    assert rows["set:set-1:unlimited"]["marketScope"] == "unlimited"
    assert rows["set:set-1:first_edition"]["marketScope"] == "first_edition"
    assert rows["set:set-1:unlimited"]["currentSetValue"] == 109.0
    assert rows["set:set-1:first_edition"]["currentSetValue"] == 209.0
    # Fail closed: no normalized index is fabricated for scoped markets.
    assert "marketIndex" not in rows["set:set-1:unlimited"]
    assert "marketIndex" not in rows["set:set-1:first_edition"]
    assert built["set_count"] == 2


def test_incomplete_explicit_scope_remains_visible_but_unavailable():
    target_date = "2026-01-10"
    built = build_global_set_value_row(
        [{
            "id": "set-1", "canonical_key": "base", "name": "Base - Shadowless",
            "base_set_name": "Base", "era": "Base", "market_scope": "shadowless",
            "market_key": "set:set-1:shadowless", "market_publication_ready": True,
            "market_current_certification_status": "SCOPED_MARKET_INCOMPLETE",
        }],
        [],
        {"set:set-1:shadowless": []},
        target_market_date=target_date,
    )
    row = built["payload_json"]["sets"][0]
    assert row["marketKey"] == "set:set-1:shadowless"
    assert row["marketScope"] == "shadowless"
    assert row["valueStatus"] == "unavailable"
    assert row["currentSetValue"] is None
    assert "marketIndex" not in row


def _scoped(set_id, name, base, scope):
    return {
        "id": set_id, "canonical_key": base.lower(), "name": name, "base_set_name": base,
        "era": "Base", "market_scope": scope, "market_key": f"set:{set_id}:{scope}",
        "market_publication_ready": True,
    }


def _mixed_build(unlimited_start=100.0):
    unl = history(days=10, start=unlimited_start)
    first = history(days=10, start=200.0)
    modern = history(days=10, start=50.0)
    sets = [
        {"id": "modern", "canonical_key": "modern", "name": "Modern", "era": "SV", "market_publication_ready": True},
        _scoped("jungle", "Jungle - Unlimited", "Jungle", "unlimited"),
        _scoped("jungle", "Jungle - 1st Edition", "Jungle", "first_edition"),
        _scoped("base", "Base - Unlimited", "Base", "unlimited"),
        _scoped("base", "Base - 1st Edition", "Base", "first_edition"),
        _scoped("base", "Base - Shadowless", "Base", "shadowless"),
    ]
    hist = {
        "set:modern": modern,
        "set:jungle:unlimited": unl, "set:jungle:first_edition": first,
        "set:base:unlimited": unl, "set:base:first_edition": first, "set:base:shadowless": [],
    }
    return build_global_set_value_row(sets, [], hist, target_market_date=unl[-1]["snapshot_date"])


def test_standard_root_one_market_and_vintage_roots_expand_without_generic_row():
    built = _mixed_build()
    rows = built["payload_json"]["sets"]
    keys = [r["marketKey"] for r in rows]
    assert len(keys) == len(set(keys)) == 6
    assert "set:modern" in keys and next(r for r in rows if r["marketKey"] == "set:modern")["marketScope"] == "standard"
    assert {r["name"] for r in rows} >= {"Jungle - Unlimited", "Jungle - 1st Edition", "Base - Unlimited", "Base - 1st Edition", "Base - Shadowless"}
    assert not any(r["name"] in {"Jungle", "Base"} for r in rows)
    assert [r["setId"] for r in rows].count("base") == 3
    assert "set:jungle" not in keys and "set:base" not in keys


def test_unavailable_scope_stays_visible_and_never_zero():
    rows = {r["marketKey"]: r for r in _mixed_build()["payload_json"]["sets"]}
    shadowless = rows["set:base:shadowless"]
    assert shadowless["valueStatus"] == "unavailable"
    assert shadowless["currentSetValue"] is None


def test_scoped_market_cannot_borrow_setid_keyed_history():
    unl = history(days=10, start=100.0)
    built = build_global_set_value_row(
        [_scoped("jungle", "Jungle - Unlimited", "Jungle", "unlimited")], [],
        {"jungle": unl}, target_market_date=unl[-1]["snapshot_date"],
    )
    assert built["payload_json"]["sets"][0]["valueStatus"] == "unavailable"


def test_ranking_orders_market_rows_not_root_sets():
    rows = _mixed_build()["payload_json"]["sets"]
    values = [r["currentSetValue"] for r in rows if r["currentSetValue"] is not None]
    assert values == sorted(values, reverse=True)
    jungle = [r for r in rows if r["setId"] == "jungle"]
    assert len(jungle) == 2 and jungle[0]["currentSetValue"] != jungle[1]["currentSetValue"]
    assert rows[-1]["currentSetValue"] is None


def test_diagnostics_distinguish_root_and_market_counts():
    built = _mixed_build()
    d = built["_diagnostics"]
    assert d["eligibleRootSetCount"] == 3
    assert d["eligibleMarketCount"] == 6 == d["publishedMarketCount"]
    assert d["editionScopedMarketCount"] == 5
    assert d["eligibleSetCount"] == 6
    assert built["set_count"] == 6
    meta = built["payload_json"]["meta"]["publicationDiagnostics"]
    assert meta["eligibleRootSetCount"] == 3 and meta["editionScopedMarketCount"] == 5


def test_fingerprint_changes_when_scope_value_changes():
    assert _mixed_build(100.0)["source_generation_fingerprint"] != _mixed_build(101.0)["source_generation_fingerprint"]


def test_duplicate_market_identity_is_rejected():
    unl = history(days=10, start=100.0)
    row = _scoped("jungle", "Jungle - Unlimited", "Jungle", "unlimited")
    with pytest.raises(ExploreSetValueUnavailable):
        build_global_set_value_row([row, dict(row)], [], {"set:jungle:unlimited": unl}, target_market_date=unl[-1]["snapshot_date"])


def test_reader_never_preloads_generic_movers_for_scoped_first_row(monkeypatch):
    called = []
    monkeypatch.setattr(svc, "read_initial_selected_set_movers", lambda *a, **k: called.append(1) or {})
    row = {
        "market_date": "2026-08-28", "updated_at": "now", "payload_size_bytes": 1,
        "payload_json": {"sets": [{"setId": "s", "marketScope": "unlimited"}], "meta": {}},
    }
    payload = read_explore_set_value_snapshot(client=_SnapshotClient(row))
    assert not called and "initialSelectedSetMovers" not in payload
