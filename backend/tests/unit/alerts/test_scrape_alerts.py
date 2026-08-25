import backend.alerts.scrape_alerts as alerts


class _Result:
    def __init__(self, data): self.data = data


class _Table:
    def __init__(self): self.rows = []; self.query = []
    def select(self, *args): self.query = self.rows; return self
    def eq(self, key, value): self.query = [row for row in self.query if row.get(key) == value]; return self
    def limit(self, n): self.query = self.query[:n]; return self
    def insert(self, row): self.rows.append({"id": str(len(self.rows) + 1), **row}); self.query = [self.rows[-1]]; return self
    def execute(self): return _Result(list(self.query))


class _Client:
    def __init__(self): self.events = _Table()
    def table(self, name): return self.events


def test_repeated_stage_dedupe_key_inserts_exactly_once(monkeypatch):
    client = _Client(); monkeypatch.setattr(alerts, "supabase", client)
    first = alerts.queue_alert("stage", "title", "message", severity="info", dedupe_key="stage:2026-08-25")
    second = alerts.queue_alert("stage", "title", "message", severity="info", dedupe_key="stage:2026-08-25")
    assert first["id"] == second["id"]
    assert len(client.events.rows) == 1
