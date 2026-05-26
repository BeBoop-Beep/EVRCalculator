import sys

from backend.db.services import explore_page_service as service


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
        self.order_field = None
        self.order_desc = None
        self.limit_value = None
        self.is_single = False

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
        self.order_field = field
        self.order_desc = desc
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


class _Client:
    def __init__(self, handlers):
        self.handlers = handlers
        self.calls = []

    def table(self, table_name):
        if table_name not in self.handlers:
            raise AssertionError(f"Unexpected table requested: {table_name}")
        return _Query(table_name, self.handlers, self.calls)


def _build_success_handlers(run_id="run-1"):
    """Handlers for the canonical path (simulation_latest_by_target works).

    The canonical view exposes run_at (not created_at) and includes all summary
    and derived-metric fields inline — so simulation_run_summary and
    simulation_derived_metrics are NOT queried on the happy path.
    """
    return {
        # RIP-specific latest view (preferred for set targets).
        # Defaulting to [] keeps legacy canonical-path tests intact.
        "explore_rip_statistics_latest": lambda _q: [],
        "simulation_latest_by_target": lambda _q: [
            {
                "target_type": "set",
                "target_id": "base-set",
                "calculation_run_id": run_id,
                "run_at": "2026-01-01T00:00:00Z",
                # Summary fields provided by the view:
                "pack_cost": 4.99,
                "mean_value": 5.55,
                "median_value": 5.10,
                "min_value": 1.00,
                "max_value": 50.00,
                "std_dev": 3.20,
                "roi_percent": 11.2,
                "prob_profit": 0.54,
                "pack_score": 0.72,
                "profit_score": 0.68,
                "safety_score": 0.81,
                "stability_score": 0.75,
            }
        ],
        # calculation_runs is used on the fallback path only.
        "calculation_runs": lambda _q: [{"id": run_id, "created_at": "2026-01-01T00:00:00Z"}],
        # simulation_run_summary / derived_metrics used on fallback path only.
        "simulation_run_summary": lambda _q: {
            "pack_cost": 4.99,
            "mean_value": 5.55,
            "roi_percent": 11.2,
        },
        "simulation_derived_metrics": lambda _q: {"headline_score": 0.9},
        "simulation_pull_summary": lambda _q: [],
        "simulation_state_counts": lambda _q: [],
        "simulation_percentiles": lambda _q: [],
        "simulation_value_distribution_bins": lambda _q: [],
        "simulation_value_threshold_bins": lambda _q: [],
        "simulation_input_cards_with_near_mint_price": lambda _q: [],
        "sets": lambda _q: [],
        "card_variants": lambda _q: [],
        "cards": lambda _q: [],
    }


def test_rip_latest_summary_is_preferred_for_set_targets(monkeypatch):
    handlers = _build_success_handlers(run_id="run-rip")
    handlers["explore_rip_statistics_latest"] = lambda _q: [
        {
            "set_id": "base-set",
            "calculation_run_id": "run-rip",
            "run_at": "2026-01-01T00:00:00Z",
            "pack_score": 78.1,
            "relative_pack_score": 81.4,
            "pack_rank": 3,
            "profit_score": 70.0,
            "safety_score": 73.0,
            "stability_score": 69.0,
            "profit_rank": 4,
            "safety_rank": 2,
            "stability_rank": 5,
            "pack_cost": 4.99,
            "mean_value": 5.55,
            "median_value": 5.10,
            "roi_percent": 11.2,
            "prob_profit": 0.54,
            "p95_value_to_cost_ratio": 1.9,
            "p99_value_to_cost_ratio": 2.5,
            "mean_value_to_cost_ratio": 1.11,
            "median_value_to_cost_ratio": 1.02,
            "expected_loss_when_losing_fraction": 0.33,
            "median_loss_when_losing_fraction": 0.29,
            "p05_shortfall_to_cost": 0.41,
            "expected_loss_when_losing": 1.2,
            "median_loss_when_losing": 1.0,
            "expected_loss_per_pack": 0.6,
            "tail_value_p05": 2.1,
            "coefficient_of_variation": 0.8,
            "hhi_ev_concentration": 0.14,
            "effective_chase_count": 7.3,
            "top1_ev_share": 0.18,
            "top3_ev_share": 0.35,
            "top5_ev_share": 0.47,
        }
    ]

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "base-set")

    assert payload["summary"]["relative_pack_score"] == 81.4
    assert payload["summary"]["pack_rank"] == 3
    assert payload["meta"]["sources"]["summary_source"] == "explore_rip_statistics_latest"
    assert payload["meta"]["sources"]["latest_target_source"] == "explore_rip_statistics_latest"

    # Canonical summary sources are skipped when RIP summary is available.
    assert payload["meta"]["sources"]["simulation_latest_by_target"] == "SKIPPED_RIP_SUMMARY"
    assert payload["meta"]["sources"]["simulation_run_summary"] == "SKIPPED_RIP_SUMMARY"
    assert payload["meta"]["sources"]["simulation_derived_metrics"] == "SKIPPED_RIP_SUMMARY"

    # Downstream queries must use the calculation_run_id from RIP summary row.
    percentiles_calls = [c for c in client.calls if c.table_name == "simulation_percentiles"]
    assert len(percentiles_calls) == 1
    assert ("calculation_run_id", "run-rip") in percentiles_calls[0].eq_filters


def test_missing_target_returns_404(monkeypatch):
    handlers = _build_success_handlers()
    handlers["simulation_latest_by_target"] = lambda _q: []

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    try:
        service.get_explore_page_payload("set", "missing-target")
        assert False, "Expected ExplorePageError"
    except service.ExplorePageError as exc:
        assert exc.status_code == 404
        assert exc.code == "TARGET_NOT_FOUND"


def test_required_summary_failure_raises_500(monkeypatch):
    """When the canonical view is unavailable (fallback path) and the fallback
    simulation_run_summary query also fails, the service must raise 500."""
    handlers = _build_success_handlers()

    # Make canonical view raise to force the fallback path.
    def _canonical_fail(_q):
        raise RuntimeError("canonical view unavailable")

    def _summary_fail(_q):
        raise RuntimeError("summary query failed")

    handlers["simulation_latest_by_target"] = _canonical_fail
    handlers["simulation_run_summary"] = _summary_fail

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    try:
        service.get_explore_page_payload("set", "base-set")
        assert False, "Expected ExplorePageError"
    except service.ExplorePageError as exc:
        assert exc.status_code == 500
        assert exc.code == "SUMMARY_QUERY_FAILED"


def test_optional_distribution_failure_returns_warning_and_empty_bins(monkeypatch):
    handlers = _build_success_handlers()

    def _distribution_fail(_q):
        raise RuntimeError("distribution unavailable")

    handlers["simulation_value_distribution_bins"] = _distribution_fail

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "base-set")

    assert payload["distribution_bins"] == []
    assert "Failed to load distribution bins" in payload["meta"]["warnings"]
    assert payload["meta"]["sources"]["simulation_value_distribution_bins"] == "FAILED"


def test_limit_values_are_safely_clamped(monkeypatch):
    handlers = _build_success_handlers()
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload(
        "set",
        "base-set",
        limit_distribution_bins="999",
        limit_top_hits="0",
    )

    assert payload["meta"]["request"]["limit_distribution_bins"] == 200
    assert payload["meta"]["request"]["limit_top_hits"] == 1

    distribution_calls = [c for c in client.calls if c.table_name == "simulation_value_distribution_bins"]
    top_hits_calls = [c for c in client.calls if c.table_name == "simulation_input_cards_with_near_mint_price"]

    assert len(distribution_calls) == 1
    assert len(top_hits_calls) >= 1
    assert distribution_calls[0].limit_value == 200
    assert any(call.limit_value == 1 for call in top_hits_calls)


def test_distribution_bins_are_queried_separately(monkeypatch):
    """On the canonical path summary comes from the view row, so
    simulation_run_summary is never queried. Distribution bins are still a
    separate optional query."""
    handlers = _build_success_handlers()
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    service.get_explore_page_payload("set", "base-set")

    summary_calls = [c for c in client.calls if c.table_name == "simulation_run_summary"]
    distribution_calls = [c for c in client.calls if c.table_name == "simulation_value_distribution_bins"]

    # Canonical path: simulation_run_summary is NOT queried.
    assert len(summary_calls) == 0
    # Distribution bins are still fetched as a separate optional query.
    assert len(distribution_calls) == 1


def test_threshold_bins_are_queried_separately(monkeypatch):
    handlers = _build_success_handlers()
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "base-set")

    threshold_calls = [c for c in client.calls if c.table_name == "simulation_value_threshold_bins"]

    assert len(threshold_calls) == 1
    assert payload["threshold_bins"] == []
    assert payload["meta"]["sources"]["simulation_value_threshold_bins"] == "OK"


def test_canonical_latest_missing_run_id_falls_back_with_warning(monkeypatch):
    """When the canonical view returns a row but without calculation_run_id the
    service falls back to calculation_runs for the run lookup, then queries
    simulation_run_summary and simulation_derived_metrics."""
    handlers = _build_success_handlers(run_id="run-from-fallback")
    handlers["simulation_latest_by_target"] = lambda _q: [
        {
            "target_type": "set",
            "target_id": "base-set",
            "run_at": "2026-01-01T00:00:00Z",
            # Note: calculation_run_id intentionally absent to trigger fallback.
        }
    ]

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "base-set")

    assert (
        payload["meta"]["sources"]["simulation_latest_by_target"]
        == "MISSING_CALCULATION_RUN_ID_FALLBACK"
    )
    assert payload["meta"]["sources"]["latest_target_source"] == "calculation_runs_fallback"
    assert any(
        "simulation_latest_by_target did not expose calculation_run_id" in warning
        for warning in payload["meta"]["warnings"]
    )


def test_canonical_path_does_not_query_summary_or_derived(monkeypatch):
    """When simulation_latest_by_target succeeds with a valid calculation_run_id,
    the service must NOT query simulation_run_summary or simulation_derived_metrics."""
    handlers = _build_success_handlers()
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    service.get_explore_page_payload("set", "base-set")

    summary_calls = [c for c in client.calls if c.table_name == "simulation_run_summary"]
    derived_calls = [c for c in client.calls if c.table_name == "simulation_derived_metrics"]

    assert len(summary_calls) == 0, "simulation_run_summary must not be queried on the canonical path"
    assert len(derived_calls) == 0, "simulation_derived_metrics must not be queried on the canonical path"


def test_canonical_path_sources_ok(monkeypatch):
    """Canonical path sets simulation_latest_by_target=OK and marks the two
    skipped tables as SKIPPED_CANONICAL."""
    handlers = _build_success_handlers()
    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "base-set")

    sources = payload["meta"]["sources"]
    assert sources["simulation_latest_by_target"] == "OK"
    assert sources["latest_target_source"] == "simulation_latest_by_target"
    assert sources["simulation_run_summary"] == "SKIPPED_CANONICAL"
    assert sources["simulation_derived_metrics"] == "SKIPPED_CANONICAL"


def test_fallback_path_queries_summary_and_derived(monkeypatch):
    """When simulation_latest_by_target raises an exception, the service falls back
    to calculation_runs and then queries simulation_run_summary +
    simulation_derived_metrics as required tables."""
    handlers = _build_success_handlers()

    def _canonical_fail(_q):
        raise RuntimeError("view unavailable in test")

    handlers["simulation_latest_by_target"] = _canonical_fail

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "base-set")

    sources = payload["meta"]["sources"]
    assert sources["simulation_latest_by_target"] == "UNAVAILABLE_FALLBACK"
    assert sources["latest_target_source"] == "calculation_runs_fallback"
    assert sources["simulation_run_summary"] == "OK"
    assert sources["simulation_derived_metrics"] == "OK"

    summary_calls = [c for c in client.calls if c.table_name == "simulation_run_summary"]
    derived_calls = [c for c in client.calls if c.table_name == "simulation_derived_metrics"]
    assert len(summary_calls) == 1
    assert len(derived_calls) == 1


def test_top_hits_are_enriched_with_variant_and_card_image_fallbacks(monkeypatch):
    handlers = _build_success_handlers()
    handlers["simulation_input_cards_with_near_mint_price"] = lambda _q: [
        {
            "card_id": "card-1",
            "card_variant_id": "variant-1",
            "card_name": "Hit One",
            "ev_contribution": 1.25,
        },
        {
            "card_id": "card-2",
            "card_variant_id": "variant-2",
            "card_name": "Hit Two",
            "ev_contribution": 0.75,
        },
        {
            "card_id": "card-3",
            "card_variant_id": None,
            "card_name": "Hit Three",
            "ev_contribution": 0.5,
        },
        {
            "card_id": "card-4",
            "card_variant_id": None,
            "card_name": "Hit Four",
            "ev_contribution": 0.25,
        },
    ]
    handlers["card_variants"] = lambda _q: [
        {
            "id": "variant-1",
            "card_id": "card-1",
            "image_small_url": "https://img.test/variant-small.png",
            "image_large_url": "https://img.test/variant-large.png",
        },
        {
            "id": "variant-2",
            "card_id": "card-2",
            "image_small_url": None,
            "image_large_url": "https://img.test/variant-large-only.png",
        },
    ]
    handlers["cards"] = lambda _q: [
        {
            "id": "card-1",
            "image_small_url": "https://img.test/card-small.png",
            "image_large_url": "https://img.test/card-large.png",
        },
        {
            "id": "card-2",
            "image_small_url": "https://img.test/card-small-fallback.png",
            "image_large_url": "https://img.test/card-large-fallback.png",
        },
        {
            "id": "card-3",
            "image_small_url": None,
            "image_large_url": "https://img.test/card-large-only.png",
        },
        {
            "id": "card-4",
            "image_small_url": None,
            "image_large_url": None,
        },
    ]

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "base-set")

    assert payload["top_hits"] == [
        {
            "card_id": "card-1",
            "card_variant_id": "variant-1",
            "card_name": "Hit One",
            "ev_contribution": 1.25,
            "image_url": "https://img.test/variant-small.png",
            "image_small_url": "https://img.test/variant-small.png",
            "image_large_url": "https://img.test/variant-large.png",
        },
        {
            "card_id": "card-2",
            "card_variant_id": "variant-2",
            "card_name": "Hit Two",
            "ev_contribution": 0.75,
            "image_url": "https://img.test/card-small-fallback.png",
            "image_small_url": "https://img.test/card-small-fallback.png",
            "image_large_url": "https://img.test/variant-large-only.png",
        },
        {
            "card_id": "card-3",
            "card_variant_id": None,
            "card_name": "Hit Three",
            "ev_contribution": 0.5,
            "image_url": "https://img.test/card-large-only.png",
            "image_small_url": None,
            "image_large_url": "https://img.test/card-large-only.png",
        },
        {
            "card_id": "card-4",
            "card_variant_id": None,
            "card_name": "Hit Four",
            "ev_contribution": 0.25,
            "image_url": None,
            "image_small_url": None,
            "image_large_url": None,
        },
    ]

    variant_calls = [c for c in client.calls if c.table_name == "card_variants"]
    card_calls = [c for c in client.calls if c.table_name == "cards"]
    assert len(variant_calls) == 1
    assert len(card_calls) == 1
    assert variant_calls[0].in_filters == [("id", ["variant-1", "variant-2"])]
    assert card_calls[0].in_filters == [("id", ["card-1", "card-2", "card-3", "card-4"])]


def test_summary_populates_p99_value_to_cost_ratio_from_percentiles(monkeypatch):
    handlers = _build_success_handlers(run_id="run-p99")
    handlers["explore_rip_statistics_latest"] = lambda _q: [
        {
            "set_id": "base-set",
            "calculation_run_id": "run-p99",
            "run_at": "2026-01-01T00:00:00Z",
            "pack_score": 78.1,
            "relative_pack_score": 81.4,
            "pack_rank": 3,
            "profit_score": 70.0,
            "safety_score": 73.0,
            "stability_score": 69.0,
            "profit_rank": 4,
            "safety_rank": 2,
            "stability_rank": 5,
            "pack_cost": 5.0,
            "mean_value": 5.55,
            "median_value": 5.1,
            "roi_percent": 11.2,
            "prob_profit": 0.54,
            "p95_value_to_cost_ratio": 1.9,
            "mean_value_to_cost_ratio": 1.11,
            "median_value_to_cost_ratio": 1.02,
            "expected_loss_when_losing_fraction": 0.33,
            "median_loss_when_losing_fraction": 0.29,
            "p05_shortfall_to_cost": 0.41,
            "expected_loss_when_losing": 1.2,
            "median_loss_when_losing": 1.0,
            "expected_loss_per_pack": 0.6,
            "tail_value_p05": 2.1,
            "coefficient_of_variation": 0.8,
            "hhi_ev_concentration": 0.14,
            "effective_chase_count": 7.3,
            "top1_ev_share": 0.18,
            "top3_ev_share": 0.35,
            "top5_ev_share": 0.47,
        }
    ]
    handlers["simulation_percentiles"] = lambda _q: [
        {"percentile": 95.0, "value": 9.5},
        {"percentile": 99.0, "value": 12.5},
    ]

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "base-set")

    assert payload["summary"]["p99_value"] == 12.5
    assert payload["summary"]["p99_value_to_cost_ratio"] == 2.5
    assert payload["summary"]["biggest_upside_score"] is not None
    assert payload["summary"]["biggest_upside_rank"] == 1
    assert payload["summary"]["biggest_upside_tier"] == "S"
    assert payload["summary"]["relative_average_return_score"] == 50.0
    assert payload["meta"]["sources"]["biggest_upside_blend"] == "SERVICE_COMPUTED"
    assert payload["meta"]["sources"]["average_return_relative"] == "SERVICE_COMPUTED"


def test_rip_summary_keeps_direct_p99_ratio_without_percentile_recompute(monkeypatch):
    handlers = _build_success_handlers(run_id="run-p99-direct")
    handlers["explore_rip_statistics_latest"] = lambda _q: [
        {
            "set_id": "base-set",
            "calculation_run_id": "run-p99-direct",
            "run_at": "2026-01-01T00:00:00Z",
            "pack_score": 78.1,
            "relative_pack_score": 81.4,
            "pack_rank": 3,
            "profit_score": 70.0,
            "safety_score": 73.0,
            "stability_score": 69.0,
            "profit_rank": 4,
            "safety_rank": 2,
            "stability_rank": 5,
            "pack_cost": 5.0,
            "mean_value": 5.55,
            "median_value": 5.1,
            "roi_percent": 11.2,
            "prob_profit": 0.54,
            "p95_value_to_cost_ratio": 1.9,
            "p99_value": 11.0,
            "p99_value_to_cost_ratio": 2.2,
            "mean_value_to_cost_ratio": 1.11,
            "median_value_to_cost_ratio": 1.02,
            "expected_loss_when_losing_fraction": 0.33,
            "median_loss_when_losing_fraction": 0.29,
            "p05_shortfall_to_cost": 0.41,
            "expected_loss_when_losing": 1.2,
            "median_loss_when_losing": 1.0,
            "expected_loss_per_pack": 0.6,
            "tail_value_p05": 2.1,
            "coefficient_of_variation": 0.8,
            "hhi_ev_concentration": 0.14,
            "effective_chase_count": 7.3,
            "top1_ev_share": 0.18,
            "top3_ev_share": 0.35,
            "top5_ev_share": 0.47,
        }
    ]
    handlers["simulation_percentiles"] = lambda _q: [
        {"percentile": 95.0, "value": 9.5},
        {"percentile": 99.0, "value": 25.0},
    ]

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "base-set")

    assert payload["summary"]["p99_value"] == 11.0
    assert payload["summary"]["p99_value_to_cost_ratio"] == 2.2
    assert payload["summary"]["biggest_upside_score"] is not None
    assert payload["summary"]["biggest_upside_rank"] == 1
    assert payload["summary"]["biggest_upside_tier"] == "S"
    assert payload["summary"]["relative_average_return_score"] == 50.0
    assert payload["meta"]["sources"]["summary_source"] == "explore_rip_statistics_latest"
    assert payload["meta"]["sources"]["simulation_derived_metrics"] == "SKIPPED_RIP_SUMMARY"
    assert payload["meta"]["sources"]["average_return_relative"] == "SERVICE_COMPUTED"


def test_pull_rate_assumptions_are_exposed_from_set_config_and_run_inputs(monkeypatch):
    handlers = _build_success_handlers(run_id="run-pull-rate")

    handlers["explore_rip_statistics_latest"] = lambda _q: [
        {
            "set_id": "base-set",
            "calculation_run_id": "run-pull-rate",
            "run_at": "2026-01-01T00:00:00Z",
            "pack_score": 78.1,
            "relative_pack_score": 81.4,
            "pack_rank": 3,
            "pack_tier": "A",
            "profit_score": 70.0,
            "safety_score": 73.0,
            "stability_score": 69.0,
            "profit_rank": 4,
            "profit_tier": "A",
            "safety_rank": 2,
            "safety_tier": "A",
            "stability_rank": 5,
            "stability_tier": "B",
            "relative_profit_score": 70.0,
            "relative_safety_score": 73.0,
            "relative_stability_score": 69.0,
            "pack_cost": 5.0,
            "mean_value": 5.55,
            "median_value": 5.1,
            "roi_percent": 11.2,
            "prob_profit": 0.54,
            "p95_value_to_cost_ratio": 1.9,
            "p99_value_to_cost_ratio": 2.5,
            "mean_value_to_cost_ratio": 1.11,
            "median_value_to_cost_ratio": 1.02,
            "expected_loss_when_losing_fraction": 0.33,
            "median_loss_when_losing_fraction": 0.29,
            "p05_shortfall_to_cost": 0.41,
            "expected_loss_when_losing": 1.2,
            "median_loss_when_losing": 1.0,
            "expected_loss_per_pack": 0.6,
            "tail_value_p05": 2.1,
            "coefficient_of_variation": 0.8,
            "hhi_ev_concentration": 0.14,
            "effective_chase_count": 7.3,
            "top1_ev_share": 0.18,
            "top3_ev_share": 0.35,
            "top5_ev_share": 0.47,
        }
    ]

    handlers["simulation_input_cards_with_near_mint_price"] = lambda _q: [
        {
            "card_id": "rr-card-1",
            "card_variant_id": "rr-variant-1",
            "card_name": "Regular Reverse One",
            "rarity_bucket": "regular reverse",
        },
        {
            "card_id": "rr-card-2",
            "card_variant_id": "rr-variant-2",
            "card_name": "Regular Reverse Two",
            "rarity_bucket": "regular reverse",
        },
        {
            "card_id": "rr-card-3",
            "card_variant_id": "rr-variant-3",
            "card_name": "Regular Reverse Three",
            "rarity_bucket": "regular reverse",
        },
        {
            "card_id": "card-1",
            "card_variant_id": "variant-1",
            "card_name": "Hit One",
            "rarity_bucket": "special illustration rare",
        },
        {
            "card_id": "card-2",
            "card_variant_id": "variant-2",
            "card_name": "Hit Two",
            "rarity_bucket": "special illustration rare",
        },
        {
            "card_id": "card-3",
            "card_variant_id": "variant-3",
            "card_name": "Hit Three",
            "rarity_bucket": "ultra rare",
        },
    ]

    class _MockSetConfig:
        PULL_RATE_MAPPING = {
            "common": 67,
            "uncommon": 43,
            "rare": 12,
            "double rare": 43,
            "illustration rare": 98,
            "special illustration rare": 487,
            "ultra rare": 211,
            "mega hyper rare": 1786,
        }
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {
                "regular reverse": 1,
            },
            "slot_2": {
                "illustration rare": 1 / 9,
                "special illustration rare": 1 / 81,
                "mega hyper rare": 1 / 1786,
                "regular reverse": 1 - (1 / 9) - (1 / 81) - (1 / 1786),
            }
        }
        RARE_SLOT_PROBABILITY = {
            "double rare": 1 / 5,
            "ultra rare": 1 / 12,
            "rare": 1 - (1 / 5) - (1 / 12),
        }
        SLOTS_PER_RARITY = {
            "common": 4,
            "uncommon": 3,
            "reverse": 2,
            "rare": 1,
        }

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    def _sets_handler(query):
        eq_by_field = {field: value for field, value in query.eq_filters}
        if eq_by_field.get("id") == "base-set":
            return [
                {
                    "id": "base-set",
                    "name": "Base Set",
                    "canonical_key": "base-set",
                    "pokemon_api_set_id": "base-set",
                }
            ]
        return []

    handlers["sets"] = _sets_handler
    monkeypatch.setattr(service, "_resolve_set_config", lambda _target_id: (_MockSetConfig, "mockSet"))

    payload = service.get_explore_page_payload("set", "base-set")

    assumptions = payload.get("pull_rate_assumptions")
    assert assumptions is not None
    assert assumptions["meta"]["is_modelled"] is True
    assert assumptions["meta"]["is_modeled"] is True
    assert assumptions["meta"]["source_label"] == "Config-based pack model + inDex-derived card counts"

    groups_by_key = {group["key"]: group for group in assumptions["groups"]}
    assert set(groups_by_key.keys()) == {"pack_structure", "hit_rarity_model", "special_pack_rules"}

    pack_rows = {row["rarity"]: row for row in groups_by_key["pack_structure"]["rows"]}
    assert "common" in pack_rows
    assert "uncommon" in pack_rows
    assert "rare" in pack_rows
    assert "regular reverse" in pack_rows
    assert pack_rows["common"]["expected_cards_per_pack"] == 4.0
    assert pack_rows["common"]["card_count"] == 67
    assert pack_rows["common"]["specific_card_odds_denominator"] == 16.75
    assert pack_rows["uncommon"]["expected_cards_per_pack"] == 3.0
    assert pack_rows["uncommon"]["card_count"] == 43
    assert pack_rows["uncommon"]["specific_card_odds_denominator"] == (43 / 3)
    assert pack_rows["rare"]["slot_label"] == "Rare slot model"
    assert pack_rows["rare"]["card_count"] == 12
    assert round(pack_rows["rare"]["expected_cards_per_pack"], 4) == round(1 - (1 / 5) - (1 / 12), 4)
    assert round(pack_rows["rare"]["specific_card_odds_denominator"], 1) == 16.7
    assert pack_rows["regular reverse"]["slot_label"] == "Reverse slot model"
    assert round(pack_rows["regular reverse"]["expected_cards_per_pack"], 3) == 1.876
    assert pack_rows["regular reverse"]["card_count"] == 3
    assert round(pack_rows["regular reverse"]["specific_card_odds_denominator"], 2) == 1.60

    hit_rows = {row["rarity"]: row for row in groups_by_key["hit_rarity_model"]["rows"]}
    assert "double rare" in hit_rows
    assert "ultra rare" in hit_rows
    assert "illustration rare" in hit_rows
    assert "special illustration rare" in hit_rows
    assert "mega hyper rare" in hit_rows
    assert hit_rows["double rare"]["specific_card_odds_denominator"] == 43
    assert hit_rows["ultra rare"]["specific_card_odds_denominator"] == 211
    assert hit_rows["illustration rare"]["specific_card_odds_denominator"] == 98
    assert hit_rows["special illustration rare"]["specific_card_odds_denominator"] == 487
    assert hit_rows["mega hyper rare"]["specific_card_odds_denominator"] == 1786

    assert groups_by_key["special_pack_rules"]["rows"] == []
    assert payload["summary"]["pack_score"] == 78.1
    assert payload["meta"]["sources"]["pull_rate_assumptions_regular_reverse_count"] == "OK"
    assert "pull_rate_assumptions_bucket_classification_source" not in payload["meta"]["sources"]


def test_pull_rate_assumptions_regular_reverse_specific_odds_require_eligible_pool(monkeypatch):
    handlers = _build_success_handlers(run_id="run-pull-rate-no-reverse")

    handlers["explore_rip_statistics_latest"] = lambda _q: [
        {
            "set_id": "base-set",
            "calculation_run_id": "run-pull-rate-no-reverse",
            "run_at": "2026-01-01T00:00:00Z",
            "pack_score": 78.1,
            "relative_pack_score": 81.4,
            "pack_rank": 3,
            "pack_tier": "A",
            "profit_score": 70.0,
            "safety_score": 73.0,
            "stability_score": 69.0,
            "profit_rank": 4,
            "profit_tier": "A",
            "safety_rank": 2,
            "safety_tier": "A",
            "stability_rank": 5,
            "stability_tier": "B",
            "relative_profit_score": 70.0,
            "relative_safety_score": 73.0,
            "relative_stability_score": 69.0,
            "pack_cost": 5.0,
            "mean_value": 5.55,
            "median_value": 5.1,
            "roi_percent": 11.2,
            "prob_profit": 0.54,
            "p95_value_to_cost_ratio": 1.9,
            "p99_value_to_cost_ratio": 2.5,
            "mean_value_to_cost_ratio": 1.11,
            "median_value_to_cost_ratio": 1.02,
            "expected_loss_when_losing_fraction": 0.33,
            "median_loss_when_losing_fraction": 0.29,
            "p05_shortfall_to_cost": 0.41,
            "expected_loss_when_losing": 1.2,
            "median_loss_when_losing": 1.0,
            "expected_loss_per_pack": 0.6,
            "tail_value_p05": 2.1,
            "coefficient_of_variation": 0.8,
            "hhi_ev_concentration": 0.14,
            "effective_chase_count": 7.3,
            "top1_ev_share": 0.18,
            "top3_ev_share": 0.35,
            "top5_ev_share": 0.47,
        }
    ]

    handlers["simulation_input_cards_with_near_mint_price"] = lambda _q: []

    class _MockSetConfig:
        PULL_RATE_MAPPING = {
            "common": 67,
            "uncommon": 43,
            "rare": 12,
            "double rare": 43,
            "illustration rare": 98,
            "special illustration rare": 487,
            "ultra rare": 211,
            "mega hyper rare": 1786,
        }
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {
                "regular reverse": 1,
            },
            "slot_2": {
                "illustration rare": 1 / 9,
                "special illustration rare": 1 / 81,
                "mega hyper rare": 1 / 1786,
                "regular reverse": 1 - (1 / 9) - (1 / 81) - (1 / 1786),
            },
        }
        RARE_SLOT_PROBABILITY = {
            "double rare": 1 / 5,
            "ultra rare": 1 / 12,
            "rare": 1 - (1 / 5) - (1 / 12),
        }

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)
    handlers["sets"] = lambda _q: [
        {
            "id": "base-set",
            "name": "Base Set",
            "canonical_key": "base-set",
            "pokemon_api_set_id": "base-set",
        }
    ]
    monkeypatch.setattr(service, "_resolve_set_config", lambda _target_id: (_MockSetConfig, "mockSet"))

    payload = service.get_explore_page_payload("set", "base-set")
    assumptions = payload.get("pull_rate_assumptions")
    groups_by_key = {group["key"]: group for group in assumptions["groups"]}
    pack_rows = {row["rarity"]: row for row in groups_by_key["pack_structure"]["rows"]}

    assert round(pack_rows["regular reverse"]["expected_cards_per_pack"], 3) == 1.876
    assert pack_rows["regular reverse"]["card_count"] is None
    assert pack_rows["regular reverse"]["specific_card_odds_denominator"] is None
    assert payload["meta"]["sources"]["pull_rate_assumptions_regular_reverse_count"] == "UNAVAILABLE"


def test_pull_rate_assumptions_resolve_set_config_via_sets_metadata_for_uuid_target(monkeypatch):
    handlers = _build_success_handlers(run_id="run-pull-rate-uuid")

    handlers["explore_rip_statistics_latest"] = lambda _q: [
        {
            "set_id": "set-uuid-1",
            "calculation_run_id": "run-pull-rate-uuid",
            "run_at": "2026-01-01T00:00:00Z",
            "pack_score": 78.1,
            "relative_pack_score": 81.4,
            "pack_rank": 3,
            "pack_tier": "A",
            "profit_score": 70.0,
            "safety_score": 73.0,
            "stability_score": 69.0,
            "profit_rank": 4,
            "profit_tier": "A",
            "safety_rank": 2,
            "safety_tier": "A",
            "stability_rank": 5,
            "stability_tier": "B",
            "relative_profit_score": 70.0,
            "relative_safety_score": 73.0,
            "relative_stability_score": 69.0,
            "pack_cost": 5.0,
            "mean_value": 5.55,
            "median_value": 5.1,
            "roi_percent": 11.2,
            "prob_profit": 0.54,
            "p95_value_to_cost_ratio": 1.9,
            "p99_value_to_cost_ratio": 2.5,
            "mean_value_to_cost_ratio": 1.11,
            "median_value_to_cost_ratio": 1.02,
            "expected_loss_when_losing_fraction": 0.33,
            "median_loss_when_losing_fraction": 0.29,
            "p05_shortfall_to_cost": 0.41,
            "expected_loss_when_losing": 1.2,
            "median_loss_when_losing": 1.0,
            "expected_loss_per_pack": 0.6,
            "tail_value_p05": 2.1,
            "coefficient_of_variation": 0.8,
            "hhi_ev_concentration": 0.14,
            "effective_chase_count": 7.3,
            "top1_ev_share": 0.18,
            "top3_ev_share": 0.35,
            "top5_ev_share": 0.47,
        }
    ]

    handlers["sets"] = lambda query: [
        {
            "id": "set-uuid-1",
            "name": "Mega Evolution",
            "canonical_key": "mega-evolution",
            "pokemon_api_set_id": "me1",
        }
    ] if any(field == "id" and value == "set-uuid-1" for field, value in query.eq_filters) else []

    handlers["simulation_input_cards_with_near_mint_price"] = lambda _q: []

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "set-uuid-1")

    assumptions = payload.get("pull_rate_assumptions")
    assert assumptions is not None
    assert len(assumptions["groups"]) == 3
    assert len(assumptions["rows"]) > 0
    assert payload["meta"]["sources"]["pull_rate_assumptions_set_metadata"] == "OK"
    assert payload["meta"]["sources"]["pull_rate_assumptions_config_resolution"] == "OK:megaEvolution"


def test_pull_rate_assumptions_include_god_pack_special_rule_for_151(monkeypatch):
    handlers = _build_success_handlers(run_id="run-pull-rate-151")

    handlers["explore_rip_statistics_latest"] = lambda _q: [
        {
            "set_id": "set-uuid-151",
            "calculation_run_id": "run-pull-rate-151",
            "run_at": "2026-01-01T00:00:00Z",
            "pack_score": 78.1,
            "relative_pack_score": 81.4,
            "pack_rank": 3,
            "pack_tier": "A",
            "profit_score": 70.0,
            "safety_score": 73.0,
            "stability_score": 69.0,
            "profit_rank": 4,
            "profit_tier": "A",
            "safety_rank": 2,
            "safety_tier": "A",
            "stability_rank": 5,
            "stability_tier": "B",
            "relative_profit_score": 70.0,
            "relative_safety_score": 73.0,
            "relative_stability_score": 69.0,
            "pack_cost": 5.0,
            "mean_value": 5.55,
            "median_value": 5.1,
            "roi_percent": 11.2,
            "prob_profit": 0.54,
            "p95_value_to_cost_ratio": 1.9,
            "p99_value_to_cost_ratio": 2.5,
            "mean_value_to_cost_ratio": 1.11,
            "median_value_to_cost_ratio": 1.02,
            "expected_loss_when_losing_fraction": 0.33,
            "median_loss_when_losing_fraction": 0.29,
            "p05_shortfall_to_cost": 0.41,
            "expected_loss_when_losing": 1.2,
            "median_loss_when_losing": 1.0,
            "expected_loss_per_pack": 0.6,
            "tail_value_p05": 2.1,
            "coefficient_of_variation": 0.8,
            "hhi_ev_concentration": 0.14,
            "effective_chase_count": 7.3,
            "top1_ev_share": 0.18,
            "top3_ev_share": 0.35,
            "top5_ev_share": 0.47,
        }
    ]

    handlers["sets"] = lambda query: [
        {
            "id": "set-uuid-151",
            "name": "Scarlet and Violet 151",
            "canonical_key": "scarletAndViolet151",
            "pokemon_api_set_id": "sv3pt5",
        }
    ] if any(field == "id" and value == "set-uuid-151" for field, value in query.eq_filters) else []

    handlers["simulation_input_cards_with_near_mint_price"] = lambda _q: []

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "set-uuid-151")
    assumptions = payload.get("pull_rate_assumptions")

    assert assumptions is not None
    groups_by_key = {group["key"]: group for group in assumptions["groups"]}
    assert "special_pack_rules" in groups_by_key
    special_rows = {row["rarity"]: row for row in groups_by_key["special_pack_rules"]["rows"]}
    assert "god pack" in special_rows
    assert special_rows["god pack"]["slot_label"] == "Special pack model"
    assert special_rows["god pack"]["rarity_odds_denominator"] == 2000


def _swsh_summary_row(set_id, run_id):
    return {
        "set_id": set_id,
        "calculation_run_id": run_id,
        "run_at": "2026-01-01T00:00:00Z",
        "pack_score": 78.1,
        "relative_pack_score": 81.4,
        "pack_rank": 3,
        "pack_tier": "A",
        "profit_score": 70.0,
        "safety_score": 73.0,
        "stability_score": 69.0,
        "profit_rank": 4,
        "profit_tier": "A",
        "safety_rank": 2,
        "safety_tier": "A",
        "stability_rank": 5,
        "stability_tier": "B",
        "relative_profit_score": 70.0,
        "relative_safety_score": 73.0,
        "relative_stability_score": 69.0,
        "pack_cost": 5.0,
        "mean_value": 5.55,
        "median_value": 5.1,
        "roi_percent": 11.2,
        "prob_profit": 0.54,
        "p95_value_to_cost_ratio": 1.9,
        "p99_value_to_cost_ratio": 2.5,
        "mean_value_to_cost_ratio": 1.11,
        "median_value_to_cost_ratio": 1.02,
        "expected_loss_when_losing_fraction": 0.33,
        "median_loss_when_losing_fraction": 0.29,
        "p05_shortfall_to_cost": 0.41,
        "expected_loss_when_losing": 1.2,
        "median_loss_when_losing": 1.0,
        "expected_loss_per_pack": 0.6,
        "tail_value_p05": 2.1,
        "coefficient_of_variation": 0.8,
        "hhi_ev_concentration": 0.14,
        "effective_chase_count": 7.3,
        "top1_ev_share": 0.18,
        "top3_ev_share": 0.35,
        "top5_ev_share": 0.47,
    }


def _build_swsh_input_rows(outcome_keys):
    rows = [
        {
            "card_id": "common-card-1",
            "card_variant_id": "common-variant-1",
            "card_name": "Common One",
            "rarity_bucket": "common",
        },
        {
            "card_id": "common-card-2",
            "card_variant_id": "common-variant-2",
            "card_name": "Common Two",
            "rarity_bucket": "common",
        },
        {
            "card_id": "uncommon-card-1",
            "card_variant_id": "uncommon-variant-1",
            "card_name": "Uncommon One",
            "rarity_bucket": "uncommon",
        },
        {
            "card_id": "regular-reverse-card-1",
            "card_variant_id": "regular-reverse-variant-1",
            "card_name": "Regular Reverse One",
            "rarity_bucket": "regular reverse",
        },
    ]

    for index, outcome_key in enumerate(outcome_keys, start=1):
        slug = outcome_key.replace(" ", "-")
        rows.append(
            {
                "card_id": f"{slug}-card-{index}",
                "card_variant_id": f"{slug}-variant-{index}",
                "card_name": f"{outcome_key.title()} Card {index}",
                "rarity_bucket": outcome_key,
            }
        )

    return rows


def _build_swsh7_live_shaped_hit_rows():
    # Live-shaped rows intentionally keep broad rarity_bucket=hits and rely on
    # card/variant metadata for modeled bucket classification.
    return [
        {
            "card_id": "live-card-holo-rare",
            "card_variant_id": "live-variant-holo-rare",
            "card_name": "Hydreigon",
            "rarity_bucket": "hits",
        },
        {
            "card_id": "live-card-regular-v",
            "card_variant_id": "live-variant-regular-v",
            "card_name": "Rayquaza V",
            "rarity_bucket": "hits",
        },
        {
            "card_id": "live-card-regular-vmax",
            "card_variant_id": "live-variant-regular-vmax",
            "card_name": "Rayquaza VMAX",
            "rarity_bucket": "hits",
        },
        {
            "card_id": "live-card-full-art-v",
            "card_variant_id": "live-variant-full-art-v",
            "card_name": "Noivern V (Full Art)",
            "rarity_bucket": "hits",
        },
        {
            "card_id": "live-card-full-art-trainer",
            "card_variant_id": "live-variant-full-art-trainer",
            "card_name": "Copycat",
            "rarity_bucket": "hits",
        },
        {
            "card_id": "live-card-alt-art-v",
            "card_variant_id": "live-variant-alt-art-v",
            "card_name": "Umbreon V (Alternate Full Art)",
            "rarity_bucket": "hits",
        },
        {
            "card_id": "live-card-alt-art-vmax",
            "card_variant_id": "live-variant-alt-art-vmax",
            "card_name": "Umbreon VMAX Alternate Art Secret",
            "rarity_bucket": "hits",
        },
        {
            "card_id": "live-card-rainbow-trainer",
            "card_variant_id": "live-variant-rainbow-trainer",
            "card_name": "Raihan",
            "rarity_bucket": "hits",
        },
        {
            "card_id": "live-card-rainbow-vmax",
            "card_variant_id": "live-variant-rainbow-vmax",
            "card_name": "Glaceon VMAX",
            "rarity_bucket": "hits",
        },
        {
            "card_id": "live-card-gold-secret-rare",
            "card_variant_id": "live-variant-gold-secret-rare",
            "card_name": "Boost Shake",
            "rarity_bucket": "hits",
        },
        {
            "card_id": "live-card-generic-hits",
            "card_variant_id": "live-variant-generic-hits",
            "card_name": "Generic Hit",
            "rarity_bucket": "hits",
        },
    ]


def _build_swsh7_live_card_rows():
    return [
        {"id": "live-card-holo-rare", "name": "Hydreigon", "rarity": "Holo Rare", "card_number": "109"},
        {"id": "live-card-regular-v", "name": "Rayquaza V", "rarity": "Ultra Rare", "card_number": "110"},
        {"id": "live-card-regular-vmax", "name": "Rayquaza VMAX", "rarity": "Ultra Rare", "card_number": "111"},
        {
            "id": "live-card-full-art-v",
            "name": "Noivern V (Full Art)",
            "rarity": "Ultra Rare",
            "card_number": "170",
        },
        {"id": "live-card-full-art-trainer", "name": "Copycat", "rarity": "Ultra Rare", "card_number": "200"},
        {
            "id": "live-card-alt-art-v",
            "name": "Umbreon V (Alternate Full Art)",
            "rarity": "Ultra Rare",
            "card_number": "189",
        },
        {
            "id": "live-card-alt-art-vmax",
            "name": "Umbreon VMAX Alternate Art Secret",
            "rarity": "Secret Rare",
            "card_number": "215",
        },
        {"id": "live-card-rainbow-trainer", "name": "Raihan", "rarity": "Secret Rare", "card_number": "222"},
        {"id": "live-card-rainbow-vmax", "name": "Glaceon VMAX", "rarity": "Secret Rare", "card_number": "210"},
        {
            "id": "live-card-gold-secret-rare",
            "name": "Boost Shake",
            "rarity": "Secret Rare",
            "card_number": "230",
        },
        {"id": "live-card-generic-hits", "name": "Generic Hit", "rarity": "Ultra Rare", "card_number": "1"},
    ]


def _build_swsh7_live_variant_rows():
    return [
        {"id": "live-variant-holo-rare", "card_id": "live-card-holo-rare", "printing_type": "holo"},
        {"id": "live-variant-regular-v", "card_id": "live-card-regular-v", "printing_type": "holo"},
        {"id": "live-variant-regular-vmax", "card_id": "live-card-regular-vmax", "printing_type": "holo"},
        {"id": "live-variant-full-art-v", "card_id": "live-card-full-art-v", "printing_type": "holo"},
        {
            "id": "live-variant-full-art-trainer",
            "card_id": "live-card-full-art-trainer",
            "printing_type": "holo",
        },
        {"id": "live-variant-alt-art-v", "card_id": "live-card-alt-art-v", "printing_type": "holo"},
        {
            "id": "live-variant-alt-art-vmax",
            "card_id": "live-card-alt-art-vmax",
            "printing_type": "holo",
        },
        {
            "id": "live-variant-rainbow-trainer",
            "card_id": "live-card-rainbow-trainer",
            "printing_type": "holo",
        },
        {
            "id": "live-variant-rainbow-vmax",
            "card_id": "live-card-rainbow-vmax",
            "printing_type": "holo",
        },
        {
            "id": "live-variant-gold-secret-rare",
            "card_id": "live-card-gold-secret-rare",
            "printing_type": "holo",
        },
        {"id": "live-variant-generic-hits", "card_id": "live-card-generic-hits", "printing_type": "holo"},
    ]


def _filter_rows_by_requested_ids(query, rows):
    requested_ids = set()
    for field, values in query.in_filters:
        if field == "id":
            requested_ids.update(str(value) for value in values)
    return [row for row in rows if str(row.get("id")) in requested_ids]


def _build_swsh6_card_and_variant_rows_for_runtime_outcomes():
    by_bucket = {
        "rare": {"name": "Cinderace", "rarity": "Rare", "card_number": "010", "printing_type": "non-holo"},
        "holo rare": {"name": "Zeraora", "rarity": "Holo Rare", "card_number": "011", "printing_type": "holo"},
        "regular v": {"name": "Celebi V", "rarity": "Ultra Rare", "card_number": "100", "printing_type": "holo"},
        "regular vmax": {"name": "Ice Rider Calyrex VMAX", "rarity": "Ultra Rare", "card_number": "101", "printing_type": "holo"},
        "full art v": {"name": "Tornadus V (Full Art)", "rarity": "Ultra Rare", "card_number": "170", "printing_type": "holo"},
        "full art trainer": {"name": "Peony", "rarity": "Ultra Rare", "card_number": "190", "printing_type": "holo"},
        "alternate art v": {"name": "Blaziken V (Alternate Full Art)", "rarity": "Ultra Rare", "card_number": "183", "printing_type": "holo"},
        "alternate art vmax": {"name": "Blaziken VMAX Alternate Art Secret", "rarity": "Secret Rare", "card_number": "201", "printing_type": "holo"},
        "rainbow rare": {"name": "Metagross VMAX", "rarity": "Secret Rare", "card_number": "210", "printing_type": "holo"},
        "gold rare": {"name": "Snorlax", "rarity": "Secret Rare", "card_number": "224", "printing_type": "holo"},
    }

    card_rows = []
    variant_rows = []
    for bucket, details in by_bucket.items():
        slug = bucket.replace(" ", "-")
        card_id = f"{slug}-card-1"
        variant_id = f"{slug}-variant-1"
        card_rows.append(
            {
                "id": card_id,
                "name": details["name"],
                "rarity": details["rarity"],
                "card_number": details["card_number"],
            }
        )
        variant_rows.append(
            {
                "id": variant_id,
                "card_id": card_id,
                "printing_type": details["printing_type"],
            }
        )

    return card_rows, variant_rows


def _build_swsh7_card_and_variant_rows_for_runtime_outcomes():
    by_bucket = {
        "rare": {"name": "Regidrago", "rarity": "Rare", "card_number": "010", "printing_type": "non-holo"},
        "holo rare": {"name": "Hydreigon", "rarity": "Holo Rare", "card_number": "109", "printing_type": "holo"},
        "regular v": {"name": "Rayquaza V", "rarity": "Ultra Rare", "card_number": "110", "printing_type": "holo"},
        "regular vmax": {"name": "Rayquaza VMAX", "rarity": "Ultra Rare", "card_number": "111", "printing_type": "holo"},
        "full art": {"name": "Noivern V (Full Art)", "rarity": "Ultra Rare", "card_number": "170", "printing_type": "holo"},
        "alternate art v": {"name": "Umbreon V (Alternate Full Art)", "rarity": "Ultra Rare", "card_number": "189", "printing_type": "holo"},
        "alternate art vmax": {"name": "Umbreon VMAX Alternate Art Secret", "rarity": "Secret Rare", "card_number": "215", "printing_type": "holo"},
        "rainbow rare": {"name": "Duraludon VMAX", "rarity": "Secret Rare", "card_number": "210", "printing_type": "holo"},
        "gold rare": {"name": "Boost Shake", "rarity": "Secret Rare", "card_number": "230", "printing_type": "holo"},
    }

    card_rows = []
    variant_rows = []
    for bucket, details in by_bucket.items():
        slug = bucket.replace(" ", "-")
        card_id = f"{slug}-card-1"
        variant_id = f"{slug}-variant-1"
        card_rows.append(
            {
                "id": card_id,
                "name": details["name"],
                "rarity": details["rarity"],
                "card_number": details["card_number"],
            }
        )
        variant_rows.append(
            {
                "id": variant_id,
                "card_id": card_id,
                "printing_type": details["printing_type"],
            }
        )

    return card_rows, variant_rows


def test_swsh6_modeled_pack_breakdown_uses_configured_rare_slot_buckets(monkeypatch):
    from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig

    handlers = _build_success_handlers(run_id="run-swsh6-modeled")
    handlers["explore_rip_statistics_latest"] = lambda _q: [_swsh_summary_row("swsh6", "run-swsh6-modeled")]
    handlers["simulation_pull_summary"] = lambda _q: [
        {
            "rarity_bucket": rarity_key,
            "pulled_count": index * 100,
            "avg_sampled_value": 1.0,
            "total_sampled_value": float(index * 100),
        }
        for index, rarity_key in enumerate(SetChillingReignConfig.RARE_SLOT_PROBABILITY.keys(), start=1)
    ]
    handlers["simulation_input_cards_with_near_mint_price"] = lambda _q: _build_swsh_input_rows(
        list(SetChillingReignConfig.RARE_SLOT_PROBABILITY.keys())
    )

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "swsh6")

    display = payload["rip_statistics"].get("pack_breakdown_display")
    assert display is not None
    assert display["mode"] == "modeled_outcome_states"
    assert display["supported"] is True
    assert display["combo_states_supported"] is False
    assert display["state_granularity"] == "single_bucket_aggregate"
    assert "combo co-occurrence is not persisted" in display["limitation_note"]
    assert display["source"] == "simulation_pull_summary"
    row_keys = [row["key"] for row in display["rows"]]
    assert set(row_keys) == set(SetChillingReignConfig.RARE_SLOT_PROBABILITY.keys())
    assert "slot_schema" not in row_keys
    assert all("God Pack" not in row["label"] for row in display["rows"])
    label_by_key = {row["key"]: row["label"] for row in display["rows"]}
    assert label_by_key["holo rare"] == "Holo Rare Bucket"
    assert label_by_key["regular v"] == "Regular V Bucket"
    assert label_by_key["alternate art v"] == "Alternate Art V Bucket"
    assert all("Only" not in row["label"] for row in display["rows"])


def test_swsh7_modeled_pack_breakdown_uses_configured_rare_slot_buckets(monkeypatch):
    from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig

    handlers = _build_success_handlers(run_id="run-swsh7-modeled")
    handlers["explore_rip_statistics_latest"] = lambda _q: [_swsh_summary_row("swsh7", "run-swsh7-modeled")]
    handlers["simulation_pull_summary"] = lambda _q: [
        {
            "rarity_bucket": rarity_key,
            "pulled_count": index * 100,
            "avg_sampled_value": 1.0,
            "total_sampled_value": float(index * 100),
        }
        for index, rarity_key in enumerate(SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY.keys(), start=1)
    ]
    handlers["simulation_input_cards_with_near_mint_price"] = lambda _q: _build_swsh_input_rows(
        list(SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY.keys())
    )

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "swsh7")

    display = payload["rip_statistics"].get("pack_breakdown_display")
    assert display is not None
    assert display["mode"] == "modeled_outcome_states"
    assert display["supported"] is True
    assert display["combo_states_supported"] is False
    assert display["state_granularity"] == "single_bucket_aggregate"
    assert "combo co-occurrence is not persisted" in display["limitation_note"]
    row_keys = [row["key"] for row in display["rows"]]
    assert set(row_keys) == set(SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY.keys())
    assert "slot_schema" not in row_keys
    assert all("Only" not in row["label"] for row in display["rows"])


def test_swsh6_pull_rate_assumptions_resolve_from_slot_schema_config(monkeypatch):
    from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig

    handlers = _build_success_handlers(run_id="run-swsh6-pull-rates")
    handlers["explore_rip_statistics_latest"] = lambda _q: [_swsh_summary_row("swsh6", "run-swsh6-pull-rates")]
    handlers["simulation_input_cards_with_near_mint_price"] = lambda _q: _build_swsh_input_rows(list(SetChillingReignConfig.RARE_SLOT_PROBABILITY.keys()))

    all_card_rows, all_variant_rows = _build_swsh6_card_and_variant_rows_for_runtime_outcomes()
    handlers["cards"] = lambda query: _filter_rows_by_requested_ids(query, all_card_rows)
    handlers["card_variants"] = lambda query: _filter_rows_by_requested_ids(query, all_variant_rows)

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "swsh6")
    assumptions = payload.get("pull_rate_assumptions")

    assert assumptions is not None
    groups_by_key = {group["key"]: group for group in assumptions["groups"]}
    hit_rows = {row["rarity"]: row for row in groups_by_key["hit_rarity_model"]["rows"]}
    assert set(hit_rows.keys()) == set(SetChillingReignConfig.RARE_SLOT_PROBABILITY.keys()) - {"rare"}

    # Each modeled bucket has one eligible card in the mocked simulation input,
    # so specific odds denominator should equal rarity odds denominator.
    for rarity_key, row in hit_rows.items():
        assert row["card_count"] == 1, f"expected card_count=1 for rarity {rarity_key}"
        assert row["rarity_odds_denominator"] is not None
        assert row["specific_card_odds_denominator"] == row["rarity_odds_denominator"]

    assert payload["meta"]["sources"]["pull_rate_assumptions_mapping_source"] == "SLOT_SCHEMA_RUNTIME_CONFIG"
    assert payload["meta"]["sources"]["pull_rate_assumptions_bucket_classification"] == "OK"


def test_swsh7_pull_rate_assumptions_resolve_from_slot_schema_config(monkeypatch):
    from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig

    handlers = _build_success_handlers(run_id="run-swsh7-pull-rates")
    handlers["explore_rip_statistics_latest"] = lambda _q: [_swsh_summary_row("swsh7", "run-swsh7-pull-rates")]
    handlers["simulation_input_cards_with_near_mint_price"] = lambda _q: _build_swsh_input_rows(list(SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY.keys()))

    all_card_rows, all_variant_rows = _build_swsh7_card_and_variant_rows_for_runtime_outcomes()
    handlers["cards"] = lambda query: _filter_rows_by_requested_ids(query, all_card_rows)
    handlers["card_variants"] = lambda query: _filter_rows_by_requested_ids(query, all_variant_rows)

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "swsh7")
    assumptions = payload.get("pull_rate_assumptions")

    assert assumptions is not None
    groups_by_key = {group["key"]: group for group in assumptions["groups"]}
    hit_rows = {row["rarity"]: row for row in groups_by_key["hit_rarity_model"]["rows"]}
    assert set(hit_rows.keys()) == set(SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY.keys()) - {"rare"}

    unsupported_keys = {
        "full art v",
        "full art trainer",
        "rainbow trainer",
        "rainbow vmax",
        "gold secret rare",
    }
    assert unsupported_keys.isdisjoint(hit_rows.keys())

    for rarity_key, row in hit_rows.items():
        assert row["card_count"] == 1, f"expected card_count=1 for rarity {rarity_key}"
        assert row["rarity_odds_denominator"] is not None
        expected_from_runtime_probability = round(1 / SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY[rarity_key])
        assert abs(row["rarity_odds_denominator"] - expected_from_runtime_probability) <= 1
        assert row["specific_card_odds_denominator"] == row["rarity_odds_denominator"]

    assert payload["meta"]["sources"]["pull_rate_assumptions_mapping_source"] == "SLOT_SCHEMA_RUNTIME_CONFIG"
    assert payload["meta"]["sources"]["pull_rate_assumptions_bucket_classification"] == "OK"


def test_swsh7_pull_rate_assumptions_classification_uses_native_fallback_when_pandas_missing(monkeypatch):
    handlers = _build_success_handlers(run_id="run-swsh7-native-fallback")
    handlers["explore_rip_statistics_latest"] = lambda _q: [_swsh_summary_row("swsh7", "run-swsh7-native-fallback")]
    handlers["simulation_input_cards_with_near_mint_price"] = lambda _q: _build_swsh7_live_shaped_hit_rows()

    all_card_rows = _build_swsh7_live_card_rows()
    all_variant_rows = _build_swsh7_live_variant_rows()
    handlers["cards"] = lambda query: _filter_rows_by_requested_ids(query, all_card_rows)
    handlers["card_variants"] = lambda query: _filter_rows_by_requested_ids(query, all_variant_rows)

    monkeypatch.setitem(sys.modules, "pandas", None)

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "swsh7")
    assumptions = payload.get("pull_rate_assumptions")

    assert assumptions is not None
    groups_by_key = {group["key"]: group for group in assumptions["groups"]}
    hit_rows = {row["rarity"]: row for row in groups_by_key["hit_rarity_model"]["rows"]}

    assert hit_rows["full art"]["card_count"] == 2
    assert hit_rows["rainbow rare"]["card_count"] == 2
    assert payload["meta"]["sources"]["pull_rate_assumptions_bucket_classification"] == "OK"


def test_swsh7_pull_rate_assumptions_classify_live_shaped_hits_with_read_time_metadata(monkeypatch):
    handlers = _build_success_handlers(run_id="run-swsh7-live-shaped")
    handlers["explore_rip_statistics_latest"] = lambda _q: [_swsh_summary_row("swsh7", "run-swsh7-live-shaped")]
    handlers["simulation_input_cards_with_near_mint_price"] = lambda _q: _build_swsh7_live_shaped_hit_rows()

    all_card_rows = _build_swsh7_live_card_rows()
    all_variant_rows = _build_swsh7_live_variant_rows()

    def _cards_handler(query):
        requested_ids = set()
        for field, values in query.in_filters:
            if field == "id":
                requested_ids.update(str(value) for value in values)
        return [row for row in all_card_rows if str(row.get("id")) in requested_ids]

    def _variants_handler(query):
        requested_ids = set()
        for field, values in query.in_filters:
            if field == "id":
                requested_ids.update(str(value) for value in values)
        return [row for row in all_variant_rows if str(row.get("id")) in requested_ids]

    handlers["cards"] = _cards_handler
    handlers["card_variants"] = _variants_handler

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "swsh7")
    assumptions = payload.get("pull_rate_assumptions")

    assert assumptions is not None
    groups_by_key = {group["key"]: group for group in assumptions["groups"]}
    hit_rows = {row["rarity"]: row for row in groups_by_key["hit_rarity_model"]["rows"]}

    assert hit_rows["regular v"]["card_count"] == 1
    assert hit_rows["alternate art vmax"]["card_count"] == 1
    assert hit_rows["full art"]["card_count"] == 2
    assert hit_rows["rainbow rare"]["card_count"] == 2
    assert hit_rows["gold rare"]["card_count"] == 1

    unsupported_keys = {
        "full art v",
        "full art trainer",
        "rainbow trainer",
        "rainbow vmax",
        "gold secret rare",
    }
    assert unsupported_keys.isdisjoint(hit_rows.keys())

    for rarity in ("regular v", "alternate art vmax", "full art"):
        row = hit_rows[rarity]
        assert row["rarity_odds_denominator"] is not None
        assert row["specific_card_odds_denominator"] == row["rarity_odds_denominator"] * row["card_count"]

    for rarity in ("rainbow rare", "gold rare"):
        row = hit_rows[rarity]
        assert row["rarity_odds_denominator"] is not None
        assert row["specific_card_odds_denominator"] == row["rarity_odds_denominator"] * row["card_count"]

    assert "hits" not in hit_rows
    assert payload["meta"]["sources"]["pull_rate_assumptions_mapping_source"] == "SLOT_SCHEMA_RUNTIME_CONFIG"
    assert payload["meta"]["sources"]["pull_rate_assumptions_bucket_classification"] == "OK"
    assert (
        payload["meta"]["sources"]["pull_rate_assumptions_bucket_classification_source"]
        == "READ_TIME_CARD_METADATA_CLASSIFICATION"
    )


def test_swsh7_pull_rate_assumptions_without_metadata_keep_specific_odds_unavailable(monkeypatch):
    handlers = _build_success_handlers(run_id="run-swsh7-metadata-missing")
    handlers["explore_rip_statistics_latest"] = lambda _q: [_swsh_summary_row("swsh7", "run-swsh7-metadata-missing")]
    handlers["simulation_input_cards_with_near_mint_price"] = lambda _q: _build_swsh7_live_shaped_hit_rows()
    handlers["cards"] = lambda _q: []
    handlers["card_variants"] = lambda _q: []

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "swsh7")
    assumptions = payload.get("pull_rate_assumptions")

    assert assumptions is not None
    groups_by_key = {group["key"]: group for group in assumptions["groups"]}
    hit_rows = {row["rarity"]: row for row in groups_by_key["hit_rarity_model"]["rows"]}

    assert hit_rows["regular v"]["card_count"] is None
    assert hit_rows["regular v"]["specific_card_odds_denominator"] is None
    assert "require eligible card counts" in (hit_rows["regular v"].get("notes") or "")

    assert payload["meta"]["sources"]["pull_rate_assumptions_bucket_classification"] == "UNAVAILABLE"
    assert (
        payload["meta"]["sources"]["pull_rate_assumptions_bucket_classification_source"]
        == "READ_TIME_CARD_METADATA_CLASSIFICATION"
    )
    assert any(
        "Slot-schema bucket classification requires card metadata columns"
        in warning
        for warning in payload["meta"]["warnings"]
    )


def test_swsh_pull_rate_assumptions_exclude_generic_hits_bucket(monkeypatch):
    from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig

    handlers = _build_success_handlers(run_id="run-swsh7-generic-hits")
    handlers["explore_rip_statistics_latest"] = lambda _q: [_swsh_summary_row("swsh7", "run-swsh7-generic-hits")]

    def _rows(_q):
        rows = _build_swsh_input_rows(list(SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY.keys()))
        rows.append(
            {
                "card_id": "generic-hit-card-1",
                "card_variant_id": "generic-hit-variant-1",
                "card_name": "Generic Hit Card",
                "rarity_bucket": "hits",
            }
        )
        return rows

    handlers["simulation_input_cards_with_near_mint_price"] = _rows

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "swsh7")
    assumptions = payload.get("pull_rate_assumptions")

    assert assumptions is not None
    groups_by_key = {group["key"]: group for group in assumptions["groups"]}
    hit_rows = {row["rarity"] for row in groups_by_key["hit_rarity_model"]["rows"]}
    assert "hits" not in hit_rows


def test_swsh_modeled_bucket_missing_eligible_count_keeps_specific_odds_unavailable(monkeypatch):
    from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig

    handlers = _build_success_handlers(run_id="run-swsh6-missing-eligible")
    handlers["explore_rip_statistics_latest"] = lambda _q: [_swsh_summary_row("swsh6", "run-swsh6-missing-eligible")]

    missing_bucket = next(
        key for key in SetChillingReignConfig.RARE_SLOT_PROBABILITY.keys() if key != "rare"
    )

    def _rows(_q):
        base_rows = _build_swsh_input_rows(list(SetChillingReignConfig.RARE_SLOT_PROBABILITY.keys()))
        return [row for row in base_rows if str(row.get("rarity_bucket")) != missing_bucket]

    handlers["simulation_input_cards_with_near_mint_price"] = _rows

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "swsh6")
    assumptions = payload.get("pull_rate_assumptions")

    assert assumptions is not None
    groups_by_key = {group["key"]: group for group in assumptions["groups"]}
    hit_rows = {row["rarity"]: row for row in groups_by_key["hit_rarity_model"]["rows"]}

    missing_row = hit_rows[missing_bucket]
    assert missing_row["card_count"] is None
    assert missing_row["specific_card_odds_denominator"] is None
    assert "require eligible card counts" in (missing_row.get("notes") or "")

    # Broad pack-structure rows remain present.
    pack_rows = {row["rarity"]: row for row in groups_by_key["pack_structure"]["rows"]}
    assert {"common", "uncommon", "rare", "regular reverse"}.issubset(pack_rows.keys())


def test_non_swsh_sets_do_not_emit_modeled_pack_breakdown_display(monkeypatch):
    handlers = _build_success_handlers(run_id="run-base-no-modeled-display")
    handlers["explore_rip_statistics_latest"] = lambda _q: [_swsh_summary_row("base-set", "run-base-no-modeled-display")]

    client = _Client(handlers)
    monkeypatch.setattr(service, "public_read_client", client)

    payload = service.get_explore_page_payload("set", "base-set")

    assert payload["rip_statistics"].get("pack_breakdown_display") is None
