from unittest.mock import patch

import pandas as pd
import pytest

from backend.jobs.evr_runner import EVRRunOrchestrator


class _DummyConfig:
    SET_NAME = "Dummy Set"
    BOOSTER_BOX_PACK_COUNT = 36
    PRODUCT_VARIANT_RULES = {
        "etb": {
            "standard": {"packs_per_product": 9},
            "pokemon_center": {"packs_per_product": 11},
        },
        "booster_box": {
            "standard": {"packs_per_product": 36},
        },
    }


def _prepared_input_payload():
    return {
        "dataframe": pd.DataFrame(
            [
                {
                    "Card Name": "Card A",
                    "Card Number": "001/999",
                    "Rarity": "rare",
                    "Special Type": "",
                    "Price ($)": 5.0,
                    "Pull Rate (1/X)": 10.0,
                    "Reverse Variant Price ($)": 5.0,
                    "Pack Price": 5.0,
                }
            ]
        ),
        "etb_price": 50.0,
        "etb_promo_card_price": 3.25,
        "booster_box_price": 180.0,
        "etb_variants": {
            "standard": {
                "etb_price": 50.0,
                "etb_promo_card_price": 3.25,
            },
            "pokemon_center": {
                "etb_price": 80.0,
                "etb_promo_card_price": 12.5,
            },
        },
        "booster_box_variants": {
            "standard": {
                "booster_box_price": 180.0,
                "booster_box_promo_card_price": 0.0,
            }
        },
    }


def _prepared_input_payload_without_etb_data():
    payload = _prepared_input_payload()
    payload["etb_price"] = None
    payload["etb_promo_card_price"] = None
    payload["etb_variants"] = {}
    return payload


@patch("backend.jobs.evr_runner.EVRInputPreparationService")
@patch("backend.jobs.evr_runner.persist_simulation_inputs", return_value={"persisted": True})
@patch("backend.jobs.evr_runner.persist_simulation_etb_summary", return_value={"persisted": True})
@patch("backend.jobs.evr_runner.persist_simulation_outputs", return_value={"persisted": True})
@patch("backend.jobs.evr_runner.persist_parent_run_with_price_snapshots", return_value={"run_id": "run-1"})
@patch("backend.jobs.evr_runner.calculate_etb_metrics")
@patch("backend.jobs.evr_runner.print_derived_metrics_summary")
@patch("backend.jobs.evr_runner.compute_all_derived_metrics", return_value={"derived": True})
@patch(
    "backend.jobs.evr_runner.calculate_pack_simulations",
    return_value=(
        {
            "values": [6.0, 4.0, 8.0],
            "mean": 6.0,
            "percentiles": {"50th": 4.5},
        },
        {
            "total_ev": 6.0,
            "net_value": 1.0,
            "opening_pack_roi": 1.2,
            "opening_pack_roi_percent": 20.0,
        },
    ),
)
@patch(
    "backend.jobs.evr_runner.calculate_pack_stats",
    return_value=(
        {
            "total_manual_ev": 5.5,
            "hit_ev_contributions": {"Card A": 2.0},
            "hit_ev": 2.0,
        },
        {"manual": True},
        [{"name": "Card A"}],
        5.0,
    ),
)
@patch("backend.jobs.evr_runner._resolve_set_config", return_value=(_DummyConfig, "dummySet"))
def test_run_disables_etb_in_normal_flow_while_preserving_pack_and_booster_box_outputs(
    _mock_resolve_set,
    _mock_pack_stats,
    _mock_pack_sims,
    _mock_compute_derived,
    _mock_print_derived,
    _mock_calc_etb,
    _mock_persist_parent,
    _mock_persist_outputs,
    _mock_persist_etb,
    _mock_persist_inputs,
    mock_input_preparation_service,
):
    mock_input_preparation_service.return_value.prepare_for_set.return_value = _prepared_input_payload()
    orchestrator = EVRRunOrchestrator()

    result = orchestrator.run(
        target_set_identifier="dummySet",
        input_source="db",
        run_metadata={"trigger": "test"},
    )

    # Simulation mean remains canonical total EV while manual EV is surfaced separately.
    assert result["total_ev"] == pytest.approx(6.0)
    assert result["calculated_expected_value_per_pack"] == pytest.approx(5.5)

    pack_comparison = result["pack_value_vs_cost_comparison"]
    assert set(pack_comparison.keys()) == {
        "simulated_mean_pack_value_vs_pack_cost",
        "simulated_median_pack_value_vs_pack_cost",
        "calculated_expected_pack_value_vs_pack_cost",
    }

    assert pack_comparison["simulated_mean_pack_value_vs_pack_cost"]["profit_loss"] == pytest.approx(1.0)
    assert pack_comparison["simulated_mean_pack_value_vs_pack_cost"]["roi"] == pytest.approx(1.2)

    assert pack_comparison["simulated_median_pack_value_vs_pack_cost"]["profit_loss"] == pytest.approx(-0.5)
    assert pack_comparison["simulated_median_pack_value_vs_pack_cost"]["roi"] == pytest.approx(0.9)

    assert pack_comparison["calculated_expected_pack_value_vs_pack_cost"]["profit_loss"] == pytest.approx(0.5)
    assert pack_comparison["calculated_expected_pack_value_vs_pack_cost"]["roi"] == pytest.approx(1.1)

    assert result["etb_value_vs_cost_comparison"] == {}
    assert result["etb_value_vs_cost_comparison_by_variant"] == {}
    assert result["etb_metrics"] is None

    booster_box_comparison = result["booster_box_value_vs_cost_comparison"]
    assert set(booster_box_comparison.keys()) == {
        "simulated_mean_booster_box_value_vs_booster_box_cost",
        "simulated_median_booster_box_value_vs_booster_box_cost",
        "calculated_expected_booster_box_value_vs_booster_box_cost",
    }

    mean_booster_box = booster_box_comparison["simulated_mean_booster_box_value_vs_booster_box_cost"]
    assert mean_booster_box["packs_per_booster_box"] == 36
    assert mean_booster_box["expected_total_booster_box_value"] == pytest.approx(36 * 6.0)
    assert mean_booster_box["profit_loss"] == pytest.approx((36 * 6.0) - 180.0)
    assert mean_booster_box["roi"] == pytest.approx((36 * 6.0) / 180.0)

    booster_by_variant = result["booster_box_value_vs_cost_comparison_by_variant"]
    assert set(booster_by_variant.keys()) == {"standard"}
    assert (
        booster_by_variant["standard"]["simulated_mean_booster_box_value_vs_booster_box_cost"]
        ["packs_per_booster_box"]
        == 36
    )

    persist_parent_kwargs = _mock_persist_parent.call_args.kwargs
    assert set(persist_parent_kwargs["pack_value_vs_cost_comparison"].keys()) == {
        "simulated_mean_pack_value_vs_pack_cost",
        "simulated_median_pack_value_vs_pack_cost",
        "calculated_expected_pack_value_vs_pack_cost",
    }
    assert persist_parent_kwargs["etb_value_vs_cost_comparison"] is None
    assert set(persist_parent_kwargs["booster_box_value_vs_cost_comparison"].keys()) == {
        "simulated_mean_booster_box_value_vs_booster_box_cost",
        "simulated_median_booster_box_value_vs_booster_box_cost",
        "calculated_expected_booster_box_value_vs_booster_box_cost",
    }
    assert set(persist_parent_kwargs["price_inputs"].keys()) == {"pack", "booster_box"}
    assert persist_parent_kwargs["price_inputs"]["booster_box"] == pytest.approx(180.0)

    assert result["persisted"]["etb_summary"] is None
    _mock_calc_etb.assert_not_called()
    _mock_persist_etb.assert_not_called()
    _mock_print_derived.assert_called_once_with({"derived": True})


@patch("backend.jobs.evr_runner.EVRInputPreparationService")
@patch("backend.jobs.evr_runner.persist_simulation_inputs", return_value={"persisted": True})
@patch("backend.jobs.evr_runner.persist_simulation_etb_summary", return_value={"persisted": True})
@patch("backend.jobs.evr_runner.persist_simulation_outputs", return_value={"persisted": True})
@patch("backend.jobs.evr_runner.persist_parent_run_with_price_snapshots", return_value={"run_id": "run-1"})
@patch("backend.jobs.evr_runner.calculate_etb_metrics")
@patch("backend.jobs.evr_runner.print_derived_metrics_summary")
@patch("backend.jobs.evr_runner.compute_all_derived_metrics", return_value={"derived": True})
@patch(
    "backend.jobs.evr_runner.calculate_pack_simulations",
    return_value=(
        {
            "values": [6.0, 4.0, 8.0],
            "mean": 6.0,
            "percentiles": {"50th": 4.5},
        },
        {
            "total_ev": 6.0,
            "net_value": 1.0,
            "opening_pack_roi": 1.2,
            "opening_pack_roi_percent": 20.0,
        },
    ),
)
@patch(
    "backend.jobs.evr_runner.calculate_pack_stats",
    return_value=(
        {
            "total_manual_ev": 5.5,
            "hit_ev_contributions": {"Card A": 2.0},
            "hit_ev": 2.0,
        },
        {"manual": True},
        [{"name": "Card A"}],
        5.0,
    ),
)
@patch("backend.jobs.evr_runner._resolve_set_config", return_value=(_DummyConfig, "dummySet"))
def test_run_prints_pack_and_booster_box_comparison_blocks_without_etb_section(
    _mock_resolve_set,
    _mock_pack_stats,
    _mock_pack_sims,
    _mock_compute_derived,
    _mock_print_derived,
    _mock_calc_etb,
    _mock_persist_parent,
    _mock_persist_outputs,
    _mock_persist_etb,
    _mock_persist_inputs,
    mock_input_preparation_service,
    capsys,
):
    mock_input_preparation_service.return_value.prepare_for_set.return_value = _prepared_input_payload()
    orchestrator = EVRRunOrchestrator()

    orchestrator.run(
        target_set_identifier="dummySet",
        input_source="db",
        run_metadata={"trigger": "test"},
    )
    output = capsys.readouterr().out

    assert "Pack comparisons:" in output
    assert "simulated_mean_pack_value_vs_pack_cost" in output
    assert "simulated_median_pack_value_vs_pack_cost" in output
    assert "calculated_expected_pack_value_vs_pack_cost" in output

    assert "ETB comparisons:" not in output
    assert "simulated_mean_etb_value_vs_etb_cost" not in output
    assert "simulated_median_etb_value_vs_etb_cost" not in output
    assert "calculated_expected_etb_value_vs_etb_cost" not in output

    assert "Booster-box comparisons:" in output
    assert "simulated_mean_booster_box_value_vs_booster_box_cost" in output
    assert "simulated_median_booster_box_value_vs_booster_box_cost" in output
    assert "calculated_expected_booster_box_value_vs_booster_box_cost" in output

    _mock_calc_etb.assert_not_called()
    _mock_persist_etb.assert_not_called()


@patch("backend.jobs.evr_runner.EVRInputPreparationService")
@patch("backend.jobs.evr_runner.persist_simulation_inputs", return_value={"persisted": True})
@patch("backend.jobs.evr_runner.persist_simulation_etb_summary", return_value={"persisted": True})
@patch("backend.jobs.evr_runner.persist_simulation_outputs", return_value={"persisted": True})
@patch("backend.jobs.evr_runner.persist_parent_run_with_price_snapshots", return_value={"run_id": "run-1"})
@patch("backend.jobs.evr_runner.calculate_etb_metrics")
@patch("backend.jobs.evr_runner.print_derived_metrics_summary")
@patch("backend.jobs.evr_runner.compute_all_derived_metrics", return_value={"derived": True})
@patch(
    "backend.jobs.evr_runner.calculate_pack_simulations",
    return_value=(
        {
            "values": [6.0, 4.0, 8.0],
            "mean": 6.0,
            "percentiles": {"50th (median)": 4.5},
        },
        {
            "total_ev": 6.0,
            "net_value": 1.0,
            "opening_pack_roi": 1.2,
            "opening_pack_roi_percent": 20.0,
        },
    ),
)
@patch(
    "backend.jobs.evr_runner.calculate_pack_stats",
    return_value=(
        {
            "total_manual_ev": 5.5,
            "hit_ev_contributions": {"Card A": 2.0},
            "hit_ev": 2.0,
        },
        {"manual": True},
        [{"name": "Card A"}],
        5.0,
    ),
)
@patch("backend.jobs.evr_runner._resolve_set_config", return_value=(_DummyConfig, "dummySet"))
def test_run_uses_legacy_median_percentile_key_as_safe_fallback(
    _mock_resolve_set,
    _mock_pack_stats,
    _mock_pack_sims,
    _mock_compute_derived,
    _mock_print_derived,
    _mock_calc_etb,
    _mock_persist_parent,
    _mock_persist_outputs,
    _mock_persist_etb,
    _mock_persist_inputs,
    mock_input_preparation_service,
):
    mock_input_preparation_service.return_value.prepare_for_set.return_value = _prepared_input_payload()
    orchestrator = EVRRunOrchestrator()

    result = orchestrator.run(
        target_set_identifier="dummySet",
        input_source="db",
        run_metadata={"trigger": "test"},
    )

    median_pack = result["pack_value_vs_cost_comparison"]["simulated_median_pack_value_vs_pack_cost"]
    assert median_pack["expected_value"] == pytest.approx(4.5)
    _mock_calc_etb.assert_not_called()
    _mock_persist_etb.assert_not_called()


@patch("backend.jobs.evr_runner.EVRInputPreparationService")
@patch("backend.jobs.evr_runner.persist_simulation_inputs", return_value={"persisted": True})
@patch("backend.jobs.evr_runner.persist_simulation_etb_summary", return_value={"persisted": True})
@patch("backend.jobs.evr_runner.persist_simulation_outputs", return_value={"persisted": True})
@patch("backend.jobs.evr_runner.persist_parent_run_with_price_snapshots", return_value={"run_id": "run-1"})
@patch("backend.jobs.evr_runner.calculate_etb_metrics")
@patch("backend.jobs.evr_runner.print_derived_metrics_summary")
@patch("backend.jobs.evr_runner.compute_all_derived_metrics", return_value={"derived": True})
@patch(
    "backend.jobs.evr_runner.calculate_pack_simulations",
    return_value=(
        {
            "values": [6.0, 4.0, 8.0],
            "mean": 6.0,
            "percentiles": {"50th": 4.5},
        },
        {
            "total_ev": 6.0,
            "net_value": 1.0,
            "opening_pack_roi": 1.2,
            "opening_pack_roi_percent": 20.0,
        },
    ),
)
@patch(
    "backend.jobs.evr_runner.calculate_pack_stats",
    return_value=(
        {
            "total_manual_ev": 5.5,
            "hit_ev_contributions": {"Card A": 2.0},
            "hit_ev": 2.0,
        },
        {"manual": True},
        [{"name": "Card A"}],
        5.0,
    ),
)
@patch("backend.jobs.evr_runner._resolve_set_config", return_value=(_DummyConfig, "dummySet"))
def test_run_does_not_block_when_etb_inputs_are_absent_in_disabled_flow(
    _mock_resolve_set,
    _mock_pack_stats,
    _mock_pack_sims,
    _mock_compute_derived,
    _mock_print_derived,
    _mock_calc_etb,
    _mock_persist_parent,
    _mock_persist_outputs,
    _mock_persist_etb,
    _mock_persist_inputs,
    mock_input_preparation_service,
):
    mock_input_preparation_service.return_value.prepare_for_set.return_value = _prepared_input_payload_without_etb_data()
    orchestrator = EVRRunOrchestrator()

    result = orchestrator.run(
        target_set_identifier="dummySet",
        input_source="db",
        run_metadata={"trigger": "test"},
    )

    assert result["total_ev"] == pytest.approx(6.0)
    assert result["etb_metrics"] is None
    assert result["etb_value_vs_cost_comparison"] == {}
    _mock_calc_etb.assert_not_called()
    _mock_persist_etb.assert_not_called()


@patch("backend.jobs.evr_runner.EVRInputPreparationService")
@patch("backend.jobs.evr_runner.persist_simulation_inputs", return_value={"persisted": True})
@patch("backend.jobs.evr_runner.persist_simulation_etb_summary", return_value={"persisted": True})
@patch("backend.jobs.evr_runner.persist_simulation_outputs", side_effect=ValueError("derived row failed"))
@patch("backend.jobs.evr_runner.persist_parent_run_with_price_snapshots", return_value={"run_id": "run-1"})
@patch("backend.jobs.evr_runner.calculate_etb_metrics")
@patch("backend.jobs.evr_runner.print_derived_metrics_summary")
@patch("backend.jobs.evr_runner.compute_all_derived_metrics", return_value={"derived": True})
@patch(
    "backend.jobs.evr_runner.calculate_pack_simulations",
    return_value=(
        {
            "values": [6.0, 4.0, 8.0],
            "mean": 6.0,
            "percentiles": {"50th": 4.5},
        },
        {
            "total_ev": 6.0,
            "net_value": 1.0,
            "opening_pack_roi": 1.2,
            "opening_pack_roi_percent": 20.0,
        },
    ),
)
@patch(
    "backend.jobs.evr_runner.calculate_pack_stats",
    return_value=(
        {
            "total_manual_ev": 5.5,
            "hit_ev_contributions": {"Card A": 2.0},
            "hit_ev": 2.0,
        },
        {"manual": True},
        [{"name": "Card A"}],
        5.0,
    ),
)
@patch("backend.jobs.evr_runner._resolve_set_config", return_value=(_DummyConfig, "dummySet"))
def test_run_persists_inputs_before_outputs_so_top_hits_are_not_blocked_by_later_output_failure(
    _mock_resolve_set,
    _mock_pack_stats,
    _mock_pack_sims,
    _mock_compute_derived,
    _mock_print_derived,
    _mock_calc_etb,
    _mock_persist_parent,
    _mock_persist_outputs,
    _mock_persist_etb,
    _mock_persist_inputs,
    mock_input_preparation_service,
):
    mock_input_preparation_service.return_value.prepare_for_set.return_value = _prepared_input_payload()
    orchestrator = EVRRunOrchestrator()

    with pytest.raises(ValueError, match="derived row failed"):
        orchestrator.run(
            target_set_identifier="dummySet",
            input_source="db",
            run_metadata={"trigger": "test"},
        )

    assert _mock_persist_inputs.called
    assert _mock_persist_outputs.called
    assert _mock_persist_inputs.call_args.kwargs["run_id"] == "run-1"


def test_run_rejects_spreadsheet_input_source_before_runtime_preparation():
    orchestrator = EVRRunOrchestrator()

    with pytest.raises(ValueError, match="input_source must be 'db'"):
        orchestrator.run(
            target_set_identifier="dummySet",
            input_source="spreadsheet",
            run_metadata={"trigger": "test"},
        )
