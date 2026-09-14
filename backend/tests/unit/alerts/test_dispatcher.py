from datetime import datetime, timedelta, timezone

import backend.alerts.dispatcher as dispatcher


class _Result:
    def __init__(self, data, count=None):
        self.data, self.count = data, count


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)
        self.filters = []
        self.count_requested = None
        self.limit_value = None
        self.values = None

    def select(self, *a, **k):
        self.count_requested = k.get("count")
        return self

    def eq(self, key, value):
        self.filters.append(("eq", key, value))
        self.rows = [row for row in self.rows if row.get(key) == value]
        return self

    def is_(self, key, value):
        self.filters.append(("is", key, value))
        self.rows = [row for row in self.rows if row.get(key) is None]
        return self

    def order(self, key, desc=False):
        self.rows.sort(key=lambda row: row.get(key, "") or "", reverse=desc)
        return self

    def limit(self, n):
        self.limit_value = n
        return self

    def update(self, values):
        self.values = values
        return self

    def execute(self):
        data = self.rows[:self.limit_value] if self.limit_value is not None else self.rows
        count = len(self.rows) if self.count_requested else None
        return _Result(data, count)


class _Client:
    def __init__(self, rows):
        self.rows, self.last = rows, None

    def table(self, name):
        self.last = _Query(self.rows)
        return self.last


def _configure_healthy_dispatcher(monkeypatch):
    monkeypatch.setenv("ALERTS_ENABLED", "true")
    monkeypatch.setenv("SLACK_ALERT_WEBHOOK_URL", "configured-not-printed")
    monkeypatch.setenv("ALERT_SCHEDULES_REQUIRED", "false")
    monkeypatch.setenv("ALERT_BACKLOG_WARNING_COUNT", "20")
    monkeypatch.setenv("ALERT_BACKLOG_CRITICAL_AGE_MINUTES", "10")
    for name in ("APP_ENV", "ENVIRONMENT", "NODE_ENV"):
        monkeypatch.delenv(name, raising=False)


def test_dispatcher_ignores_suppressed_rows(monkeypatch):
    rows = [
        {"id": "a", "sent": False, "suppressed_at": None, "created_at": "2026-08-25T00:00:00Z"},
        {"id": "b", "sent": False, "suppressed_at": "2026-08-25T01:00:00Z", "created_at": "2026-04-01T00:00:00Z"},
    ]
    client = _Client(rows)
    monkeypatch.setattr(dispatcher, "supabase", client)
    assert [row["id"] for row in dispatcher.fetch_pending_alerts(25)] == ["a"]
    assert ("is", "suppressed_at", "null") in client.last.filters


def test_pending_queue_read_failure_is_not_reported_as_empty(monkeypatch):
    class _BrokenClient:
        def table(self, _name):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(dispatcher, "supabase", _BrokenClient())
    try:
        dispatcher.fetch_pending_alerts(25)
    except RuntimeError as exc:
        assert "could not be read" in str(exc)
    else:
        raise AssertionError("database failure must propagate to a nonzero dispatcher exit")


def test_health_check_never_returns_webhook_secret(monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(minutes=12)).isoformat()
    monkeypatch.setattr(
        dispatcher,
        "supabase",
        _Client([{"id": "a", "sent": False, "suppressed_at": None, "created_at": old}]),
    )
    _configure_healthy_dispatcher(monkeypatch)
    monkeypatch.setenv("SLACK_ALERT_WEBHOOK_URL", "https://secret.example/token")
    health = dispatcher.get_dispatcher_health()
    assert health["slack_webhook_configured"] is True
    assert "secret.example" not in str(health)
    assert health["oldest_pending_age_minutes"] >= 11


def test_empty_queue_is_healthy(monkeypatch):
    monkeypatch.setattr(dispatcher, "supabase", _Client([]))
    _configure_healthy_dispatcher(monkeypatch)
    health = dispatcher.get_dispatcher_health()
    assert health["pending_unsuppressed_count"] == 0
    assert health["backlog_healthy"] is True
    assert health["delivery_progress_healthy"] is True
    assert health["healthy"] is True


def test_fresh_pending_alert_is_healthy(monkeypatch):
    fresh = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    rows = [{"id": "a", "sent": False, "suppressed_at": None, "created_at": fresh}]
    monkeypatch.setattr(dispatcher, "supabase", _Client(rows))
    _configure_healthy_dispatcher(monkeypatch)
    health = dispatcher.get_dispatcher_health()
    assert health["oldest_pending_age_minutes"] < 10
    assert health["backlog_critical"] is False
    assert health["healthy"] is True


def test_old_pending_backlog_makes_health_unhealthy(monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    rows = [{"id": "a", "sent": False, "suppressed_at": None, "created_at": old}]
    monkeypatch.setattr(dispatcher, "supabase", _Client(rows))
    _configure_healthy_dispatcher(monkeypatch)
    health = dispatcher.get_dispatcher_health()
    assert health["backlog_critical"] is True
    assert health["backlog_healthy"] is False
    assert health["delivery_progress_healthy"] is False
    assert health["healthy"] is False


def test_recent_success_is_reported_but_does_not_hide_old_backlog(monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    recent = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    rows = [
        {"id": "pending", "sent": False, "suppressed_at": None, "created_at": old},
        {"id": "sent", "sent": True, "suppressed_at": None, "created_at": old, "sent_at": recent},
    ]
    monkeypatch.setattr(dispatcher, "supabase", _Client(rows))
    _configure_healthy_dispatcher(monkeypatch)
    health = dispatcher.get_dispatcher_health()
    assert health["recent_delivery"] is True
    assert health["delivery_progress_healthy"] is True
    assert health["backlog_healthy"] is False
    assert health["healthy"] is False


def test_recent_success_with_fresh_pending_queue_is_healthy(monkeypatch):
    fresh = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    recent = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    rows = [
        {"id": "pending", "sent": False, "suppressed_at": None, "created_at": fresh},
        {"id": "sent", "sent": True, "suppressed_at": None, "created_at": fresh, "sent_at": recent},
    ]
    monkeypatch.setattr(dispatcher, "supabase", _Client(rows))
    _configure_healthy_dispatcher(monkeypatch)
    health = dispatcher.get_dispatcher_health()
    assert health["recent_delivery"] is True
    assert health["backlog_healthy"] is True
    assert health["healthy"] is True


def test_high_but_fresh_backlog_is_warning_not_hard_failure(monkeypatch):
    fresh = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    rows = [
        {"id": str(index), "sent": False, "suppressed_at": None, "created_at": fresh}
        for index in range(3)
    ]
    monkeypatch.setattr(dispatcher, "supabase", _Client(rows))
    _configure_healthy_dispatcher(monkeypatch)
    monkeypatch.setenv("ALERT_BACKLOG_WARNING_COUNT", "2")
    health = dispatcher.get_dispatcher_health()
    assert health["pending_unsuppressed_count"] == 3
    assert health["backlog_warning"] is True
    assert health["backlog_critical"] is False
    assert health["healthy"] is True


def test_health_is_unhealthy_when_alerts_disabled_or_webhook_missing(monkeypatch):
    monkeypatch.setattr(dispatcher, "supabase", _Client([]))
    monkeypatch.setenv("ALERTS_ENABLED", "false")
    monkeypatch.setenv("ALERT_SCHEDULES_REQUIRED", "false")
    monkeypatch.delenv("SLACK_ALERT_WEBHOOK_URL", raising=False)
    assert dispatcher.get_dispatcher_health()["healthy"] is False
    monkeypatch.setenv("ALERTS_ENABLED", "true")
    assert dispatcher.get_dispatcher_health()["healthy"] is False


def test_required_schedule_health_is_fail_closed(monkeypatch):
    monkeypatch.setattr(dispatcher, "supabase", _Client([]))
    _configure_healthy_dispatcher(monkeypatch)
    monkeypatch.setenv("ALERT_SCHEDULES_REQUIRED", "true")
    monkeypatch.setenv("ALERT_DISPATCHER_SCHEDULED", "true")
    monkeypatch.setenv("MARKET_FRESHNESS_WATCHDOG_SCHEDULED", "false")
    assert dispatcher.get_dispatcher_health()["healthy"] is False
    monkeypatch.setenv("MARKET_FRESHNESS_WATCHDOG_SCHEDULED", "true")
    assert dispatcher.get_dispatcher_health()["healthy"] is True


def test_slack_failure_does_not_mark_and_success_marks_once(monkeypatch):
    monkeypatch.setenv("ALERTS_ENABLED", "true")
    monkeypatch.setenv("SLACK_ALERT_WEBHOOK_URL", "secret")
    monkeypatch.setattr(dispatcher, "fetch_pending_alerts", lambda n: [{"id": "a"}])
    monkeypatch.setattr(dispatcher, "get_dispatcher_health", lambda: {
        "pending_unsuppressed_count": 1, "oldest_pending_age_minutes": 1})
    marked = []
    monkeypatch.setattr(dispatcher, "mark_alert_sent", lambda alert_id: marked.append(alert_id) or True)
    monkeypatch.setattr(dispatcher, "send_slack_alert", lambda *a: False)
    assert dispatcher.send_pending_alerts()["failed_count"] == 1 and marked == []
    monkeypatch.setattr(dispatcher, "send_slack_alert", lambda *a: True)
    assert dispatcher.send_pending_alerts()["sent_count"] == 1 and marked == ["a"]


def test_disabled_dispatcher_never_fetches(monkeypatch):
    monkeypatch.setenv("ALERTS_ENABLED", "false")
    monkeypatch.setattr(
        dispatcher,
        "fetch_pending_alerts",
        lambda _n: (_ for _ in ()).throw(AssertionError("fetched")),
    )
    assert dispatcher.send_pending_alerts()["fetched_count"] == 0


def test_enabled_dispatcher_rejects_missing_webhook(monkeypatch):
    monkeypatch.setenv("ALERTS_ENABLED", "true")
    monkeypatch.delenv("SLACK_ALERT_WEBHOOK_URL", raising=False)
    try:
        dispatcher.send_pending_alerts()
    except ValueError as exc:
        assert "SLACK_ALERT_WEBHOOK_URL" in str(exc)
    else:
        raise AssertionError("missing webhook must fail")


def test_http_200_is_success_and_non_200_is_failure(monkeypatch):
    class _Response:
        def __init__(self, status):
            self.status_code, self.text = status, "response"

    monkeypatch.setattr(dispatcher.requests, "post", lambda *a, **k: _Response(200))
    assert dispatcher.send_slack_alert({"id": "a"}, "configured-secret") is True
    monkeypatch.setattr(dispatcher.requests, "post", lambda *a, **k: _Response(503))
    assert dispatcher.send_slack_alert({"id": "a"}, "configured-secret") is False


def test_formatter_allowlists_fields_and_excludes_secrets():
    result = dispatcher.format_slack_message({
        "severity": "critical",
        "alert_type": "x",
        "title": "blocked",
        "message": "action required",
        "payload": {
            "market_date": "2026-08-25",
            "status": "failed",
            "SUPABASE_SERVICE_ROLE_KEY": "db-secret",
            "webhook": "slack-secret",
            "raw_payload": {"huge": "secret"},
        },
    })
    rendered = str(result)
    assert "Market Date" in rendered and "failed" in rendered
    assert "db-secret" not in rendered and "slack-secret" not in rendered
