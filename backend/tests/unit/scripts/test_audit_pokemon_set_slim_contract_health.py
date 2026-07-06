from backend.scripts import audit_pokemon_set_slim_contract_health as audit


def test_read_only_audit_flag_is_true():
    assert audit.READ_ONLY_AUDIT is True


def test_measure_payload_bytes_matches_utf8_json_length():
    payload = {"name": "Prismatic Evolutions", "value": 12.5}
    import json

    expected = len(json.dumps(payload, default=str).encode("utf-8"))
    assert audit.measure_payload_bytes(payload) == expected


def test_measure_payload_bytes_handles_none():
    assert audit.measure_payload_bytes(None) == 0


def test_measure_payload_bytes_counts_multibyte_characters_correctly():
    # json.dumps defaults to ensure_ascii=True, so non-ASCII characters are
    # escaped (e.g. "\\u00e9"), not emitted as raw multi-byte UTF-8 — the byte
    # count must reflect that escaped, all-ASCII wire representation.
    import json

    payload = {"name": "Pokémon"}
    serialized = json.dumps(payload, default=str)
    assert "\\u00e9" in serialized, "sanity check: json.dumps must escape non-ASCII by default"
    assert audit.measure_payload_bytes(payload) == len(serialized.encode("utf-8")) == len(serialized)


def test_classify_health_status_error_takes_priority_over_everything():
    status = audit.classify_health_status(has_data=True, byte_size=10, budget_bytes=1_000_000, errored=True)
    assert status == "error"


def test_classify_health_status_over_budget_even_when_data_present():
    status = audit.classify_health_status(has_data=True, byte_size=500_000, budget_bytes=250_000)
    assert status == "over_budget"


def test_classify_health_status_empty_when_no_data_and_within_budget():
    status = audit.classify_health_status(has_data=False, byte_size=100, budget_bytes=250_000)
    assert status == "empty"


def test_classify_health_status_healthy_when_data_present_and_within_budget():
    status = audit.classify_health_status(has_data=True, byte_size=1_000, budget_bytes=250_000)
    assert status == "healthy"


def test_classify_missing_data_warning_returns_none_when_data_present():
    assert audit.classify_missing_data_warning("top_chase", has_data=True) is None


def test_classify_missing_data_warning_names_the_contract_label():
    warning = audit.classify_missing_data_warning("top_chase", has_data=False)
    assert warning is not None
    assert "market/top-chase" in warning
    assert "no usable data" in warning


def test_classify_missing_data_warning_falls_back_to_raw_key_for_unknown_contract():
    warning = audit.classify_missing_data_warning("mystery_contract", has_data=False)
    assert warning == "mystery_contract has no usable data for this set"


def test_classify_budget_violation_returns_none_within_budget():
    assert audit.classify_budget_violation("shell", 50_000, 75_000) is None


def test_classify_budget_violation_returns_none_at_exact_budget_boundary():
    assert audit.classify_budget_violation("shell", 75_000, 75_000) is None


def test_classify_budget_violation_returns_none_for_zero_budget():
    assert audit.classify_budget_violation("shell", 999, 0) is None


def test_classify_budget_violation_reports_the_contract_label_and_sizes():
    warning = audit.classify_budget_violation("insights", 450_000, 400_000)
    assert warning is not None
    assert "insights" in warning
    assert "450,000B" in warning
    assert "400,000B" in warning


def test_worst_sets_by_missing_contracts_sorts_descending_and_truncates():
    rows = [
        {"set_name": "Alpha", "missing_contract_count": 1},
        {"set_name": "Beta", "missing_contract_count": 4},
        {"set_name": "Gamma", "missing_contract_count": 0},
        {"set_name": "Delta", "missing_contract_count": 2},
    ]
    ranked = audit.worst_sets_by_missing_contracts(rows, top_n=2)
    assert ranked == [("Beta", 4), ("Delta", 2)]


def test_worst_sets_by_missing_contracts_defaults_missing_count_to_zero():
    rows = [{"set_name": "Alpha"}]
    ranked = audit.worst_sets_by_missing_contracts(rows, top_n=5)
    assert ranked == [("Alpha", 0)]


def test_payload_budgets_cover_all_eight_contracts():
    assert set(audit.PAYLOAD_BUDGETS_BYTES.keys()) == set(audit.CONTRACT_LABELS.keys())
    assert audit.PAYLOAD_BUDGETS_BYTES["shell"] == 75_000
    assert audit.PAYLOAD_BUDGETS_BYTES["overview"] == 250_000
    assert audit.PAYLOAD_BUDGETS_BYTES["top_chase"] == 250_000
    assert audit.PAYLOAD_BUDGETS_BYTES["movers"] == 150_000
    assert audit.PAYLOAD_BUDGETS_BYTES["cards_page"] == 250_000
    assert audit.PAYLOAD_BUDGETS_BYTES["cards_validation"] == 250_000
    assert audit.PAYLOAD_BUDGETS_BYTES["pull_rates"] == 150_000
    assert audit.PAYLOAD_BUDGETS_BYTES["insights"] == 400_000


def test_audit_set_is_read_only_and_uses_injected_services_only(monkeypatch):
    """audit_set must never reach for the real DB-backed service modules when
    services are injected — proves the function takes services as data, not
    as a hidden import side effect, which is what keeps this script testable
    (and keeps a future test from accidentally hitting a real database)."""

    calls = []

    class _FakeModule:
        def __init__(self, name):
            self._name = name

        def __getattr__(self, attr_name):
            def _fn(*args, **kwargs):
                calls.append((self._name, attr_name, args, kwargs))
                if attr_name == "get_pokemon_set_shell_snapshot_payload":
                    return {"set": {"id": args[0]}, "summary": {"pack_score": 10}}
                if attr_name == "get_pokemon_set_overview_snapshot_payload":
                    return {"setValueHistoriesByScope": {"standard": [{"date": "2026-01-01", "setValue": 1}]}, "performanceVsCostHistory": []}
                if attr_name == "get_pokemon_set_top_chase_snapshot_payload":
                    return {"topChaseCards": [], "topChaseCardHistories": {}}
                if attr_name == "get_pokemon_set_market_movers_payload":
                    return {"marketMovers": {"heatingUp": [], "coolingOff": []}}
                if attr_name == "get_pokemon_set_cards_page_snapshot_payload":
                    return {"cards": [{"id": "card-1"}], "pagination": {"totalCards": 1}}
                if attr_name == "get_pokemon_set_card_validation_snapshot_payload":
                    return {"cards": [{"id": "card-1"}], "cardAppealMarketPriceCorrelation": {"n": 1}}
                if attr_name == "get_pokemon_set_pull_rates_snapshot_payload":
                    return {"pullRates": None}
                if attr_name == "get_pokemon_set_insights_snapshot_payload":
                    return {"summary": {}, "outcomeDistribution": {"distributionBins": []}, "simulationDrivers": []}
                raise AssertionError(f"unexpected call {attr_name}")

            return _fn

    services = {
        "shell": _FakeModule("shell"),
        "overview": _FakeModule("overview"),
        "top_chase": _FakeModule("top_chase"),
        "movers": _FakeModule("movers"),
        "cards_page": _FakeModule("cards_page"),
        "cards_validation": _FakeModule("cards_validation"),
        "pull_rates": _FakeModule("pull_rates"),
        "insights": _FakeModule("insights"),
    }

    row = audit.audit_set({"id": "set-1", "name": "Test Set", "canonical_key": "testSet"}, services=services)

    assert row["set_id"] == "set-1"
    assert row["has_shell"] is True
    assert row["has_overview"] is True
    assert row["has_top_chase"] is False
    assert row["has_movers_30d"] is False
    assert row["has_cards_page"] is True
    assert row["has_cards_validation"] is True
    assert row["has_pull_rates"] is False
    assert row["has_insights"] is False
    assert row["health_status"] == "degraded"
    # Movers must have been called for all three windows, not just one.
    movers_windows_called = {kwargs.get("window") for name, _, _, kwargs in calls if name == "movers"}
    assert movers_windows_called == {"1D", "7D", "30D"}


def test_audit_set_records_fetch_errors_without_raising(monkeypatch):
    class _FailingModule:
        def __getattr__(self, attr_name):
            def _fn(*args, **kwargs):
                raise RuntimeError("boom")

            return _fn

    failing = _FailingModule()
    services = {key: failing for key in ("shell", "overview", "top_chase", "movers", "cards_page", "cards_validation", "pull_rates", "insights")}

    row = audit.audit_set({"id": "set-1", "name": "Test Set"}, services=services)

    assert row["health_status"] == "error"
    assert "boom" in row["warnings"]
