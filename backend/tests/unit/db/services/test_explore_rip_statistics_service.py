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
        "explore_rip_statistics_latest": lambda _q: [
            {
                "set_id": "set-1",
                "run_at": "2026-01-02T00:00:00Z",
                "relative_pack_score": 66.0,
                "pack_score": 71.0,
                "pack_rank": 8,
                "pack_tier": "A",
                "profit_score": 63.0,
                "profit_rank": 11,
                "profit_tier": "B",
                "safety_score": 68.0,
                "safety_rank": 9,
                "safety_tier": "A",
                "stability_score": 59.0,
                "stability_rank": 14,
                "stability_tier": "B",
                "pack_score_is_placeholder": False,
                "pack_cost": 4.99,
                "mean_value": 6.11,
                "median_value": 5.21,
                "roi_percent": 22.4,
                "prob_profit": 0.55,
                "prob_big_hit": 0.11,
                "p95_value_to_cost_ratio": 2.2,
                "p99_value_to_cost_ratio": 4.8,
            },
            {
                "set_id": "set-2",
                "run_at": "2026-01-03T00:00:00Z",
                "relative_pack_score": 82.0,
                "pack_score": 89.0,
                "pack_rank": 3,
                "pack_tier": "S",
                "profit_score": 82.0,
                "profit_rank": 4,
                "profit_tier": "S",
                "safety_score": 78.0,
                "safety_rank": 5,
                "safety_tier": "A",
                "stability_score": 74.0,
                "stability_rank": 6,
                "stability_tier": "A",
                "pack_score_is_placeholder": False,
                "pack_cost": 5.49,
                "mean_value": 7.18,
                "median_value": 5.88,
                "roi_percent": 30.7,
                "prob_profit": 0.63,
                "prob_big_hit": 0.15,
                "p95_value_to_cost_ratio": 2.9,
                "p99_value_to_cost_ratio": 7.5,
            },
        ],
        "sets": lambda q: [
            {
                "id": "set-1",
                "name": "Base Set",
                "release_date": "1999-01-09",
                "era_id": "era-1",
                "logo_image_url": "https://img.example/base-logo.png",
                "symbol_image_url": "https://img.example/base-symbol.png",
                "hero_image_url": "https://img.example/base-hero.png",
            },
            {
                "id": "set-2",
                "name": "Jungle",
                "release_date": "1999-06-16",
                "era_id": "era-1",
                "logo_image_url": "https://img.example/jungle-logo.png",
                "symbol_image_url": "https://img.example/jungle-symbol.png",
                "hero_image_url": None,
            },
        ],
        "eras": lambda q: [{"id": "era-1", "name": "Wizards of the Coast"}],
    }


def test_targets_endpoint_returns_sorted_targets_and_default(monkeypatch):
    handlers = _build_handlers()
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    def _mock_interpretation(summary_row):
        if summary_row.get("pack_score") == 89.0:
            return {"meta": {"packScore": {"label": "Strong value, some path sensitivity", "severity": "caution"}}}
        return {"meta": {"packScore": {"label": "Good value, easy misses", "severity": "neutral"}}}

    monkeypatch.setattr(service, "build_rip_interpretation", _mock_interpretation)

    payload = service.get_rip_statistics_targets_payload(limit="150")
    targets_by_id = {target["target_id"]: target for target in payload["targets"]}

    assert payload["default_target"] == {"target_type": "set", "target_id": "set-2"}
    assert payload["targets"][0]["target_id"] == "set-1"
    assert targets_by_id["set-2"]["name"] == "Jungle"
    assert targets_by_id["set-2"]["era"] == "Wizards of the Coast"
    assert targets_by_id["set-2"]["logo_image_url"] == "https://img.example/jungle-logo.png"
    assert targets_by_id["set-2"]["symbol_image_url"] == "https://img.example/jungle-symbol.png"
    assert targets_by_id["set-2"]["hero_image_url"] is None
    assert targets_by_id["set-2"]["leaderboard_label"] == "Strong value"
    assert targets_by_id["set-2"]["canonical_recommendation_header"] == "Strong value, some path sensitivity"
    assert targets_by_id["set-2"]["pack_tier"] == "S"
    assert targets_by_id["set-1"]["pack_tier"] == "A"
    assert targets_by_id["set-2"]["biggest_upside_score"] is not None
    assert targets_by_id["set-2"]["relative_biggest_upside_score"] is not None
    assert targets_by_id["set-2"]["biggest_upside_rank"] == 1
    assert targets_by_id["set-2"]["biggest_upside_tier"] == "S"
    assert targets_by_id["set-2"]["relative_average_return_score"] is not None
    assert targets_by_id["set-2"]["relative_average_return_score"] > targets_by_id["set-1"]["relative_average_return_score"]
    assert targets_by_id["set-2"]["relative_p99_value_to_cost_score"] is not None
    assert targets_by_id["set-2"]["relative_p99_value_to_cost_score"] > targets_by_id["set-1"]["relative_p99_value_to_cost_score"]
    assert targets_by_id["set-2"]["p99_value_to_cost_rank"] == 1
    assert targets_by_id["set-2"]["p99_value_to_cost_tier"] == "S"
    assert targets_by_id["set-1"]["p99_value_to_cost_ratio"] == 4.8
    assert payload["meta"]["sources"]["explore_rip_statistics_latest"] == "OK"
    assert payload["meta"]["sources"]["simulation_latest_by_target"] == "SKIPPED_RIP_SUMMARY"
    assert payload["meta"]["request"]["limit"] == 150


def test_targets_endpoint_without_rows_raises_404(monkeypatch):
    handlers = _build_handlers()
    handlers["explore_rip_statistics_latest"] = lambda _q: []
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
    target_query = next(call for call in client.calls if call.table_name == "explore_rip_statistics_latest")
    assert target_query.limit_value == 200