import inspect
import json

import pytest

import backend.db.services.evr_input_preparation_service as evr_input_preparation_service
from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig
from backend.scripts import audit_swsh_production_runtime_smoke as production_smoke
from backend.scripts.audit_swsh_production_runtime_smoke import (
    TARGETS,
    _capture_other_swsh_runtime_enabled_state,
    _capture_sv_mega_routing_state,
    _compute_sv_mega_routing_status,
    _load_simulation_input,
    _warning_flags,
    run_production_runtime_smoke,
)
from backend.simulations.evrSimulator import _should_use_monte_carlo_v2, get_simulation_engine


def _make_mock_set_row(*, set_id: str, set_name: str) -> dict:
    return {
        "set_id": set_id,
        "set_name": set_name,
        "canonical_key": set_id,
        "simulation_input": {
            "source": "db_evr_input_preparation_service",
            "db_attempted": True,
            "fallback_used": False,
            "strict_db_input": True,
            "row_count": 10,
            "column_names": ["Card Name", "Card Number", "Rarity", "printing_type", "Price ($)"],
            "required_columns_present": True,
            "missing_required_columns": [],
            "price_column_detected": "Price ($)",
            "non_positive_price_rows": 0,
            "missing_price_rows": 0,
            "usable_price_rows": 10,
        },
        "pack_count": 100,
        "estimated_pack_price": 4.99,
        "estimated_pack_price_source": "EVRInputPreparationService.prepare_for_set.pack_price",
        "estimated_pack_price_resolution_status": "resolved",
        "roi_formula": "(average_pack_value - estimated_pack_price) / estimated_pack_price",
        "simulation_engine": "slot_schema",
        "slot_schema_runtime_enabled": True,
        "probability_table_status": {
            "production_has_rare_slot_probability": True,
            "draft_table_present": True,
            "production_equals_draft": True,
            "sum_probability": 1.0,
            "sum_is_one": True,
            "mapping_keys_match": True,
            "missing_mapping_keys": [],
            "unexpected_table_keys": [],
            "residual_rare_probability": 0.12,
            "residual_rare_non_negative": True,
            "runtime_enabled": True,
            "simulation_engine": "slot_schema",
            "routes_slot_schema": True,
            "monte_carlo_v2_disabled": True,
            "production_probability_table": {"rare": 0.12, "holo rare": 0.88},
            "draft_probability_table": {"rare": 0.12, "holo rare": 0.88},
        },
        "rare_slot_probability_table": {"rare": 0.12, "holo rare": 0.88},
        "production_probability_table_sum": 1.0,
        "residual_rare_probability": 0.12,
        "metrics": {
            "average_pack_value": 3.5,
            "median_pack_value": 3.0,
            "roi_at_estimated_pack_price": -0.3,
            "chance_to_beat_pack_cost": 0.2,
            "p05": 0.5,
            "p95": 9.0,
            "p99": 20.0,
            "best_simulated_pull": {
                "max_pack_value": 31.0,
                "best_pool_card_reference": {
                    "bucket": "holo rare",
                    "card_name": "Mock Hit",
                    "card_number": "001",
                    "printing_type": "holo",
                    "value": 31.0,
                },
            },
        },
        "top_ev_contributing_cards": [
            {
                "card_name": "Mock Hit",
                "display_label": "Mock Hit",
                "ev_contribution": 0.8,
                "share_of_hit_ev": 0.2,
                "share_of_total_pack_ev": 0.05,
            }
        ],
        "cards_carrying_set": {
            "top_1_share_of_hit_ev": 0.2,
            "top_5_share_of_hit_ev": 0.5,
            "hit_ev_total": 4.0,
            "total_pack_ev": 3.5,
        },
        "rare_slot_bucket_frequencies": [{"bucket": "holo rare", "observed_count": 88, "observed_probability": 0.88}],
        "rare_slot_frequency_deltas": {
            "rows": [
                {
                    "bucket": "holo rare",
                    "expected_bucket_probability": 0.88,
                    "observed_bucket_probability": 0.88,
                    "observed_count": 88,
                    "delta": 0.0,
                    "abs_delta": 0.0,
                }
            ],
            "largest_abs_delta": 0.0,
        },
        "largest_bucket_frequency_delta": 0.0,
        "roi_consistency_check": {
            "expected_roi_from_mean_and_pack_price": (3.5 - 4.99) / 4.99,
            "reported_roi": (3.5 - 4.99) / 4.99,
            "absolute_delta": 0.0,
            "passed": True,
        },
        "reverse_slot_sanity_check": {
            "expected_regular_reverse_probability": 1.0,
            "expected_regular_reverse_count": 100,
            "observed_regular_reverse_count": 100,
            "count_delta": 0,
            "reverse_pool_count": 10,
            "reverse_pool_has_non_reverse_entries": False,
            "rare_slot_reverse_holo_leakage_by_bucket": {},
            "has_reverse_holo_leakage": False,
        },
        "warning_flags": [
            {
                "code": "production_table_missing",
                "severity": "critical",
                "triggered": False,
                "detail": "ok",
                "value": None,
                "threshold": None,
            }
        ],
        "elapsed_seconds": 0.1,
    }


def test_script_uses_real_production_configs_not_draft_subclasses():
    by_id = {target.set_id: target for target in TARGETS}

    assert by_id["swsh6"].production_config is SetChillingReignConfig
    assert by_id["swsh7"].production_config is SetEvolvingSkiesConfig

    source = inspect.getsource(production_smoke)
    assert "DraftEmpiricalChillingReignRuntimeConfig" not in source
    assert "DraftEmpiricalEvolvingSkiesRuntimeConfig" not in source


def test_swsh6_swsh7_route_to_slot_schema_and_not_v2():
    for config in [SetChillingReignConfig, SetEvolvingSkiesConfig]:
        assert get_simulation_engine(config) == "slot_schema"
        assert _should_use_monte_carlo_v2(config) is False
        assert getattr(config, "SLOT_SCHEMA_RUNTIME_ENABLED", False) is True


def test_production_probability_tables_equal_draft_tables():
    assert SetChillingReignConfig.RARE_SLOT_PROBABILITY == SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT
    assert SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY == SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT


def test_strict_mode_rejects_fallback_when_db_input_unavailable(monkeypatch):
    def _raise_db_unavailable(_self, _config, _canonical_key, _set_name):
        raise RuntimeError("db unavailable for strict test")

    monkeypatch.setattr(
        evr_input_preparation_service.EVRInputPreparationService,
        "prepare_for_set",
        _raise_db_unavailable,
    )

    with pytest.raises(RuntimeError) as exc_info:
        _load_simulation_input(TARGETS[0], prefer_db_input=True, allow_fallback=False)

    error = str(exc_info.value)
    assert "fallback disabled" in error.lower()
    assert TARGETS[0].set_id in error
    assert TARGETS[0].set_name in error


def test_output_contains_both_sets(tmp_path, monkeypatch):
    json_path = tmp_path / "production_smoke.json"
    md_path = tmp_path / "production_smoke.md"

    def _mock_single_set(target, *, pack_count, seed, prefer_db_input, strict_db_input, sv_mega_routing_status):
        return _make_mock_set_row(set_id=target.set_id, set_name=target.set_name)

    monkeypatch.setattr(
        "backend.scripts.audit_swsh_production_runtime_smoke._run_single_set_production_smoke",
        _mock_single_set,
    )

    payload = run_production_runtime_smoke(
        json_output_path=json_path,
        markdown_output_path=md_path,
        pack_count=200,
        prefer_db_input=True,
        strict_db_input=True,
    )

    assert json_path.exists()
    assert md_path.exists()
    assert payload["runtime_approval_input_status"] == "strict_db_input_passed"

    set_ids = {row["set_id"] for row in payload["sets"]}
    assert set_ids == {"swsh6", "swsh7"}

    for row in payload["sets"]:
        assert "estimated_pack_price" in row
        assert "estimated_pack_price_source" in row
        assert "estimated_pack_price_resolution_status" in row
        assert "roi_formula" in row
        assert "roi_consistency_check" in row
        assert row["roi_consistency_check"]["passed"] is True

    markdown = md_path.read_text(encoding="utf-8")
    assert "Estimated pack price used" in markdown
    assert "ROI formula" in markdown
    assert "ROI consistency check" in markdown


def test_warning_flags_are_structured():
    flags = _warning_flags(
        probability_status={
            "production_has_rare_slot_probability": True,
            "production_equals_draft": True,
            "sum_is_one": True,
            "sum_probability": 1.0,
            "mapping_keys_match": True,
            "missing_mapping_keys": [],
            "unexpected_table_keys": [],
            "residual_rare_non_negative": True,
            "residual_rare_probability": 0.01,
            "production_probability_table": {"rare": 1.0},
            "draft_table_attr": "ANY",
        },
        simulation_input={
            "source": "db_evr_input_preparation_service",
            "row_count": 10,
            "fallback_used": False,
        },
        largest_rare_slot_delta=0.001,
        reverse_sanity={
            "has_reverse_holo_leakage": False,
            "rare_slot_reverse_holo_leakage_by_bucket": {},
            "reverse_pool_has_non_reverse_entries": False,
        },
        card_pool={"rare": [{"value": 1.0}]},
        sv_mega_routing_status={"changed": False, "all_expected_v2": True, "changed_entries": {}, "v2_violations": []},
        roi_consistency_check={
            "expected_roi_from_mean_and_pack_price": -0.5,
            "reported_roi": -0.5,
            "absolute_delta": 0.0,
            "passed": True,
        },
    )

    assert isinstance(flags, list)
    assert flags
    for flag in flags:
        assert "code" in flag
        assert "severity" in flag
        assert "triggered" in flag
        assert "detail" in flag


def test_roi_consistency_mismatch_warning_triggers_when_reported_roi_is_wrong():
    flags = _warning_flags(
        probability_status={
            "production_has_rare_slot_probability": True,
            "production_equals_draft": True,
            "sum_is_one": True,
            "sum_probability": 1.0,
            "mapping_keys_match": True,
            "missing_mapping_keys": [],
            "unexpected_table_keys": [],
            "residual_rare_non_negative": True,
            "residual_rare_probability": 0.01,
            "production_probability_table": {"rare": 1.0},
            "draft_table_attr": "ANY",
        },
        simulation_input={
            "source": "db_evr_input_preparation_service",
            "row_count": 10,
            "fallback_used": False,
        },
        largest_rare_slot_delta=0.001,
        reverse_sanity={
            "has_reverse_holo_leakage": False,
            "rare_slot_reverse_holo_leakage_by_bucket": {},
            "reverse_pool_has_non_reverse_entries": False,
        },
        card_pool={"rare": [{"value": 1.0}]},
        sv_mega_routing_status={"changed": False, "all_expected_v2": True, "changed_entries": {}, "v2_violations": []},
        roi_consistency_check={
            "expected_roi_from_mean_and_pack_price": -0.25,
            "reported_roi": -0.20,
            "absolute_delta": 0.05,
            "passed": False,
        },
    )

    mismatch_flag = next(flag for flag in flags if flag["code"] == "roi_consistency_mismatch")
    assert mismatch_flag["severity"] == "critical"
    assert mismatch_flag["triggered"] is True


def test_script_is_read_only_and_has_no_db_mutation_calls():
    source = inspect.getsource(production_smoke).lower()

    assert ".insert(" not in source
    assert ".update(" not in source
    assert ".delete(" not in source
    assert "upsert(" not in source


def test_sv_mega_routing_remains_unchanged_guardrail():
    before = _capture_sv_mega_routing_state()
    after = _capture_sv_mega_routing_state()

    status = _compute_sv_mega_routing_status(before, after)
    assert status["changed"] is False
    assert status["all_expected_v2"] is True
    assert status["v2_violations"] == []


def test_other_swsh_sets_remain_disabled_when_script_runs(tmp_path, monkeypatch):
    json_path = tmp_path / "production_smoke_other_swsh.json"
    md_path = tmp_path / "production_smoke_other_swsh.md"

    def _mock_single_set(target, *, pack_count, seed, prefer_db_input, strict_db_input, sv_mega_routing_status):
        return _make_mock_set_row(set_id=target.set_id, set_name=target.set_name)

    monkeypatch.setattr(
        "backend.scripts.audit_swsh_production_runtime_smoke._run_single_set_production_smoke",
        _mock_single_set,
    )

    before = _capture_other_swsh_runtime_enabled_state()

    payload = run_production_runtime_smoke(
        json_output_path=json_path,
        markdown_output_path=md_path,
        pack_count=200,
        prefer_db_input=True,
        strict_db_input=True,
    )

    after = _capture_other_swsh_runtime_enabled_state()

    assert before == after
    assert payload["other_swsh_runtime_guardrail"]["unchanged"] is True
    assert payload["other_swsh_runtime_guardrail"]["unexpected_enabled_ids"] == []


def test_strict_failure_writes_status_artifact(tmp_path, monkeypatch):
    json_path = tmp_path / "strict_failure.json"
    md_path = tmp_path / "strict_failure.md"

    def _raise_on_set(*_args, **_kwargs):
        raise RuntimeError("forced strict blocker")

    monkeypatch.setattr(
        "backend.scripts.audit_swsh_production_runtime_smoke._run_single_set_production_smoke",
        _raise_on_set,
    )

    with pytest.raises(RuntimeError, match="forced strict blocker"):
        run_production_runtime_smoke(
            json_output_path=json_path,
            markdown_output_path=md_path,
            pack_count=200,
            prefer_db_input=True,
            strict_db_input=True,
        )

    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["runtime_approval_input_status"] == "strict_db_input_failed"
