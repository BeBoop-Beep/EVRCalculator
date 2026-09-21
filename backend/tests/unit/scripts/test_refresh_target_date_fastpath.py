from types import SimpleNamespace
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



class _Transient522(Exception):
    code = 522


class _FastpathQuery:
    def __init__(self, client, table):
        self.client = client
        self.table_name = table

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def in_(self, _column, values):
        self.client.in_batches.append((self.table_name, list(values)))
        return self

    def execute(self):
        if self.client.fail:
            raise _Transient522("Cloudflare 522 connection timed out")
        return SimpleNamespace(data=list(self.client.rows.get(self.table_name, [])))


class _FastpathClient:
    def __init__(self, *, fail=False, rows=None):
        self.fail = fail
        self.rows = dict(rows or {})
        self.in_batches = []

    def table(self, name):
        return _FastpathQuery(self, name)


def test_completed_scrape_cohort_retries_transient_failure_with_fresh_client():
    initial = _FastpathClient(fail=True)
    replacement = _FastpathClient(
        rows={"scrape_jobs": [{"set_id": "set-1"}, {"set_id": "set-2"}]}
    )
    replacements = []

    def factory():
        replacements.append(True)
        return replacement

    result = refresh._load_completed_scrape_set_ids(
        initial,
        "2026-09-20",
        replacement_client_factory=factory,
        sleep=lambda _seconds: None,
    )

    assert result == {"set-1", "set-2"}
    assert replacements == [True]


def test_target_date_preload_retries_transient_failure_and_keeps_fastpath_available():
    initial = _FastpathClient(fail=True)
    replacement = _FastpathClient(
        rows={
            "pokemon_set_cards_snapshot_latest": [
                {
                    "set_id": "set-1",
                    "updated_at": "2026-09-20T12:00:00Z",
                    "pricing_market_date": "2026-09-19",
                    "snapshot_market_date": "2026-09-19",
                }
            ],
            "pokemon_set_market_dashboard_snapshot_latest": [
                {
                    "set_id": "set-1",
                    "latest_market_date": "2026-09-19",
                    "updated_at": "2026-09-20T12:00:00Z",
                }
            ],
        }
    )
    replacements = []

    def factory():
        replacements.append(True)
        return replacement

    loaded = refresh._load_target_snapshot_market_dates(
        initial,
        ["set-1"],
        window="365d",
        replacement_client_factory=factory,
        sleep=lambda _seconds: None,
    )

    assert loaded is not None
    cards, market = loaded
    assert cards["set-1"]["market_date"] == "2026-09-19"
    assert market["set-1"]["market_date"] == "2026-09-19"
    # Cards first attempt fails -> replacement. The Market preload starts with
    # the shared initial client and therefore needs its own fresh retry too.
    assert replacements == [True, True]


def test_completed_scrape_cohort_exhausted_transient_failure_falls_back_to_deep_audit():
    initial = _FastpathClient(fail=True)
    calls = []

    def factory():
        calls.append(True)
        return _FastpathClient(fail=True)

    result = refresh._load_completed_scrape_set_ids(
        initial,
        "2026-09-20",
        replacement_client_factory=factory,
        sleep=lambda _seconds: None,
    )

    assert result is None
    assert len(calls) == 2


def test_target_date_preload_uses_bounded_batches_to_avoid_statement_timeout():
    set_ids = [f"set-{i}" for i in range(45)]
    rows = {
        "pokemon_set_cards_snapshot_latest": [
            {
                "set_id": set_id,
                "updated_at": "2026-09-21T12:00:00Z",
                "pricing_market_date": "2026-09-20",
                "snapshot_market_date": "2026-09-20",
            }
            for set_id in set_ids
        ],
        "pokemon_set_market_dashboard_snapshot_latest": [
            {
                "set_id": set_id,
                "latest_market_date": "2026-09-20",
                "updated_at": "2026-09-21T12:00:00Z",
            }
            for set_id in set_ids
        ],
    }
    client = _FastpathClient(rows=rows)

    loaded = refresh._load_target_snapshot_market_dates(
        client,
        set_ids,
        window="365d",
        replacement_client_factory=lambda: client,
        sleep=lambda _seconds: None,
    )

    assert loaded is not None
    cards, market = loaded
    assert set(cards) == set(set_ids)
    assert set(market) == set(set_ids)

    cards_batches = [
        len(values)
        for table, values in client.in_batches
        if table == "pokemon_set_cards_snapshot_latest"
    ]
    market_batches = [
        len(values)
        for table, values in client.in_batches
        if table == "pokemon_set_market_dashboard_snapshot_latest"
    ]
    assert cards_batches == [20, 20, 5]
    assert market_batches == [20, 20, 5]
    assert max(cards_batches + market_batches) <= refresh.TARGET_DATE_PRELOAD_BATCH_SIZE
