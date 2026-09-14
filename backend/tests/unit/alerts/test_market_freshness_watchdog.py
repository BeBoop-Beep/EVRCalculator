from datetime import datetime, timezone

import backend.alerts.market_freshness_watchdog as watchdog


NOW = datetime(2026, 8, 30, 15, 0, tzinfo=timezone.utc)  # 08:00 America/Phoenix
FRESH_DATES = {
    "accepted_market_quality": "2026-08-30",
    "set_value": "2026-08-30",
    "set_market_dashboard": "2026-08-30",
    "sealed_snapshot": "2026-08-30",
    "global_market_index": "2026-08-30",
}


def _state(batch=None, dates=None):
    return {"batch": batch, "authority_dates": dict(FRESH_DATES if dates is None else dates)}


class _Result:
    def __init__(self, data):
        self.data = data


class _ContractQuery:
    def __init__(self, client, table, rows):
        self.client = client
        self.table = table
        self.rows = list(rows)

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
    }

    def __init__(self):
        self.selections = {}
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
            "pokemon_market_date_quality": [{"market_date": "2026-08-30", "status": "READY"}],
            "pokemon_set_value_daily_history": [{"snapshot_date": "2026-08-30", "value_scope": "standard"}],
            "pokemon_set_market_dashboard_snapshot_latest": [{"latest_market_date": "2026-08-30"}],
            "pokemon_set_sealed_market_snapshot_latest": [{"market_date": "2026-08-30"}],
            "pokemon_market_index_daily_history": [{"market_date": "2026-08-30", "tcg": "pokemon"}],
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


def test_fresh_healthy_state_has_no_failures():
    assert watchdog.evaluate_watchdog_state(_state({"status": "complete"}), now=NOW) == []


def test_phoenix_rollover_does_not_use_utc_date(monkeypatch):
    # UTC has rolled to Aug 31, Phoenix is still Aug 30 at 17:30.
    now = datetime(2026, 8, 31, 0, 30, tzinfo=timezone.utc)
    failures = watchdog.evaluate_watchdog_state(_state({"status": "complete"}), now=now)
    assert failures == []


def test_loader_uses_canonical_dashboard_latest_market_date_column():
    client = _ContractClient()
    state = watchdog.load_watchdog_state(client, "2026-08-30")
    assert state["batch"]["id"] == 8
    assert state["authority_dates"] == FRESH_DATES
    assert client.selections["pokemon_set_market_dashboard_snapshot_latest"] == [("latest_market_date",)]


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
