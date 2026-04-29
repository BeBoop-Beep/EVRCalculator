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
        "simulation_input_cards": lambda _q: [],
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
    top_hits_calls = [c for c in client.calls if c.table_name == "simulation_input_cards"]

    assert len(distribution_calls) == 1
    assert len(top_hits_calls) == 1
    assert distribution_calls[0].limit_value == 200
    assert top_hits_calls[0].limit_value == 1


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
    handlers["simulation_input_cards"] = lambda _q: [
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
