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


def test_duplicate_watchdog_execution_uses_same_dedupe_key(monkeypatch):
    monkeypatch.setattr(watchdog, "load_watchdog_state", lambda *_: _state())
    keys = []
    monkeypatch.setattr(watchdog, "queue_alert", lambda *a, **k: keys.append(k["dedupe_key"]) or {"id": "same"})
    watchdog.run_watchdog(client=object(), now=NOW)
    watchdog.run_watchdog(client=object(), now=NOW)
    assert keys == ["batch_not_created:2026-08-30:missing_batch"] * 2
