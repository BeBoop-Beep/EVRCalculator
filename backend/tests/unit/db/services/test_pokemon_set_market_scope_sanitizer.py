from backend.db.services import pokemon_set_market_service as svc


def test_sanitizer_accepts_explicit_edition_scopes():
    for raw, want in [("standard", "standard"), ("unlimited", "unlimited"), ("first_edition", "first_edition"),
                      ("first-edition", "first_edition"), ("1st_edition", "first_edition"), ("shadowless", "shadowless"),
                      ("hits", "hits"), ("top10", "top10"), ("", "standard"), (None, "standard"), ("bogus", "standard")]:
        assert svc._sanitize_value_scope(raw) == want


class _Q:
    def __init__(self, log, rows):
        self.log, self.rows = log, rows

    def select(self, *a): return self
    def eq(self, c, v): self.log.append((c, v)); return self
    def order(self, *a, **k): return self
    def limit(self, *a): return self

    def execute(self):
        class R:
            pass
        r = R()
        r.data = self.rows
        return r


class _C:
    def __init__(self, rows, publishable=True, cert_rows=None):
        self.log, self.rows, self.tables = [], rows, []
        self.cert = [{"history_publishable": publishable}] if cert_rows is None else cert_rows

    def table(self, name):
        self.tables.append(name)
        if name == "pokemon_market_scoped_history_market_certification_v1":
            return _Q(self.log, self.cert)
        return _Q(self.log, self.rows)


def test_edition_history_reads_root_table_for_selected_scope_only(monkeypatch):
    client = _C([{"market_date": "2026-09-02", "set_value": 30.0}, {"market_date": "2026-09-01", "set_value": 20.0}])
    monkeypatch.setattr(svc, "_run_set_value_history_read", lambda fn, operation_name=None: fn(client))
    hist = svc._load_market_set_value_history("set-1", 30, "first_edition", [], {})
    assert client.tables == [
        "pokemon_market_scoped_history_market_certification_v1",
        "pokemon_market_root_set_value_daily_history_v2_shadow",
    ]
    assert ("market_scope", "first_edition") in client.log and ("certified_on_date", True) in client.log
    assert [p["setValue"] for p in hist] == [20.0, 30.0]
    assert all(p["valueScope"] == "first_edition" for p in hist)


def test_standard_history_does_not_touch_the_root_edition_table(monkeypatch):
    touched = []

    def fake(fn, operation_name=None):
        class C:
            def table(self, name):
                touched.append(name)
                raise RuntimeError("stop")
        return fn(C())

    monkeypatch.setattr(svc, "_run_set_value_history_read", fake)
    try:
        svc._load_market_set_value_history("set-1", 30, "standard", [], {})
    except Exception:
        pass
    assert "pokemon_market_root_set_value_daily_history_v2_shadow" not in touched


def test_withheld_or_unverifiable_scope_history_fails_closed(monkeypatch):
    rows = [{"market_date": "2026-09-01", "set_value": 20.0}]
    for client in (_C(rows, publishable=False), _C(rows, cert_rows=[])):
        monkeypatch.setattr(svc, "_run_set_value_history_read", lambda fn, operation_name=None, c=client: fn(c))
        warnings = []
        assert svc._load_market_set_value_history("set-1", 30, "first_edition", warnings, {}) == []
        assert warnings
        assert "pokemon_market_root_set_value_daily_history_v2_shadow" not in client.tables
