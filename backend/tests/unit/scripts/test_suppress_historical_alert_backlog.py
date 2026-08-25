from backend.scripts.suppress_historical_alert_backlog import summarize, suppress


class _Result:
    def __init__(self, data): self.data = data


class _Query:
    def __init__(self, rows): self.rows, self.updated = rows, None
    def update(self, values): self.updated = values; return self
    def in_(self, key, ids): self.rows = [r for r in self.rows if r[key] in ids]; return self
    def eq(self, key, value): self.rows = [r for r in self.rows if r.get(key) == value]; return self
    def is_(self, key, value): self.rows = [r for r in self.rows if r.get(key) is None]; return self
    def execute(self):
        for row in self.rows: row.update(self.updated)
        return _Result(self.rows)


class _Client:
    def __init__(self, rows): self.rows = rows
    def table(self, name): return _Query(self.rows)


def test_historical_summary_preserves_breakdown_and_bounds():
    rows = [{"id": "1", "alert_type": "a", "severity": "error", "created_at": "2026-04-01"},
            {"id": "2", "alert_type": "a", "severity": "error", "created_at": "2026-05-01"}]
    report = summarize(rows, "2026-08-01T00:00:00+00:00")
    assert report["row_count"] == 2 and report["oldest"] == "2026-04-01"
    assert report["newest"] == "2026-05-01" and report["breakdown"] == {"a|error": 2}


def test_commit_suppresses_without_deleting_or_marking_sent():
    rows = [{"id": "1", "sent": False, "suppressed_at": None}]
    assert suppress(_Client(rows), rows, reason="operator approved") == 1
    assert rows[0]["sent"] is False and rows[0]["suppression_reason"] == "operator approved"
    assert rows[0]["suppressed_at"]
