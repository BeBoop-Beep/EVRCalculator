import json
from pathlib import Path

import pytest

from backend.scripts import accept_market_explorer_variant_engine as acceptance


def test_pilot_uuid_constants_are_exact():
    assert acceptance.PILOTS["celebrations"]["setId"] == "be7c981b-c55e-4f60-a1b8-be922531452d"
    assert acceptance.PILOTS["fossil"]["setId"] == "c86889c9-ea25-4caa-b63c-7aa0b9796da8"


def test_local_preflight_detects_safe_1b_and_temp_only_1c_artifacts():
    checks = {row["name"]: row for row in acceptance.audit_local_artifacts()}
    assert all(row["status"] == "PASS" for row in checks.values())
    assert checks["no_global_migration_backfill"]["status"] == "PASS"
    assert checks["benchmark_temp_only"]["status"] == "PASS"


def test_aggregate_status_fails_closed():
    assert acceptance.aggregate_status([{"status": "PASS"}]) == "PASS"
    assert acceptance.aggregate_status([{"status": "PASS"}, {"status": "BLOCKED"}]) == "BLOCKED"
    assert acceptance.aggregate_status([{"status": "BLOCKED"}, {"status": "FAIL"}]) == "FAIL"


def test_integrity_detects_overlap_duplicate_zero_length_and_bad_authority():
    rows = [
        {"card_variant_id": "first", "observation_id": "o1", "valid_from": "2026-01-01",
         "valid_to": "2026-01-03", "source_date": "2026-01-01", "market_price": 10,
         "condition_ok": True, "currency_ok": True},
        {"card_variant_id": "first", "observation_id": "o2", "valid_from": "2026-01-02",
         "valid_to": None, "source_date": "2026-01-09", "market_price": -1,
         "condition_ok": False, "currency_ok": False},
        {"card_variant_id": "unlimited", "observation_id": "o3", "valid_from": "2026-01-02",
         "valid_to": "2026-01-02", "source_date": "2026-01-02", "market_price": 5,
         "condition_ok": True, "currency_ok": True},
    ]
    result = acceptance.validate_intervals(rows)
    assert result["overlap"] == 1
    assert result["nextBoundaryMismatch"] == 1
    assert result["zeroLength"] == 1
    assert result["nonPositivePrice"] == 1
    assert result["sourceDateMismatch"] == 1
    assert result["conditionMismatch"] == result["currencyMismatch"] == 1


def test_separate_variant_chains_never_supersede_each_other():
    rows = [
        {"card_variant_id": "first", "observation_id": "a", "valid_from": "2026-01-01",
         "valid_to": "2026-02-01", "source_date": "2026-01-01", "market_price": 10},
        {"card_variant_id": "first", "observation_id": "b", "valid_from": "2026-02-01",
         "valid_to": None, "source_date": "2026-02-01", "market_price": 20},
        {"card_variant_id": "unlimited", "observation_id": "c", "valid_from": "2026-01-15",
         "valid_to": None, "source_date": "2026-01-15", "market_price": 5},
    ]
    assert not any(acceptance.validate_intervals(rows).values())


def test_parity_uses_explicit_tolerance_and_chain_link_math():
    old = [{"market_date": "2026-01-01", "basket_value": 100, "common_current_value": 0,
            "common_previous_value": 0},
           {"market_date": "2026-01-02", "basket_value": 110, "common_current_value": 110,
            "common_previous_value": 100}]
    close = [{**row, "basket_value": row["basket_value"] + 1e-10} for row in old]
    assert acceptance.compare_parity(old, close, tolerance=1e-8)["status"] == "PASS"
    close[-1]["basket_value"] = 111
    assert acceptance.compare_parity(old, close, tolerance=1e-8)["status"] == "FAIL"


def test_legacy_parity_uses_previous_usable_date_across_consecutive_degraded_dates():
    constituents = [
        {"market_date": day, "canonical_card_id": card_id, "market_price": price}
        for day, prices in (
            ("2026-01-01", {"a": 40, "b": 60}),       # READY
            ("2026-01-02", {"a": 50, "b": 60}),       # DEGRADED
            ("2026-01-03", {"a": 90, "b": 60}),       # DEGRADED
            ("2026-01-04", {"a": 55, "b": 65}),       # READY
            ("2026-01-05", {"a": 60, "b": 66}),       # READY
        )
        for card_id, price in prices.items()
    ]

    rows = acceptance.build_canonical_legacy_cohort(
        constituents, ["2026-01-01", "2026-01-04", "2026-01-05"]
    )

    assert [row["market_date"] for row in rows] == [
        "2026-01-01", "2026-01-04", "2026-01-05"
    ]
    assert rows[1]["previous_usable_market_date"] == "2026-01-01"
    assert rows[1]["common_current_value"] == 120
    assert rows[1]["common_previous_value"] == 100
    assert rows[2]["previous_usable_market_date"] == "2026-01-04"
    assert rows[2]["common_current_value"] == 126
    assert rows[2]["common_previous_value"] == 120
    assert acceptance.compare_parity(rows, rows, tolerance=1e-8) == {
        "rowsCompared": 3,
        "numericTolerance": 1e-8,
        "maxAbsoluteDifference": 0.0,
        "maxRelativeDifference": 0.0,
        "perFieldMaxAbsoluteDifference": {
            "constituent_count": 0.0, "eligible_universe_count": 0.0,
            "basket_value": 0.0, "common_count": 0.0,
            "common_current_value": 0.0, "common_previous_value": 0.0,
            "daily_return": 0.0, "normalized_index": 0.0,
        },
        "status": "PASS",
    }


def test_multi_variant_source_reconstruction_is_independent_deterministic_and_carry_forward():
    rows = [
        {"id": "a1", "card_variant_id": "first", "condition_id": "nm", "currency": "USD",
         "market_price": "10", "captured_at": "2026-01-01", "created_at": "2026-01-01T01:00:00Z"},
        {"id": "a2", "card_variant_id": "first", "condition_id": "nm", "currency": "USD",
         "market_price": "11", "captured_at": "2026-01-01", "created_at": "2026-01-01T02:00:00Z"},
        {"id": "b1", "card_variant_id": "unlimited", "condition_id": "nm", "currency": '"USD"',
         "market_price": "4", "captured_at": "2026-01-01", "created_at": None},
        {"id": "c1", "card_variant_id": "unspecified", "condition_id": "nm", "currency": "USD",
         "market_price": "6", "captured_at": "2026-01-03", "created_at": "2026-01-03T01:00:00Z"},
    ]
    winners = acceptance.select_variant_source_winners(rows, "nm")
    assert {row["id"] for row in winners} == {"a2", "b1", "c1"}

    # 2026-01-02 is DEGRADED and deliberately absent from the canonical cadence.
    states = acceptance.reconstruct_variant_source_states(
        winners, ["2026-01-01", "2026-01-03", "2026-01-04"]
    )
    by_key = {(row["card_variant_id"], row["market_date"]): row for row in states}
    assert not any(row["market_date"] == "2026-01-02" for row in states)
    assert by_key[("first", "2026-01-04")]["market_price"] == 11
    assert by_key[("unlimited", "2026-01-04")]["market_price"] == 4
    assert by_key[("unspecified", "2026-01-04")]["market_price"] == 6
    assert acceptance.build_variant_market_series(states)[-1]["common_count"] == 3


def test_not_applicable_legacy_parity_passes_only_with_source_reconciliation():
    integrity = {"overlap": 0}
    cohort = {"currentBasketValid": True}
    not_applicable = {"applicable": False, "status": "NOT_APPLICABLE"}
    source = {"status": "PASS"}
    series = {"status": "VARIANT_SOURCE_PARITY_PASS"}
    assert acceptance.pilot_correctness_passes(integrity, cohort, not_applicable, source, series)
    assert not acceptance.pilot_correctness_passes(
        integrity, cohort, {"applicable": True, "status": "FAIL"}, source, series)
    assert not acceptance.pilot_correctness_passes(
        integrity, cohort, not_applicable, {"status": "FAIL"}, series)


def test_high_impact_gap_classification_is_price_sorted_and_named():
    result = acceptance.classify_high_impact([
        {"cardName": "Pikachu", "currentPrice": 50},
        {"cardName": "Charizard", "currentPrice": 500, "firstEdition": True},
        {"cardName": "Dragonite", "currentPrice": 120},
    ])
    assert result["marketValueRepresented"] == 670
    assert result["namedCounts"] == {"dragonite": 1, "charizard": 1, "pikachu": 1}
    assert result["top25"][0]["cardName"] == "Charizard"


def test_benchmark_parser_accepts_text_and_json_explain_formats():
    parsed = acceptance.parse_benchmark_output(
        'Planning Time: 1.2 ms\nExecution Time: 10.5 ms\n"Planning Time": 0.8,\n"Execution Time": 5.5'
    )
    assert parsed["planningMs"] == [1.2, 0.8]
    assert parsed["executionMs"] == [10.5, 5.5]
    assert parsed["medianExecutionMs"] == 8.0


def test_architecture_decision_requires_complete_evidence():
    assert acceptance.architecture_decision({})["decision"] == "BLOCKED_INSUFFICIENT_EVIDENCE"
    decision = acceptance.architecture_decision({"intervalExecutionMs": [800, 900],
        "factExecutionMs": [100, 120], "factBuildMs": 5000, "storageRatio": 2})
    assert decision["decision"] == "DECISION_B_DAILY_FACT"
    decision = acceptance.architecture_decision({"intervalExecutionMs": [100, 120],
        "factExecutionMs": [90, 100], "factBuildMs": 5000, "storageRatio": 2})
    assert decision["decision"] == "DECISION_A_INTERVALS"


def test_cli_never_allows_commit_for_read_only_modes():
    with pytest.raises(SystemExit, match="--commit is valid only"):
        acceptance.main(["--preflight", "--commit"])


def test_database_url_is_never_persisted_in_command_or_errors():
    secret = "postgresql://admin:secret@example/db"
    command = acceptance.redacted_command(["tool", "--database-url", secret, "--preflight"])
    assert secret not in command
    assert "<REDACTED_DATABASE_URL>" in command
    assert secret not in acceptance.safe_error(RuntimeError(f"failed {secret}"), secret)


def test_artifact_schema_contains_json_and_human_report(tmp_path):
    report = {"schemaVersion": "market-explorer-acceptance-v1", "status": "BLOCKED",
              "gitSha": "abc", "mode": "preflight", "environmentLabel": "test",
              "checks": [acceptance.check("permissions", "BLOCKED", "no direct SQL")]}
    acceptance.write_artifacts(report, tmp_path / "run")
    saved = json.loads((tmp_path / "run/acceptance.json").read_text())
    assert saved["schemaVersion"] == "market-explorer-acceptance-v1"
    assert "**BLOCKED** `permissions`" in (tmp_path / "run/acceptance.md").read_text()


def test_runner_source_contains_no_catalog_backfill_path():
    source = Path(acceptance.__file__).read_text(encoding="utf-8")
    assert "--catalog-backfill" not in source
    assert "run_backfill(client, commit=commit" in source


def test_pilot_dry_run_passes_commit_false(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(acceptance, "run_preflight", lambda _client, catalog=None: {
        "status": "PASS", "checks": [], "marketDates": []})
    monkeypatch.setattr(acceptance, "run_pilot", lambda _client, key, **kwargs: (
        calls.append((key, kwargs["commit"])) or {"status": "PASS"}))
    monkeypatch.setattr(acceptance, "write_artifacts", lambda *_args: None)
    monkeypatch.setattr(acceptance.subprocess, "check_output", lambda *_args, **_kwargs: "abc\n")
    monkeypatch.setattr("backend.db.clients.supabase_client.create_service_role_client", lambda: object())
    assert acceptance.main(["--pilot", "celebrations", "--artifact-dir", str(tmp_path)]) == 0
    assert calls == [("celebrations", False)]


def test_failed_first_pilot_stops_full_acceptance(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(acceptance, "run_preflight", lambda _client, catalog=None: {
        "status": "PASS", "checks": [], "marketDates": []})
    monkeypatch.setattr(acceptance, "run_pilot", lambda _client, key, **_kwargs: (
        calls.append(key) or {"status": "FAIL"}))
    monkeypatch.setattr(acceptance, "write_artifacts", lambda *_args: None)
    monkeypatch.setattr(acceptance.subprocess, "check_output", lambda *_args, **_kwargs: "abc\n")
    monkeypatch.setattr("backend.db.clients.supabase_client.create_service_role_client", lambda: object())
    assert acceptance.main(["--full-acceptance", "--artifact-dir", str(tmp_path)]) == 2
    assert calls == ["celebrations"]
