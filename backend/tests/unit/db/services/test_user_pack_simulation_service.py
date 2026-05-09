from backend.db.services import user_pack_simulation_service as service


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
        self.is_single = False

    def select(self, fields):
        self.select_fields = fields
        return self

    def eq(self, field, value):
        self.eq_filters.append((field, value))
        return self

    def order(self, field, desc=False):
        self.order_fields.append((field, desc))
        return self

    def in_(self, field, values):
        self.in_filters.append((field, list(values)))
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def single(self):
        self.is_single = True
        return self

    def execute(self):
        self.calls.append(self)
        handler = self.handlers[self.table_name]
        payload = handler(self)
        return _Result(payload)

    # Any write attempt should fail this test suite.
    def insert(self, *_args, **_kwargs):
        raise AssertionError(f"Unexpected write operation on {self.table_name}")

    def upsert(self, *_args, **_kwargs):
        raise AssertionError(f"Unexpected write operation on {self.table_name}")

    def update(self, *_args, **_kwargs):
        raise AssertionError(f"Unexpected write operation on {self.table_name}")

    def delete(self, *_args, **_kwargs):
        raise AssertionError(f"Unexpected write operation on {self.table_name}")


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
        "sets": lambda q: (
            [
                {
                    "id": "set-123",
                    "name": "Base Set",
                    "canonical_key": "base-set",
                    "logo_image_url": "https://img.example/logo.png",
                    "symbol_image_url": "https://img.example/symbol.png",
                    "hero_image_url": "https://img.example/hero.png",
                }
            ]
            if ("id", "set-123") in q.eq_filters or ("canonical_key", "base-set") in q.eq_filters
            else []
        ),
        "explore_rip_statistics_latest": lambda _q: [
            {
                "set_id": "set-123",
                "calculation_run_id": "run-1",
                "pack_score": 70.0,
                "pack_tier": "B",
                "profit_score": 65.0,
                "safety_score": 60.0,
                "stability_score": 58.0,
                "pack_cost": 5.0,
                "mean_value": 6.0,
                "median_value": 5.5,
                "prob_profit": 0.52,
                "prob_big_hit": 0.10,
                "expected_loss_when_losing": 1.2,
                "median_loss_when_losing": 1.0,
                "coefficient_of_variation": 0.8,
                "hhi_ev_concentration": 0.2,
                "effective_chase_count": 5.0,
                "tail_value_p05": 2.0,
            }
        ],
        "simulation_value_distribution_bins": lambda _q: [
            {
                "bin_floor": 0.0,
                "bin_ceiling": 4.0,
                "occurrence_count": 20,
                "probability": 0.2,
                "cumulative_probability": 0.2,
                "survival_probability": 0.8,
            },
            {
                "bin_floor": 4.0,
                "bin_ceiling": 8.0,
                "occurrence_count": 50,
                "probability": 0.5,
                "cumulative_probability": 0.7,
                "survival_probability": 0.3,
            },
            {
                "bin_floor": 8.0,
                "bin_ceiling": 20.0,
                "occurrence_count": 30,
                "probability": 0.3,
                "cumulative_probability": 1.0,
                "survival_probability": 0.0,
            },
        ],
        "simulation_value_threshold_bins": lambda _q: [
            {
                "threshold_floor": 0.0,
                "threshold_ceiling": 4.0,
                "occurrence_count": 20,
                "probability": 0.2,
                "cumulative_probability": 0.2,
                "survival_probability": 0.8,
                "bucket_label": "0-4",
                "bucket_order": 1,
            },
            {
                "threshold_floor": 4.0,
                "threshold_ceiling": 8.0,
                "occurrence_count": 50,
                "probability": 0.5,
                "cumulative_probability": 0.7,
                "survival_probability": 0.3,
                "bucket_label": "4-8",
                "bucket_order": 2,
            },
            {
                "threshold_floor": 8.0,
                "threshold_ceiling": 20.0,
                "occurrence_count": 30,
                "probability": 0.3,
                "cumulative_probability": 1.0,
                "survival_probability": 0.0,
                "bucket_label": "8-20",
                "bucket_order": 3,
            },
        ],
        "simulation_percentiles": lambda _q: [
            {"percentile": 5, "value": 2.0},
            {"percentile": 50, "value": 5.5},
            {"percentile": 95, "value": 15.0},
        ],
        "simulation_input_cards_with_near_mint_price": lambda _q: [
            {
                "card_id": "card-1",
                "card_variant_id": "variant-1",
                "card_name": "Charizard ex",
                "rarity_bucket": "ultra_rare",
                "ev_contribution": 1.5,
                "current_near_mint_price": 45.0,
            }
        ],
        "card_variants": lambda _q: [
            {
                "id": "variant-1",
                "card_id": "card-1",
                "image_small_url": "https://img.example/variant-small.png",
                "image_large_url": "https://img.example/variant-large.png",
            }
        ],
        "cards": lambda _q: [
            {
                "id": "card-1",
                "image_small_url": "https://img.example/card-small.png",
                "image_large_url": "https://img.example/card-large.png",
            }
        ],
        "simulation_pull_summary": lambda _q: [
            {
                "rarity_bucket": "ultra_rare",
                "pulled_count": 120,
                "avg_sampled_value": 8.0,
                "total_sampled_value": 960.0,
            }
        ],
        "simulation_state_counts": lambda _q: [
            {"state_group": "pack_path", "state_name": "normal", "occurrence_count": 980000},
            {"state_group": "pack_path", "state_name": "god_pack", "occurrence_count": 20000},
            {"state_group": "normal_pack_state", "state_name": "solid", "occurrence_count": 500000},
        ],
        "simulation_run_summary": lambda _q: {
            "pack_cost": 5.0,
            "mean_value": 6.0,
            "median_value": 5.5,
            "net_value": 1.0,
            "roi": 1.2,
            "roi_percent": 20.0,
            "prob_profit": 0.52,
            "prob_big_hit": 0.10,
            "expected_loss_when_losing": 1.2,
            "median_loss_when_losing": 1.0,
            "coefficient_of_variation": 0.8,
            "tail_value_p05": 2.0,
        },
        "simulation_derived_metrics": lambda _q: {
            "hhi_ev_concentration": 0.2,
            "effective_chase_count": 5.0,
        },
        "set_pack_score_rankings_latest": lambda q: (
            [
                {
                    "target_id": "set-123",
                    "pack_rank": 10,
                    "pack_tier": "B",
                    "profit_rank": 11,
                    "profit_tier": "B",
                    "safety_rank": 12,
                    "safety_tier": "C",
                    "stability_rank": 13,
                    "stability_tier": "C",
                }
            ]
            if any(field == "target_id" and value == "set-123" for field, value in q.eq_filters)
            else [
                {"target_id": "set-123", "pack_score": 70.0, "profit_score": 65.0, "safety_score": 60.0, "stability_score": 58.0},
                {"target_id": "set-456", "pack_score": 80.0, "profit_score": 75.0, "safety_score": 72.0, "stability_score": 68.0},
                {"target_id": "set-789", "pack_score": 50.0, "profit_score": 48.0, "safety_score": 55.0, "stability_score": 45.0},
            ]
        ),
        "calculation_history_trend": lambda _q: [
            {
                "snapshot_date": "2026-04-01",
                "simulated_mean_pack_value_vs_pack_cost": 1.20,
                "simulated_median_pack_value_vs_pack_cost": 1.10,
                "run_created_at": "2026-04-01T00:00:00Z",
                "calculation_run_id": "run-h1",
                "p95_value_to_cost_ratio": 3.0,
                "market_pack_cost": 5.0,
            },
            {
                "snapshot_date": "2026-04-10",
                "simulated_mean_pack_value_vs_pack_cost": 1.10,
                "simulated_median_pack_value_vs_pack_cost": 1.00,
                "run_created_at": "2026-04-10T00:00:00Z",
                "calculation_run_id": "run-h2",
                "p95_value_to_cost_ratio": 2.8,
                "market_pack_cost": 5.0,
            },
        ],
    }


def test_rejects_missing_target_id(monkeypatch):
    with _raises_service_error("INVALID_TARGET_ID"):
        service.simulate_with_custom_price("set", "", 7.5)


def test_rejects_non_positive_custom_pack_cost(monkeypatch):
    with _raises_service_error("INVALID_CUSTOM_PACK_COST"):
        service.simulate_with_custom_price("set", "set-123", 0)


def test_rejects_large_custom_pack_cost(monkeypatch):
    with _raises_service_error("INVALID_CUSTOM_PACK_COST"):
        service.simulate_with_custom_price("set", "set-123", 1000)


def test_returns_baseline_and_custom_objects(monkeypatch):
    handlers = _build_handlers()
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.simulate_with_custom_price("set", "set-123", 7.5)

    assert isinstance(payload.get("baseline"), dict)
    assert isinstance(payload.get("custom"), dict)
    assert isinstance(payload.get("comparison", {}).get("summary_metrics"), dict)
    assert isinstance(payload.get("context", {}).get("history_trend"), list)
    assert payload["meta"]["writes_to_database"] is False
    assert payload["meta"]["mode"] == "repriced_from_latest_distribution"


def test_summary_metrics_include_percentage_point_delta(monkeypatch):
    handlers = _build_handlers()
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.simulate_with_custom_price("set", "set-123", 7.5)

    summary_metrics = payload["comparison"]["summary_metrics"]
    chance = summary_metrics["chance_to_beat_cost"]
    expected_points = (payload["custom"]["prob_profit"] - payload["baseline"]["prob_profit"]) * 100.0

    assert chance["difference_unit"] == "percentage_points"
    assert round(chance["difference_value"], 6) == round(expected_points, 6)
    assert chance["difference_label"].endswith("pts")


def test_roi_and_net_value_update_with_custom_price(monkeypatch):
    handlers = _build_handlers()
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.simulate_with_custom_price("set", "set-123", 7.5)

    baseline = payload["baseline"]
    custom = payload["custom"]

    assert baseline["net_value"] == 1.0
    assert round(custom["net_value"], 6) == -1.5
    assert round(baseline["roi"], 6) == 1.2
    assert round(custom["roi"], 6) == 0.8
    assert round(custom["roi_percent"], 6) == -20.0


def test_mean_median_and_stability_consistency(monkeypatch):
    handlers = _build_handlers()
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.simulate_with_custom_price("set", "set-123", 7.5)

    assert payload["custom"]["mean_value"] == payload["baseline"]["mean_value"]
    assert payload["custom"]["median_value"] == payload["baseline"]["median_value"]
    assert payload["custom"]["stability_score"] == payload["baseline"]["stability_score"]


def test_service_does_not_write_simulation_tables(monkeypatch):
    handlers = _build_handlers()
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    service.simulate_with_custom_price("set", "set-123", 7.5)

    # If any write method was called, _Query would raise AssertionError.
    assert len(client.calls) > 0
    write_table_names = {
        "calculation_runs",
        "calculation_configs",
        "calculation_price_snapshots",
        "simulation_run_summary",
        "simulation_derived_metrics",
        "simulation_input_cards",
        "simulation_percentiles",
        "simulation_pull_summary",
        "simulation_state_counts",
        "simulation_value_distribution_bins",
        "simulation_value_threshold_bins",
        "simulation_etb_summary",
        "sealed_product_prices",
    }
    queried_tables = {call.table_name for call in client.calls}
    assert queried_tables.intersection(write_table_names)


def _raises_service_error(expected_code):
    class _ContextManager:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, _tb):
            assert exc_type is service.UserPackSimulationError
            assert exc.code == expected_code
            return True

    return _ContextManager()
