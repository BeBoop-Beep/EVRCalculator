from datetime import datetime, timedelta, timezone

import backend.alerts.dispatcher as dispatcher


class _Result:
    def __init__(self, data, count=None): self.data, self.count = data, count


class _Query:
    def __init__(self, rows): self.rows, self.filters = list(rows), []
    def select(self, *a, **k): self.count_requested = k.get("count"); return self
    def eq(self, key, value): self.filters.append(("eq", key, value)); self.rows = [r for r in self.rows if r.get(key) == value]; return self
    def is_(self, key, value): self.filters.append(("is", key, value)); self.rows = [r for r in self.rows if r.get(key) is None]; return self
    def order(self, key, desc=False): self.rows.sort(key=lambda r: r.get(key, ""), reverse=desc); return self
    def limit(self, n): self.rows = self.rows[:n]; return self
    def update(self, values): self.values = values; return self
    def execute(self): return _Result(self.rows, len(self.rows))


class _Client:
    def __init__(self, rows): self.rows, self.last = rows, None
    def table(self, name): self.last = _Query(self.rows); return self.last


def test_dispatcher_ignores_suppressed_rows(monkeypatch):
    rows = [{"id": "a", "sent": False, "suppressed_at": None, "created_at": "2026-08-25T00:00:00Z"},
            {"id": "b", "sent": False, "suppressed_at": "2026-08-25T01:00:00Z", "created_at": "2026-04-01T00:00:00Z"}]
    client = _Client(rows); monkeypatch.setattr(dispatcher, "supabase", client)
    assert [row["id"] for row in dispatcher.fetch_pending_alerts(25)] == ["a"]
    assert ("is", "suppressed_at", "null") in client.last.filters


def test_health_check_never_returns_webhook_secret(monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(minutes=12)).isoformat()
    monkeypatch.setattr(dispatcher, "supabase", _Client([{"id": "a", "sent": False,
        "suppressed_at": None, "created_at": old}]))
    monkeypatch.setenv("ALERTS_ENABLED", "true")
    monkeypatch.setenv("SLACK_ALERT_WEBHOOK_URL", "https://secret.example/token")
    health = dispatcher.get_dispatcher_health()
    assert health["slack_webhook_configured"] is True
    assert "secret.example" not in str(health)
    assert health["oldest_pending_age_minutes"] >= 11


def test_slack_failure_does_not_mark_and_success_marks_once(monkeypatch):
    monkeypatch.setenv("ALERTS_ENABLED", "true"); monkeypatch.setenv("SLACK_ALERT_WEBHOOK_URL", "secret")
    monkeypatch.setattr(dispatcher, "fetch_pending_alerts", lambda n: [{"id": "a"}])
    monkeypatch.setattr(dispatcher, "get_dispatcher_health", lambda: {
        "pending_unsuppressed_count": 1, "oldest_pending_age_minutes": 1})
    marked = []
    monkeypatch.setattr(dispatcher, "mark_alert_sent", lambda alert_id: marked.append(alert_id) or True)
    monkeypatch.setattr(dispatcher, "send_slack_alert", lambda *a: False)
    assert dispatcher.send_pending_alerts()["failed_count"] == 1 and marked == []
    monkeypatch.setattr(dispatcher, "send_slack_alert", lambda *a: True)
    assert dispatcher.send_pending_alerts()["sent_count"] == 1 and marked == ["a"]


def test_formatter_allowlists_fields_and_excludes_secrets():
    result = dispatcher.format_slack_message({"severity": "critical", "alert_type": "x",
        "title": "blocked", "message": "action required", "payload": {
            "market_date": "2026-08-25", "status": "failed",
            "SUPABASE_SERVICE_ROLE_KEY": "db-secret", "webhook": "slack-secret", "raw_payload": {"huge": "secret"}}})
    rendered = str(result)
    assert "Market Date" in rendered and "failed" in rendered
    assert "db-secret" not in rendered and "slack-secret" not in rendered
