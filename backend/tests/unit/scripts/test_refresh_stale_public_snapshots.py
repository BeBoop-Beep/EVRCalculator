from datetime import datetime, timedelta, timezone

from backend.scripts import refresh_stale_public_snapshots as refresh


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _row(set_id: str, set_updated: str, rankings_embedded: str, *, include_ranks: bool = True):
    summary = {
        "target_id": set_id,
        "set_id": set_id,
        "name": "Set",
    }
    if include_ranks:
        summary["pack_rank"] = 3
        summary["profit_rank"] = 4
    return {
        "set_id": set_id,
        "updated_at": set_updated,
        "payload_json": {
            "summary": summary,
            "meta": {
                "snapshotCompleteness": {
                    "explore_rankings_snapshot_updated_at": rankings_embedded,
                },
                "sectionFreshness": {
                    "decisionSignalRanks": {
                        "status": "fresh",
                    }
                },
                "warnings": [],
                "sources": {"simulation_input_cards": "OK"},
            },
            "top_hits": [{"card_name": "Chase"}],
        },
    }


def test_verify_set_page_no_false_positive_when_set_page_newer_than_rankings_and_ranks_present(monkeypatch):
    t0 = datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc)
    rankings_updated = _iso(t0)
    set_updated = _iso(t0 + timedelta(minutes=12))

    monkeypatch.setattr(
        refresh,
        "_read_snapshot_row",
        lambda _client, table, _select_fields, _filters: (
            {"updated_at": rankings_updated} if table == "pokemon_explore_rankings_snapshot_latest" else _row("set-1", set_updated, rankings_updated)
        ),
    )
    monkeypatch.setattr(refresh, "_has_known_stale_warning", lambda _warnings: False)
    monkeypatch.setattr(refresh, "_source_rows_exist_for_set_page", lambda _client, _set_id: True)

    problems = refresh._verify_set_page(None, {"id": "set-1", "canonical_key": "whiteFlare"}, rankings_updated_at=rankings_updated)

    assert problems == []


def test_verify_set_page_stale_when_rankings_rebuilt_after_set_page(monkeypatch):
    t0 = datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc)
    set_updated = _iso(t0)
    rankings_updated = _iso(t0 + timedelta(minutes=15))

    monkeypatch.setattr(
        refresh,
        "_read_snapshot_row",
        lambda _client, table, _select_fields, _filters: (
            {"updated_at": rankings_updated} if table == "pokemon_explore_rankings_snapshot_latest" else _row("set-1", set_updated, set_updated)
        ),
    )
    monkeypatch.setattr(refresh, "_has_known_stale_warning", lambda _warnings: False)
    monkeypatch.setattr(refresh, "_source_rows_exist_for_set_page", lambda _client, _set_id: True)

    problems = refresh._verify_set_page(None, {"id": "set-1", "canonical_key": "whiteFlare"}, rankings_updated_at=rankings_updated)

    assert any("rankings snapshot rebuilt after set page snapshot" in problem for problem in problems)


def test_verify_set_page_stale_when_rank_fields_missing(monkeypatch):
    t0 = datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc)
    rankings_updated = _iso(t0)

    monkeypatch.setattr(
        refresh,
        "_read_snapshot_row",
        lambda _client, table, _select_fields, _filters: (
            {"updated_at": rankings_updated}
            if table == "pokemon_explore_rankings_snapshot_latest"
            else _row("set-1", rankings_updated, rankings_updated, include_ranks=False)
        ),
    )
    monkeypatch.setattr(refresh, "_has_known_stale_warning", lambda _warnings: False)
    monkeypatch.setattr(refresh, "_source_rows_exist_for_set_page", lambda _client, _set_id: True)

    problems = refresh._verify_set_page(None, {"id": "set-1", "canonical_key": "whiteFlare"}, rankings_updated_at=rankings_updated)

    assert any("rank fields missing" in problem for problem in problems)


def _market_row(*, updated_at="2026-06-21T00:00:00+00:00", latest_market_date="2026-06-20"):
    histories = {
        "standard": [{"date": "2026-06-20", "setValue": 100}],
        "hits": [{"date": "2026-06-20", "setValue": 50}],
        "top10": [{"date": "2026-06-20", "setValue": 25}],
    }
    return {
        "set_id": "set-1",
        "window_key": "365d",
        "updated_at": updated_at,
        "latest_market_date": latest_market_date,
        "set_value_histories_json": histories,
        "payload_json": {
            "latestMarketDate": latest_market_date,
            "setValueHistoriesByScope": histories,
            "meta": {
                "snapshot": {"type": "pokemon_set_market_dashboard"},
                "setValueHistoryLatestDateByScope": {
                    "standard": "2026-06-20",
                    "hits": "2026-06-20",
                    "top10": "2026-06-20",
                },
            },
        },
    }


def test_market_dashboard_stale_when_raw_set_value_snapshot_date_newer(monkeypatch):
    monkeypatch.setattr(refresh, "_latest_for_market_dashboard", lambda _client, _set_id: (None, []))

    def latest_by_scope(_client, _set_id, *, column):
        if column == "updated_at":
            return {"standard": "2026-06-20T00:00:00+00:00", "hits": "2026-06-20T00:00:00+00:00", "top10": "2026-06-20T00:00:00+00:00"}, []
        return {"standard": "2026-06-24", "hits": "2026-06-24", "top10": "2026-06-23"}, []

    monkeypatch.setattr(refresh, "_latest_set_value_history_by_scope", latest_by_scope)
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_args, **_kwargs: _market_row())

    result = refresh._market_snapshot_staleness(None, "set-1", "365d")

    assert result.stale is True
    assert result.family == "market_dashboard"
    assert "latest_market_date" in result.reason


def test_market_dashboard_missing_row_is_stale(monkeypatch):
    monkeypatch.setattr(refresh, "_latest_for_market_dashboard", lambda _client, _set_id: (None, []))
    monkeypatch.setattr(
        refresh,
        "_latest_set_value_history_by_scope",
        lambda _client, _set_id, *, column: ({"standard": "2026-06-25", "hits": None, "top10": None}, []),
    )
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_args, **_kwargs: None)

    result = refresh._market_snapshot_staleness(None, "set-1", "365d")

    assert result.stale is True
    assert result.reason == "snapshot row missing"


def test_market_dashboard_stale_when_one_scope_history_lags(monkeypatch):
    monkeypatch.setattr(refresh, "_latest_for_market_dashboard", lambda _client, _set_id: (None, []))

    def latest_by_scope(_client, _set_id, *, column):
        if column == "updated_at":
            return {"standard": "2026-06-20T00:00:00+00:00", "hits": "2026-06-20T00:00:00+00:00", "top10": "2026-06-20T00:00:00+00:00"}, []
        return {"standard": "2026-06-25", "hits": "2026-06-25", "top10": "2026-06-25"}, []

    row = _market_row(latest_market_date="2026-06-25")
    row["set_value_histories_json"]["standard"] = [{"date": "2026-06-25", "setValue": 100}]
    row["set_value_histories_json"]["hits"] = [{"date": "2026-06-20", "setValue": 50}]
    row["set_value_histories_json"]["top10"] = [{"date": "2026-06-25", "setValue": 25}]
    row["payload_json"]["meta"]["setValueHistoryLatestDateByScope"] = {
        "standard": "2026-06-25",
        "hits": "2026-06-20",
        "top10": "2026-06-25",
    }

    monkeypatch.setattr(refresh, "_latest_set_value_history_by_scope", latest_by_scope)
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_args, **_kwargs: row)

    result = refresh._market_snapshot_staleness(None, "set-1", "365d")

    assert result.stale is True
    assert result.reason == "hits set value history newer than dashboard history"


def test_market_dashboard_stale_when_raw_set_value_updated_after_dashboard(monkeypatch):
    monkeypatch.setattr(refresh, "_latest_for_market_dashboard", lambda _client, _set_id: (None, []))

    def latest_by_scope(_client, _set_id, *, column):
        if column == "updated_at":
            return {"standard": "2026-06-22T00:00:00+00:00", "hits": "2026-06-25T00:00:00+00:00", "top10": "2026-06-22T00:00:00+00:00"}, []
        return {"standard": "2026-06-20", "hits": "2026-06-20", "top10": "2026-06-20"}, []

    monkeypatch.setattr(refresh, "_latest_set_value_history_by_scope", latest_by_scope)
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_args, **_kwargs: _market_row(updated_at="2026-06-24T00:00:00+00:00"))

    result = refresh._market_snapshot_staleness(None, "set-1", "365d")

    assert result.stale is True
    assert result.reason == "set value daily history updated after market dashboard"


def test_build_plan_all_reports_multiple_stale_market_dashboards(monkeypatch):
    monkeypatch.setattr(refresh, "_cards_snapshot_staleness", lambda _client, set_id: refresh.FreshnessResult("cards", False, "fresh"))
    monkeypatch.setattr(refresh, "_set_page_snapshot_staleness", lambda _client, set_id: refresh.FreshnessResult("set_page", False, "fresh"))
    monkeypatch.setattr(
        refresh,
        "_market_snapshot_staleness",
        lambda _client, set_id, window: refresh.FreshnessResult(
            "market_dashboard",
            set_id in {"set-1", "set-2"},
            "stale" if set_id in {"set-1", "set-2"} else "fresh",
        ),
    )
    monkeypatch.setattr(refresh, "_global_snapshot_staleness", lambda _client, *, family: refresh.FreshnessResult(family, False, "fresh"))

    plans, rankings, validation, _source_checks = refresh._build_plan(
        None,
        set_rows=[{"id": "set-1"}, {"id": "set-2"}, {"id": "set-3"}],
        window="365d",
    )

    assert [plan.set_row["id"] for plan in plans if plan.market_dashboard.stale] == ["set-1", "set-2"]
    assert rankings.stale is False
    assert validation.stale is False


def test_market_dashboard_staleness_does_not_plan_set_page_or_desirability_rebuild(monkeypatch):
    rebuilt = []
    monkeypatch.setattr(refresh, "build_set_page_snapshot_row", lambda *_args, **_kwargs: rebuilt.append("set_page"))
    summary = refresh.RefreshSummary()
    plan = refresh.SetRefreshPlan(
        set_row={"id": "set-1", "canonical_key": "shroudedFable"},
        cards=refresh.FreshnessResult("cards", False, "fresh", "2026-06-24T00:00:00+00:00"),
        market_dashboard=refresh.FreshnessResult("market_dashboard", True, "set value daily history date newer than latest_market_date", "2026-06-24T00:00:00+00:00"),
        set_page=refresh.FreshnessResult("set_page", False, "fresh", "2026-06-24T00:00:00+00:00"),
    )

    refresh._maybe_rebuild_set_page(None, plan, rankings_updated_at=None, commit=True, summary=summary)

    assert rebuilt == []
    assert summary.rebuilt_sets["set_page"] == []


def test_desirability_validation_freshness_does_not_depend_on_market_dashboard(monkeypatch):
    tables = []

    def latest_timestamp(_client, *, table, timestamp_columns, filters=(), in_filters=()):
        tables.append(table)
        return None, [f"{table}: ok"]

    monkeypatch.setattr(refresh, "_latest_timestamp", latest_timestamp)

    refresh._latest_for_desirability_validation(None)

    assert "pokemon_set_market_dashboard_snapshot_latest" not in tables
