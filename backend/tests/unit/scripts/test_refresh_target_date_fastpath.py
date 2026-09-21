from unittest.mock import patch

from backend.scripts import refresh_stale_public_snapshots as refresh


def _fresh(family):
    return refresh.FreshnessResult(
        family, False, "fresh", "2026-09-20T00:00:00+00:00", "2026-09-20", []
    )


def _global(_client, *, family):
    return _fresh(family)


def test_target_date_fast_result_proves_stale_on_date_mismatch():
    result = refresh._target_date_fast_result(
        "cards",
        snapshot_row={
            "market_date": "2026-09-19",
            "updated_at": "2026-09-20T03:00:00+00:00",
        },
        target_market_date="2026-09-20",
    )
    assert result is not None
    assert result.stale is True
    assert "2026-09-19" in result.reason
    assert "2026-09-20" in result.reason


def test_target_date_fast_result_defers_to_deep_audit_when_already_current():
    result = refresh._target_date_fast_result(
        "cards",
        snapshot_row={
            "market_date": "2026-09-20",
            "updated_at": "2026-09-20T03:00:00+00:00",
        },
        target_market_date="2026-09-20",
    )
    assert result is None


def test_build_plan_skips_expensive_dependency_scans_when_target_date_is_proven_stale():
    set_rows = [{"id": "set-1", "canonical_key": "alpha"}]
    cards_dates = {"set-1": {"market_date": "2026-09-19", "updated_at": "u1"}}
    market_dates = {"set-1": {"market_date": "2026-09-19", "updated_at": "u2"}}

    with patch.object(refresh, "_load_completed_scrape_set_ids", return_value={"set-1"}), patch.object(
        refresh, "_load_target_snapshot_market_dates", return_value=(cards_dates, market_dates)
    ), patch.object(
        refresh, "_cards_snapshot_staleness", side_effect=AssertionError("deep cards scan must be skipped")
    ), patch.object(
        refresh, "_market_snapshot_staleness", side_effect=AssertionError("deep market scan must be skipped")
    ), patch.object(
        refresh, "_set_page_snapshot_staleness", side_effect=AssertionError("deep page scan must be skipped")
    ), patch.object(refresh, "_global_snapshot_staleness", side_effect=_global):
        plans, rankings, validation, _checks = refresh._build_plan(
            object(),
            set_rows=set_rows,
            window="365d",
            target_market_date="2026-09-20",
        )

    assert len(plans) == 1
    assert plans[0].cards.stale is True
    assert plans[0].market_dashboard.stale is True
    assert plans[0].set_page.stale is True
    assert rankings.stale is False
    assert validation.stale is False


def test_build_plan_deep_audits_when_snapshot_dates_are_already_current():
    set_rows = [{"id": "set-1", "canonical_key": "alpha"}]
    cards_dates = {"set-1": {"market_date": "2026-09-20", "updated_at": "u1"}}
    market_dates = {"set-1": {"market_date": "2026-09-20", "updated_at": "u2"}}
    calls = []

    def cards(_client, set_id):
        calls.append(("cards", set_id))
        return _fresh("cards")

    def market(_client, set_id, window):
        calls.append(("market", set_id, window))
        return _fresh("market_dashboard")

    def page(_client, set_id):
        calls.append(("page", set_id))
        return _fresh("set_page")

    with patch.object(refresh, "_load_completed_scrape_set_ids", return_value={"set-1"}), patch.object(
        refresh, "_load_target_snapshot_market_dates", return_value=(cards_dates, market_dates)
    ), patch.object(refresh, "_cards_snapshot_staleness", side_effect=cards), patch.object(
        refresh, "_market_snapshot_staleness", side_effect=market
    ), patch.object(refresh, "_set_page_snapshot_staleness", side_effect=page), patch.object(
        refresh, "_global_snapshot_staleness", side_effect=_global
    ):
        refresh._build_plan(
            object(), set_rows=set_rows, window="365d", target_market_date="2026-09-20"
        )

    assert calls == [
        ("cards", "set-1"),
        ("market", "set-1", "365d"),
        ("page", "set-1"),
    ]


def test_build_plan_falls_back_to_deep_audit_when_bulk_preload_is_unreadable():
    set_rows = [{"id": "set-1", "canonical_key": "alpha"}]
    calls = []

    def cards(_client, set_id):
        calls.append("cards")
        return _fresh("cards")

    def market(_client, set_id, window):
        calls.append("market")
        return _fresh("market_dashboard")

    def page(_client, set_id):
        calls.append("page")
        return _fresh("set_page")

    with patch.object(refresh, "_load_completed_scrape_set_ids", return_value={"set-1"}), patch.object(
        refresh, "_load_target_snapshot_market_dates", return_value=None
    ), patch.object(refresh, "_cards_snapshot_staleness", side_effect=cards), patch.object(
        refresh, "_market_snapshot_staleness", side_effect=market
    ), patch.object(refresh, "_set_page_snapshot_staleness", side_effect=page), patch.object(
        refresh, "_global_snapshot_staleness", side_effect=_global
    ):
        refresh._build_plan(
            object(), set_rows=set_rows, window="365d", target_market_date="2026-09-20"
        )

    assert calls == ["cards", "market", "page"]
