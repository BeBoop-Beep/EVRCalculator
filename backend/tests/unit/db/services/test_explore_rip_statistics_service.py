from backend.db.services import explore_rip_statistics_service as service


class _AnySetCollectorPayloads(dict):
    """An available Collector Appeal payload for whatever set id is asked for.

    These tests exercise target discovery/enrichment, not Collector Appeal, so
    the bundle is stubbed rather than built - the real build reads the pull
    model and card links from the network, which a unit test must not. Serving
    an available payload for every id keeps the public-cohort integrity check
    satisfied for each fixture's arbitrary set ids.
    """

    def get(self, key, default=None):
        return {
            "setId": key,
            "setName": key,
            "status": "available",
            "asOf": "2026-01-01T00:00:00Z",
            "rosterDesirability": {"score": 90.0, "version": "universal_set_desirability_v3"},
            "dualPathDepth": {"rawValue": 0.25, "displayPercent": 25.0, "version": "dual_path_depth_v1"},
            "collectorAppeal": {"score": 92.5, "rawValue": 0.925, "version": "collector_appeal_ca7_v1"},
            "chaseAppeal": {"score": 70.0, "rawValue": 0.70, "version": "chase_appeal_ca2_v1"},
            "topSubjects": [],
            "coverage": {"status": "available", "reasons": []},
        }


def _stub_collector_appeal_bundle(monkeypatch):
    monkeypatch.setattr(
        service,
        "get_collector_appeal_bundle",
        lambda **_: {"payloads": _AnySetCollectorPayloads()},
    )


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
        self.range_value = None

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

    def range(self, start, end):
        self.range_value = (start, end)
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
                "desirability_score": 42.0,
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
                "desirability_score": 96.0,
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
        "pokemon_set_value_daily_history": lambda q: [
            {
                "set_id": "set-2",
                "snapshot_date": "2026-01-04",
                "set_value": 222.22,
                "priced_card_count": 58,
                "total_card_count": 64,
                "source": "snapshot",
            },
            {
                "set_id": "set-1",
                "snapshot_date": "2026-01-04",
                "set_value": 111.11,
                "priced_card_count": 92,
                "total_card_count": 102,
                "source": "snapshot",
            },
            {
                "set_id": "set-1",
                "snapshot_date": "2026-01-03",
                "set_value": 100.0,
                "priced_card_count": 90,
                "total_card_count": 102,
                "source": "snapshot",
            },
        ],
        "pokemon_set_opening_desirability_latest": lambda _q: [
            {
                "set_id": "set-1",
                "opening_desirability_score": 42.0,
                "opening_desirability_display_status": "scored",
                "scoring_version": "opening-v1",
            },
            {
                "set_id": "set-2",
                "opening_desirability_score": 96.0,
                "opening_desirability_display_status": "scored",
                "scoring_version": "opening-v1",
            },
        ],
        "pokemon_canonical_card_market_prices_latest": lambda _q: [
            *[
                {"set_id": "set-1", "canonical_card_id": f"set-1-card-{index:02d}", "market_price": float(index)}
                for index in range(1, 13)
            ],
            *[
                {"set_id": "set-2", "canonical_card_id": f"set-2-card-{index:02d}", "market_price": float(index * 2)}
                for index in range(1, 13)
            ],
        ],
        "set_pack_score_rankings_latest": lambda _q: [],
    }


def test_targets_endpoint_returns_sorted_targets_and_default(monkeypatch):
    handlers = _build_handlers()
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)
    _stub_collector_appeal_bundle(monkeypatch)

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
    assert targets_by_id["set-1"]["pack_tier"] == "D"
    assert targets_by_id["set-1"]["pack_rank"] == targets_by_id["set-1"]["rip_rank_with_desirability"]
    assert targets_by_id["set-1"]["relative_rip_core_score"] is not None
    assert targets_by_id["set-1"]["top_10_card_value"] == 75.0
    assert targets_by_id["set-2"]["top_10_card_value"] == 150.0
    assert targets_by_id["set-2"]["top_10_card_value_rank"] == 1
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
    assert targets_by_id["set-2"]["rip_score_with_desirability"] == 83.0
    assert targets_by_id["set-2"]["rip_score_without_desirability"] == 79.75
    assert targets_by_id["set-2"]["rip_score_delta"] == 3.25
    assert targets_by_id["set-2"]["rip_rank_with_desirability"] == 1
    assert targets_by_id["set-2"]["rip_rank_without_desirability"] == 1
    assert targets_by_id["set-2"]["desirability_component_score"] == 96.0
    assert targets_by_id["set-2"]["pack_score"] == 83.0
    assert targets_by_id["set-2"]["set_value_for_validation"] == 222.22
    assert targets_by_id["set-2"]["current_checklist_set_value"] == 222.22
    assert targets_by_id["set-2"]["checklist_set_value"] == 222.22
    assert targets_by_id["set-2"]["setValueForValidation"] == 222.22
    assert targets_by_id["set-2"]["currentChecklistSetValue"] == 222.22
    assert targets_by_id["set-2"]["checklistSetValue"] == 222.22
    assert targets_by_id["set-2"]["current_checklist_set_value_date"] == "2026-01-04"
    assert targets_by_id["set-2"]["checklist_set_value_priced_card_count"] == 58
    assert payload["meta"]["ripDesirabilityComparison"]["valid_comparison_count"] == 2
    assert payload["meta"]["sources"]["explore_rip_statistics_latest"] == "OK"
    assert payload["meta"]["sources"]["simulation_latest_by_target"] == "SKIPPED_RIP_SUMMARY"
    assert payload["meta"]["sources"]["pokemon_set_value_daily_history"] == "OK"
    assert payload["meta"]["request"]["limit"] == 150


def test_targets_endpoint_includes_canonical_checklist_set_value_for_validation(monkeypatch):
    handlers = _build_handlers()
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)
    _stub_collector_appeal_bundle(monkeypatch)
    monkeypatch.setattr(
        service,
        "build_rip_interpretation",
        lambda _summary_row: {"meta": {"packScore": {"label": "Good value", "severity": "neutral"}}},
    )

    payload = service.get_rip_statistics_targets_payload()
    targets_by_id = {target["target_id"]: target for target in payload["targets"]}
    history_query = next(call for call in client.calls if call.table_name == "pokemon_set_value_daily_history")

    assert ("value_scope", "standard") in history_query.eq_filters
    assert history_query.in_filters == [("set_id", ["set-1", "set-2"])]
    assert ("snapshot_date", True) in history_query.order_fields
    assert targets_by_id["set-1"]["set_value_for_validation"] == 111.11
    assert targets_by_id["set-1"]["current_checklist_set_value"] == 111.11
    assert targets_by_id["set-1"]["checklist_set_value"] == 111.11
    assert targets_by_id["set-2"]["set_value_for_validation"] == 222.22
    assert targets_by_id["set-2"]["current_checklist_set_value_date"] == "2026-01-04"


def test_targets_endpoint_without_rows_raises_404(monkeypatch):
    handlers = _build_handlers()
    handlers["explore_rip_statistics_latest"] = lambda _q: []
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)
    _stub_collector_appeal_bundle(monkeypatch)

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
    _stub_collector_appeal_bundle(monkeypatch)

    payload = service.get_rip_statistics_targets_payload()

    assert payload["targets"][0]["name"] == payload["targets"][0]["target_id"]
    assert payload["meta"]["sources"]["sets"] == "FAILED"
    assert any("set metadata" in warning.lower() for warning in payload["meta"]["warnings"])


def test_limit_is_safely_clamped(monkeypatch):
    handlers = _build_handlers()
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)
    _stub_collector_appeal_bundle(monkeypatch)

    payload = service.get_rip_statistics_targets_payload(limit="999")

    assert payload["meta"]["request"]["limit"] == 200
    target_query = next(call for call in client.calls if call.table_name == "explore_rip_statistics_latest")
    assert target_query.limit_value == 200


def test_all_scored_opening_desirability_rows_join_into_canonical_comparison(monkeypatch):
    set_ids = [f"set-{index:02d}" for index in range(33)]
    handlers = {
        "explore_rip_statistics_latest": lambda _q: [
            {
                "set_id": set_id,
                "run_at": "2026-07-01T00:00:00Z",
                "pack_score": 20 + index,
                "relative_pack_score": index,
                "pack_rank": 33 - index,
                "pack_tier": "C",
                "profit_score": 20 + index,
                "safety_score": 30 + index,
                "stability_score": 40 + index,
                "desirability_score": (50 + index if index < 21 else None),
                "pack_cost": 5,
                "mean_value": 4,
            }
            for index, set_id in enumerate(set_ids)
        ],
        "sets": lambda _q: [{"id": set_id, "name": f"Set {index:02d}"} for index, set_id in enumerate(set_ids)],
        "eras": lambda _q: [],
        "pokemon_set_value_daily_history": lambda _q: [],
        "pokemon_set_opening_desirability_latest": lambda _q: [
            {
                "set_id": set_id,
                "opening_desirability_score": 50 + index,
                "opening_desirability_display_status": "scored",
                "scoring_version": "opening-v1",
            }
            for index, set_id in enumerate(set_ids)
        ],
        "pokemon_canonical_card_market_prices_latest": lambda _q: [
            {
                "set_id": set_id,
                "canonical_card_id": f"{set_id}-card-{card_index:02d}",
                "market_price": card_index + index,
            }
            for index, set_id in enumerate(set_ids)
            for card_index in range(1, 11)
        ],
        "set_pack_score_rankings_latest": lambda _q: [],
    }
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)
    _stub_collector_appeal_bundle(monkeypatch)
    monkeypatch.setattr(
        service,
        "build_rip_interpretation",
        lambda _row: {"meta": {"packScore": {"label": "Profile", "summary": "Summary", "severity": "neutral"}}},
    )

    payload = service.get_rip_statistics_targets_payload(limit=100)

    assert len(payload["targets"]) == 33
    assert payload["meta"]["ripDesirabilityComparison"]["valid_comparison_count"] == 33
    assert all(target["rip_score_with_desirability"] is not None for target in payload["targets"])
    assert all(target["rip_rank_with_desirability"] == target["pack_rank"] for target in payload["targets"])
    assert all(target["top_10_card_value_rank"] is not None for target in payload["targets"])


def test_top_10_card_value_sorts_before_aggregation_and_reports_unavailable_prices(monkeypatch):
    rows = [
        {"set_id": "set-1", "canonical_card_id": "missing", "market_price": None},
        *[
            {"set_id": "set-1", "canonical_card_id": f"card-{index:02d}", "market_price": float(index)}
            for index in [3, 12, 1, 8, 11, 4, 10, 2, 9, 7, 6, 5]
        ],
    ]
    client = _Client({"pokemon_canonical_card_market_prices_latest": lambda _q: rows})
    monkeypatch.setattr(service, "public_read_client", client)
    _stub_collector_appeal_bundle(monkeypatch)
    sources = {}
    warnings = []

    lookup = service._load_top_10_card_value_lookup(["set-1"], sources=sources, warnings=warnings)

    assert lookup["set-1"]["top_10_card_value"] == 75.0
    assert lookup["set-1"]["top_10_card_value_sample_size"] == 10
    assert lookup["set-1"]["top_10_card_value_priced_card_count"] == 12
    assert lookup["set-1"]["top_10_card_value_unavailable_price_count"] == 1
    assert lookup["set-1"]["top_10_card_value_coverage"] == 1.0


def test_top_10_card_value_rank_ties_use_target_id_deterministically():
    targets = [
        {"target_id": "set-z", "top_10_card_value": 100},
        {"target_id": "set-a", "top_10_card_value": 100},
        {"target_id": "set-m", "top_10_card_value": 90},
    ]

    service._rank_top_10_card_values(targets)

    assert {target["target_id"]: target["top_10_card_value_rank"] for target in targets} == {
        "set-a": 1,
        "set-z": 2,
        "set-m": 3,
    }
