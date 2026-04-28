from backend.db.services import explore_rip_statistics_service as service


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_name, handlers, calls):
        self.table_name = table_name
        self.handlers = handlers
        self.calls = calls
        self.select_fields = None
        self.eq_filters = []
        self.in_filters = []
        self.order_fields = []
        self.limit_value = None

    def select(self, fields):
        self.select_fields = fields
        return self

    def eq(self, field, value):
        self.eq_filters.append((field, value))
        return self

    def in_(self, field, values):
        self.in_filters.append((field, list(values)))
        return self

    def order(self, field, desc=False):
        self.order_fields.append((field, desc))
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def execute(self):
        self.calls.append(self)
        handler = self.handlers[self.table_name]
        return _Result(handler(self))


class _Client:
    def __init__(self, handlers):
        self.handlers = handlers
        self.calls = []

    def table(self, table_name):
        if table_name not in self.handlers:
            raise AssertionError(f"Unexpected table requested: {table_name}")
        return _Query(table_name, self.handlers, self.calls)


def _build_handlers():
    return {
        "simulation_latest_by_target": lambda _q: [
            {
                "target_type": "set",
                "target_id": "set-1",
                "run_at": "2026-01-02T00:00:00Z",
                "pack_score": 71.0,
                "profit_score": 63.0,
                "safety_score": 68.0,
                "stability_score": 59.0,
                "pack_score_is_placeholder": False,
                "pack_cost": 4.99,
                "mean_value": 6.11,
                "median_value": 5.21,
                "roi_percent": 22.4,
                "prob_profit": 0.55,
                "prob_big_hit": 0.11,
            },
            {
                "target_type": "set",
                "target_id": "set-2",
                "run_at": "2026-01-03T00:00:00Z",
                "pack_score": 89.0,
                "profit_score": 82.0,
                "safety_score": 78.0,
                "stability_score": 74.0,
                "pack_score_is_placeholder": False,
                "pack_cost": 5.49,
                "mean_value": 7.18,
                "median_value": 5.88,
                "roi_percent": 30.7,
                "prob_profit": 0.63,
                "prob_big_hit": 0.15,
            },
        ],
        "sets": lambda q: [
            {"id": "set-1", "name": "Base Set", "release_date": "1999-01-09", "era_id": "era-1"},
            {"id": "set-2", "name": "Jungle", "release_date": "1999-06-16", "era_id": "era-1"},
        ],
        "eras": lambda q: [{"id": "era-1", "name": "Wizards of the Coast"}],
    }


def test_targets_endpoint_returns_sorted_targets_and_default(monkeypatch):
    handlers = _build_handlers()
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_rip_statistics_targets_payload(limit="150")

    assert payload["default_target"] == {"target_type": "set", "target_id": "set-2"}
    assert payload["targets"][0]["target_id"] == "set-2"
    assert payload["targets"][0]["name"] == "Jungle"
    assert payload["targets"][0]["era"] == "Wizards of the Coast"
    assert payload["meta"]["sources"]["simulation_latest_by_target"] == "OK"
    assert payload["meta"]["request"]["limit"] == 150


def test_targets_endpoint_without_rows_raises_404(monkeypatch):
    handlers = _build_handlers()
    handlers["simulation_latest_by_target"] = lambda _q: []
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    try:
        service.get_rip_statistics_targets_payload()
        assert False, "Expected ExploreRipStatisticsTargetsError"
    except service.ExploreRipStatisticsTargetsError as exc:
        assert exc.status_code == 404
        assert exc.code == "TARGETS_NOT_FOUND"


def test_set_enrichment_failure_falls_back_to_target_id(monkeypatch):
    handlers = _build_handlers()

    def _sets_fail(_q):
        raise RuntimeError("set metadata unavailable")

    handlers["sets"] = _sets_fail
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_rip_statistics_targets_payload()

    assert payload["targets"][0]["name"] == payload["targets"][0]["target_id"]
    assert payload["meta"]["sources"]["sets"] == "FAILED"
    assert any("set metadata" in warning.lower() for warning in payload["meta"]["warnings"])


def test_limit_is_safely_clamped(monkeypatch):
    handlers = _build_handlers()
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_rip_statistics_targets_payload(limit="999")

    assert payload["meta"]["request"]["limit"] == 200
    target_query = next(call for call in client.calls if call.table_name == "simulation_latest_by_target")
    assert target_query.limit_value == 200