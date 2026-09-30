from datetime import datetime, timezone

import backend.alerts.market_freshness_watchdog as watchdog


NOW = datetime(2026, 8, 30, 15, 0, tzinfo=timezone.utc)  # 08:00 America/Phoenix
HEALTHY_MOVERS_CONTRACT = {
    "builder": "pokemon_mixed_market_seven_day_movers_v3",
    "universe_contract": "serving_cards_and_sealed_exact_instruments_v1",
    "baseline_guard": "target_baseline_reversion_guard_v1",
    "card_constituent_count": 20315,
    "sealed_constituent_count": 1377,
    "card_candidate_count": 2370,
    "sealed_candidate_count": 419,
    "candidate_instrument_count": 2789,
    "published_card_count": 36,
    "published_sealed_count": 14,
    "published_instrument_count": 50,
    "card_count": 50,
    "eligible_set_count": 208,
}

FRESH_DATES = {
    "accepted_market_quality": "2026-08-30",
    "set_value": "2026-08-30",
    "set_market_dashboard": "2026-08-30",
    "sealed_snapshot": "2026-08-30",
    "global_market_index": "2026-08-30",
    "explore_set_value": "2026-08-30",
    "explore_card_movers": "2026-08-30",
    "explorer_v2": "2026-08-30",
    "card_market_current": "2026-08-30",
    "sealed_product_current": "2026-08-30",
}


def _state(batch=None, dates=None, movers_contract=None):
    return {
        "batch": batch,
        "authority_dates": dict(FRESH_DATES if dates is None else dates),
        "explore_card_movers_contract": dict(
            HEALTHY_MOVERS_CONTRACT if movers_contract is None else movers_contract
        ),
    }


class _Result:
    def __init__(self, data):
        self.data = data


class _ContractNotFilter:
    def __init__(self, query):
        self.query = query

    def is_(self, key, value):
        self.query._assert_column(key)
        assert value == "null"
        self.query.client.not_null_filters.append((self.query.table, key))
        self.query.rows = [row for row in self.query.rows if row.get(key) is not None]
        return self.query


class _ContractQuery:
    def __init__(self, client, table, rows):
        self.client = client
        self.table = table
        self.rows = list(rows)

    @property
    def not_(self):
        return _ContractNotFilter(self)

    def _assert_column(self, column):
        assert column in self.client.columns[self.table], f"unknown column {self.table}.{column}"

    def select(self, columns):
        selected = [column.strip() for column in str(columns).split(",") if column.strip()]
        for column in selected:
            self._assert_column(column)
        self.client.selections.setdefault(self.table, []).append(tuple(selected))
        return self

    def eq(self, key, value):
        self._assert_column(key)
        self.rows = [row for row in self.rows if row.get(key) == value]
        return self

    def order(self, key, desc=False):
        self._assert_column(key)
        self.rows.sort(key=lambda row: row.get(key) or "", reverse=desc)
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def execute(self):
        return _Result(self.rows)


class _ContractClient:
    columns = {
        "pokemon_scrape_batches": {
            "id", "market_date", "status", "created_at", "started_at", "updated_at", "completed_at",
        },
        "pokemon_market_date_quality": {"market_date", "status"},
        "pokemon_set_value_daily_history": {"snapshot_date", "value_scope"},
        "pokemon_set_market_dashboard_snapshot_latest": {"latest_market_date"},
        "pokemon_set_sealed_market_snapshot_latest": {"market_date"},
        "pokemon_market_index_daily_history": {"market_date", "tcg"},
        "pokemon_explore_set_value_snapshot_latest": {"market_date", "tcg", "scope"},
        "pokemon_explore_card_movers_snapshot_latest": {
            "market_date", "tcg", "scope", "window_key",
            "payload_json", "card_count", "eligible_set_count",
        },
        "pokemon_market_explorer_surface_serving_v2": {"singleton", "generation_id"},
        "pokemon_market_explorer_surface_generations_v2": {"generation_id", "market_date", "state"},
        "card_market_usd_latest": {"captured_at"},
        "sealed_product_market_usd_latest": {"captured_at"},
    }

    def __init__(self):
        self.selections = {}
        self.not_null_filters = []
        self.rows = {
            "pokemon_scrape_batches": [{
                "id": 8,
                "market_date": "2026-08-30",
                "status": "complete",
                "created_at": "2026-08-30T08:05:00Z",
                "started_at": "2026-08-30T08:05:00Z",
                "updated_at": "2026-08-30T09:00:00Z",
                "completed_at": "2026-08-30T09:00:00Z",
            }],
            "pokemon_market_date_quality": [
                {"market_date": None, "status": "READY"},
                {"market_date": "2026-08-30", "status": "READY"},
            ],
            "pokemon_set_value_daily_history": [
                {"snapshot_date": None, "value_scope": "standard"},
                {"snapshot_date": "2026-08-30", "value_scope": "standard"},
            ],
            "pokemon_set_market_dashboard_snapshot_latest": [
                {"latest_market_date": None},
                {"latest_market_date": "2026-08-30"},
            ],
            "pokemon_set_sealed_market_snapshot_latest": [
                {"market_date": None},
                {"market_date": "2026-08-30"},
            ],
            "pokemon_market_index_daily_history": [
                {"market_date": None, "tcg": "pokemon"},
                {"market_date": "2026-08-30", "tcg": "pokemon"},
            ],
            "pokemon_explore_set_value_snapshot_latest": [
                {"market_date": "2026-08-30", "tcg": "pokemon", "scope": "market"},
            ],
            "pokemon_explore_card_movers_snapshot_latest": [
                {
                    "market_date": "2026-08-30",
                    "tcg": "pokemon",
                    "scope": "explore",
                    "window_key": "7D",
                    "card_count": 50,
                    "eligible_set_count": 208,
                    "payload_json": {
                        "meta": {
                            "builder": "pokemon_mixed_market_seven_day_movers_v3",
                            "universeContractVersion": "serving_cards_and_sealed_exact_instruments_v1",
                            "baselineQualityGuardVersion": "target_baseline_reversion_guard_v1",
                            "coverage": {
                                "cardConstituentCount": 20315,
                                "sealedConstituentCount": 1377,
                                "cardCandidateCount": 2370,
                                "sealedCandidateCount": 419,
                                "candidateInstrumentCount": 2789,
                                "publishedCardCount": 36,
                                "publishedSealedCount": 14,
                                "publishedInstrumentCount": 50,
                            },
                        }
                    },
                },
            ],
            "pokemon_market_explorer_surface_serving_v2": [
                {"singleton": 1, "generation_id": "gen-current"},
            ],
            "pokemon_market_explorer_surface_generations_v2": [
                {"generation_id": "gen-current", "market_date": "2026-08-30", "state": "VALIDATED"},
            ],
            "card_market_usd_latest": [
                {"captured_at": "2026-08-30"},
            ],
            "sealed_product_market_usd_latest": [
                {"captured_at": "2026-08-30"},
            ],
        }

    def table(self, name):
        assert name in self.rows
        return _ContractQuery(self, name, self.rows[name])


def test_missing_daily_batch_after_deadline_is_critical(monkeypatch):
    monkeypatch.setenv("MARKET_BATCH_DEADLINE_AZ", "03:10")
    failures = watchdog.evaluate_watchdog_state(_state(), now=NOW)
    assert any(row["alert_type"] == "batch_not_created" for row in failures)


def test_stalled_batch_reports_batch_state(monkeypatch):
    monkeypatch.setenv("MARKET_BATCH_STALL_MINUTES", "120")
    batch = {"id": 9, "status": "running", "updated_at": "2026-08-30T10:00:00Z"}
    failures = watchdog.evaluate_watchdog_state(_state(batch), now=NOW)
    stalled = next(row for row in failures if row["alert_type"] == "batch_progress_stalled")
    assert stalled["batch_id"] == 9 and stalled["status"] == "running"


def test_stale_public_date_and_snapshot_divergence_are_independent(monkeypatch):
    dates = dict(FRESH_DATES, accepted_market_quality="2026-08-29", sealed_snapshot="2026-08-28")
    failures = watchdog.evaluate_watchdog_state(_state({"status": "complete"}, dates), now=NOW)
    assert {row["alert_type"] for row in failures} == {
        "market_publication_stale", "market_snapshot_date_divergence"
    }


def test_explorer_v2_has_bounded_convergence_grace_then_becomes_required(monkeypatch):
    monkeypatch.setenv("MARKET_EXPLORER_CONVERGENCE_DEADLINE_AZ", "10:30")
    dates = dict(FRESH_DATES, explorer_v2="2026-08-29")
    # NOW is 08:00 Phoenix: core publication is due, but bounded maintained-cache
    # convergence is still inside its explicit grace window.
    assert watchdog.evaluate_watchdog_state(_state({"status": "complete"}, dates), now=NOW) == []

    after_deadline = datetime(2026, 8, 30, 18, 0, tzinfo=timezone.utc)  # 11:00 Phoenix
    failures = watchdog.evaluate_watchdog_state(
        _state({"status": "complete"}, dates), now=after_deadline
    )
    divergence = next(
        row for row in failures if row["alert_type"] == "market_snapshot_date_divergence"
    )
    assert divergence["failure_class"] == "authority_date_mismatch"
    assert divergence["actual_dates"]["explorer_v2"] == "2026-08-29"


def test_missing_required_authority_date_fails_closed_after_publication_deadline():
    dates = dict(FRESH_DATES, sealed_snapshot=None)
    failures = watchdog.evaluate_watchdog_state(_state({"status": "complete"}, dates), now=NOW)
    missing = next(row for row in failures if row.get("failure_class") == "authority_date_missing")
    assert missing["alert_type"] == "market_snapshot_date_divergence"
    assert missing["missing_authorities"] == ["sealed_snapshot"]
    assert missing["actual_dates"]["sealed_snapshot"] is None


def test_fresh_healthy_state_has_no_failures():
    assert watchdog.evaluate_watchdog_state(_state({"status": "complete"}), now=NOW) == []


def test_current_by_date_but_cards_only_or_thirty_item_movers_fail_semantics():
    legacy = dict(
        HEALTHY_MOVERS_CONTRACT,
        builder="pokemon_raw_market_seven_day_movers_v2",
        universe_contract="serving_raw_exact_variant_v1",
        sealed_constituent_count=0,
        sealed_candidate_count=0,
        published_card_count=30,
        published_sealed_count=0,
        published_instrument_count=30,
        card_count=30,
        eligible_set_count=155,
    )
    failures = watchdog.evaluate_watchdog_state(
        _state({"status": "complete"}, movers_contract=legacy), now=NOW
    )
    failure = next(
        row for row in failures
        if row["alert_type"] == "market_snapshot_semantics_invalid"
    )
    assert failure["failure_class"] == "explore_card_movers_universe_contract"
    assert failure["expected_contract"]["universe_contract"] == "serving_cards_and_sealed_exact_instruments_v1"


def test_mixed_movers_fail_if_candidates_support_fifty_but_only_thirty_publish():
    short = dict(
        HEALTHY_MOVERS_CONTRACT,
        published_card_count=22,
        published_sealed_count=8,
        published_instrument_count=30,
        card_count=30,
    )
    failures = watchdog.evaluate_watchdog_state(
        _state({"status": "complete"}, movers_contract=short), now=NOW
    )
    assert any(
        row.get("failure_class") == "explore_card_movers_universe_contract"
        for row in failures
    )


def test_phoenix_rollover_does_not_use_utc_date(monkeypatch):
    # UTC has rolled to Aug 31, Phoenix is still Aug 30 at 17:30.
    now = datetime(2026, 8, 31, 0, 30, tzinfo=timezone.utc)
    failures = watchdog.evaluate_watchdog_state(_state({"status": "complete"}), now=now)
    assert failures == []


def test_loader_uses_canonical_columns_and_ignores_null_authority_dates():
    client = _ContractClient()
    state = watchdog.load_watchdog_state(client, "2026-08-30")
    assert state["batch"]["id"] == 8
    assert state["authority_dates"] == FRESH_DATES
    assert client.selections["pokemon_set_market_dashboard_snapshot_latest"] == [("latest_market_date",)]
    assert set(client.not_null_filters) == {
        ("pokemon_market_date_quality", "market_date"),
        ("pokemon_set_value_daily_history", "snapshot_date"),
        ("pokemon_set_market_dashboard_snapshot_latest", "latest_market_date"),
        ("pokemon_set_sealed_market_snapshot_latest", "market_date"),
        ("pokemon_market_index_daily_history", "market_date"),
        ("pokemon_explore_set_value_snapshot_latest", "market_date"),
        ("pokemon_explore_card_movers_snapshot_latest", "market_date"),
        ("card_market_usd_latest", "captured_at"),
        ("sealed_product_market_usd_latest", "captured_at"),
    }


def test_load_failure_is_structured_and_read_only_health_does_not_queue(monkeypatch):
    monkeypatch.setattr(watchdog, "load_watchdog_state", lambda *_: (_ for _ in ()).throw(RuntimeError("schema unavailable")))
    monkeypatch.setattr(watchdog, "queue_alert", lambda *a, **k: (_ for _ in ()).throw(AssertionError("queued")))
    report = watchdog.run_watchdog(client=object(), now=NOW, queue_failures=False)
    assert report["healthy"] is False
    assert report["execution_failed"] is True
    assert report["queued_or_deduplicated_count"] == 0
    assert report["failures"][0]["alert_type"] == "market_watchdog_execution_failed"
    assert report["failures"][0]["stage"] == "load_watchdog_state"
    assert "schema unavailable" in report["failures"][0]["error_summary"]


def test_load_failure_attempts_one_deduplicated_operational_alert(monkeypatch):
    monkeypatch.setattr(watchdog, "load_watchdog_state", lambda *_: (_ for _ in ()).throw(RuntimeError("database unavailable")))
    calls = []
    monkeypatch.setattr(watchdog, "queue_alert", lambda *a, **k: calls.append((a, k)) or None)
    report = watchdog.run_watchdog(client=object(), now=NOW, queue_failures=True)
    assert report["healthy"] is False
    assert report["execution_failed"] is True
    assert report["queued_or_deduplicated_count"] == 0
    assert len(calls) == 1
    assert calls[0][0][0] == "market_watchdog_execution_failed"
    assert calls[0][1]["dedupe_key"] == "market_watchdog_execution_failed:2026-08-30:load_watchdog_state"


def test_duplicate_watchdog_execution_uses_same_dedupe_key(monkeypatch):
    monkeypatch.setattr(watchdog, "load_watchdog_state", lambda *_: _state())
    keys = []
    monkeypatch.setattr(watchdog, "queue_alert", lambda *a, **k: keys.append(k["dedupe_key"]) or {"id": "same"})
    watchdog.run_watchdog(client=object(), now=NOW)
    watchdog.run_watchdog(client=object(), now=NOW)
    assert keys == ["batch_not_created:2026-08-30:missing_batch"] * 2
