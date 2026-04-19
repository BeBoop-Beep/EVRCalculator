from unittest.mock import patch

import pandas as pd

import pandas as pd
import pytest

from backend.db.services.calculation_run_persistence_service import (
    persist_parent_run_with_price_snapshots,
    persist_simulation_derived_metrics,
    persist_simulation_etb_summary,
    persist_simulation_inputs,
)


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_etb_summary")
def test_persist_simulation_etb_summary_raises_when_metrics_missing(mock_create_simulation_etb_summary):
    with pytest.raises(ValueError, match="Missing required field: etb_metrics"):
        persist_simulation_etb_summary(run_id="run-1", etb_metrics=None)

    mock_create_simulation_etb_summary.assert_not_called()


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_etb_summary")
def test_persist_simulation_etb_summary_raises_when_required_field_missing(mock_create_simulation_etb_summary):
    incomplete_metrics = {
        "etb_market_price": "49.99",
        "etb_promo_price": "3.5",
        "total_ev_per_pack": "4.5",
        "total_packs_per_etb": "9",
        "total_etb_ev": "44.0",
        "etb_net_value": "-5.99",
    }

    with pytest.raises(ValueError, match="Missing required field"):
        persist_simulation_etb_summary(run_id="run-1", etb_metrics=incomplete_metrics)

    mock_create_simulation_etb_summary.assert_not_called()


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_etb_summary")
def test_persist_simulation_etb_summary_coerces_and_persists(mock_create_simulation_etb_summary):
    mock_create_simulation_etb_summary.return_value = {"id": "etb-1"}

    result = persist_simulation_etb_summary(
        run_id="run-1",
        etb_metrics={
            "etb_market_price": "49.99",
            "etb_promo_price": "3.5",
            "total_ev_per_pack": "4.5",
            "total_packs_per_etb": "9",
            "total_etb_ev": "44.0",
            "etb_net_value": "-5.99",
            "etb_roi": "0.880176",
            "etb_roi_percentage": "88.0176",
        },
    )

    assert result == {"persisted": True, "etb_summary_id": "etb-1"}
    mock_create_simulation_etb_summary.assert_called_once_with(
        "run-1",
        {
            "packs_per_etb": 9,
            "etb_market_price": 49.99,
            "promo_price": 3.5,
            "ev_per_pack": 4.5,
            "total_etb_ev": 44.0,
            "net_value": -5.99,
            "roi": 0.880176,
            "roi_percent": 88.0176,
        },
    )


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_derived_metrics")
def test_persist_simulation_derived_metrics_maps_required_fields_from_runtime(mock_create_simulation_derived_metrics):
    mock_create_simulation_derived_metrics.return_value = [{"id": "derived-1"}]

    derived = {
        "ev_composition_metrics": {
            "total_pack_ev": "7.18",
            "hit_ev": "6.16",
            "non_hit_ev": "1.02",
            "hit_ev_share_of_pack_ev": "0.858",
            "hit_cards_count": "208",
        },
        "chase_dependency_metrics": {
            "n_cards": "600",
            "total_ev": "7.18",
            "top1_ev_share": "0.22",
            "top3_ev_share": "0.47",
            "top5_ev_share": "0.63",
        },
        "index_score": {
            "ind_ex_score_v1": "72.4",
            "prob_profit_component": "0.71",
            "stability_component": "0.65",
            "diversification_component": "0.37",
        },
    }

    rows = persist_simulation_derived_metrics(run_id="run-1", derived=derived)

    assert rows == [{"id": "derived-1"}]
    persisted_payload = mock_create_simulation_derived_metrics.call_args.args[1]
    assert all(not isinstance(value, dict) for value in persisted_payload.values())
    mock_create_simulation_derived_metrics.assert_called_once_with(
        "run-1",
        {
            "hit_ev": 6.16,
            "non_hit_ev": 1.02,
            "hit_ev_share": 0.858,
            "hit_cards_tracked": 208,
            "cards_tracked": 600,
            "total_card_ev": 7.18,
            "top1_ev_share": 0.22,
            "top3_ev_share": 0.47,
            "top5_ev_share": 0.63,
            "index_score": 72.4,
            "profit_component": 0.71,
            "stability_component": 0.65,
            "diversification_component": 0.37,
        },
    )


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_derived_metrics")
def test_persist_simulation_derived_metrics_prefers_primary_chase_aliases_when_both_present(
    mock_create_simulation_derived_metrics,
):
    mock_create_simulation_derived_metrics.return_value = [{"id": "derived-1"}]

    persist_simulation_derived_metrics(
        run_id="run-1",
        derived={
            "ev_composition_metrics": {
                "total_pack_ev": 7.18,
                "hit_ev": 6.16,
                "non_hit_ev": 1.02,
                "hit_ev_share_of_pack_ev": 0.858,
                "hit_cards_count": 208,
            },
            "chase_dependency_metrics": {
                "cards_tracked": 700,
                "n_cards": 600,
                "total_card_ev": 8.18,
                "total_ev": 7.18,
                "top1_ev_share": 0.22,
                "top3_ev_share": 0.47,
                "top5_ev_share": 0.63,
            },
            "index_score": {
                "ind_ex_score_v1": 72.4,
                "prob_profit_component": 0.71,
                "stability_component": 0.65,
                "diversification_component": 0.37,
            },
        },
    )

    persisted_payload = mock_create_simulation_derived_metrics.call_args.args[1]
    assert persisted_payload["cards_tracked"] == 700
    assert persisted_payload["total_card_ev"] == 8.18


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_derived_metrics")
def test_persist_simulation_derived_metrics_accepts_legacy_chase_metric_names(mock_create_simulation_derived_metrics):
    mock_create_simulation_derived_metrics.return_value = [{"id": "derived-1"}]

    derived = {
        "ev_composition_metrics": {
            "hit_ev": 6.16,
            "non_hit_ev": 1.02,
            "hit_ev_share_of_pack_ev": 0.858,
            "hit_cards_count": 208,
        },
        "chase_dependency_metrics": {
            "n_cards": 600,
            "total_ev": 7.18,
            "top1_ev_share": 0.22,
            "top3_ev_share": 0.47,
            "top5_ev_share": 0.63,
        },
        "index_score": {
            "ind_ex_score_v1": 72.4,
            "prob_profit_component": 0.71,
            "stability_component": 0.65,
            "diversification_component": 0.37,
        },
    }

    persist_simulation_derived_metrics(run_id="run-1", derived=derived)

    mock_create_simulation_derived_metrics.assert_called_once_with(
        "run-1",
        {
            "hit_ev": 6.16,
            "non_hit_ev": 1.02,
            "hit_ev_share": 0.858,
            "hit_cards_tracked": 208,
            "cards_tracked": 600,
            "total_card_ev": 7.18,
            "top1_ev_share": 0.22,
            "top3_ev_share": 0.47,
            "top5_ev_share": 0.63,
            "index_score": 72.4,
            "profit_component": 0.71,
            "stability_component": 0.65,
            "diversification_component": 0.37,
        },
    )


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_input_cards")
@patch("backend.db.services.calculation_run_persistence_service.create_simulation_top_hits")
def test_persist_simulation_inputs_normalizes_legacy_top_hit_rows(
    mock_create_simulation_top_hits,
    mock_create_simulation_input_cards,
):
    mock_create_simulation_top_hits.return_value = [{"id": "top-hit-1"}]
    mock_create_simulation_input_cards.return_value = [{"id": "input-card-1"}]

    top_hits_df = pd.DataFrame(
        [
            {
                "Card Name": "Charizard ex",
                "Card Number": "199/165",
                "Rarity": "special illustration rare",
                "Price ($)": 45.0,
                "Effective_Pull_Rate": 225.0,
                "EV": 0.2,
            }
        ]
    )
    input_df = pd.DataFrame(
        [
            {
                "card_id": "199/165",
                "card_variant_id": "199/165",
                "condition_id": 1,
                "card_name": "Charizard ex",
                "rarity_bucket": "hits",
                "price_source": "market",
                "price_used": 45.0,
                "captured_at": "2026-04-18T00:00:00Z",
                "effective_pull_rate": 225.0,
                "ev_contribution": 0.2,
            }
        ]
    )

    result = persist_simulation_inputs(
        run_id="run-1",
        top_10_hits=top_hits_df,
        calculation_input=input_df,
        config=object(),
    )

    assert result == {"top_hits_count": 1, "input_cards_count": 1}
    persisted_top_hits = mock_create_simulation_top_hits.call_args.args[1]
    assert set(persisted_top_hits[0].keys()) == {
        "card_id",
        "card_variant_id",
        "rank",
        "card_name",
        "rarity_bucket",
        "market_price_at_run",
        "effective_pull_rate",
        "ev_contribution",
    }
    mock_create_simulation_top_hits.assert_called_once_with(
        "run-1",
        [
            {
                "card_id": "199/165",
                "card_variant_id": "199/165",
                "rank": 1,
                "card_name": "Charizard ex",
                "rarity_bucket": "special illustration rare",
                "market_price_at_run": 45.0,
                "effective_pull_rate": 225.0,
                "ev_contribution": 0.2,
            }
        ],
    )


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_derived_metrics")
def test_persist_simulation_derived_metrics_coerces_empty_shares_to_zero(mock_create_simulation_derived_metrics):
    mock_create_simulation_derived_metrics.return_value = [{"id": "derived-1"}]

    rows = persist_simulation_derived_metrics(
        run_id="run-1",
        derived={
            "ev_composition_metrics": {
                "total_pack_ev": 0.0,
                "hit_ev": 0.0,
                "non_hit_ev": 0.0,
                "hit_ev_share_of_pack_ev": None,
                "hit_cards_count": 0,
            },
            "chase_dependency_metrics": {
                "n_cards": 0,
                "total_ev": 0.0,
                "top1_ev_share": None,
                "top3_ev_share": None,
                "top5_ev_share": None,
            },
            "index_score": {
                "ind_ex_score_v1": 0.0,
                "prob_profit_component": 0.0,
                "stability_component": 0.0,
                "diversification_component": 1.0,
            },
        },
    )

    assert rows == [{"id": "derived-1"}]
    mock_create_simulation_derived_metrics.assert_called_once_with(
        "run-1",
        {
            "hit_ev": 0.0,
            "non_hit_ev": 0.0,
            "hit_ev_share": 0.0,
            "hit_cards_tracked": 0,
            "cards_tracked": 0,
            "total_card_ev": 0.0,
            "top1_ev_share": 0.0,
            "top3_ev_share": 0.0,
            "top5_ev_share": 0.0,
            "index_score": 0.0,
            "profit_component": 0.0,
            "stability_component": 0.0,
            "diversification_component": 1.0,
        },
    )


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_input_cards")
@patch("backend.db.services.calculation_run_persistence_service.create_simulation_top_hits")
def test_persist_simulation_inputs_maps_dataframe_runtime_columns_to_child_table_contract(
    mock_create_simulation_top_hits,
    mock_create_simulation_input_cards,
):
    from backend.db.services.calculation_run_persistence_service import persist_simulation_inputs

    mock_create_simulation_top_hits.return_value = [{"id": "top-hit-1"}]
    mock_create_simulation_input_cards.return_value = [{"id": "input-1"}]

    result = persist_simulation_inputs(
        run_id="run-1",
        top_10_hits=[
            {
                "card_id": "card-1",
                "card_variant_id": "variant-1",
                "rank": 1,
                "card_name": "Card A",
                "rarity_bucket": "rare",
                "market_price_at_run": 5.0,
                "effective_pull_rate": 10.0,
                "ev_contribution": 0.5,
            }
        ],
        calculation_input=pd.DataFrame(
            [
                {
                    "card_id": "card-1",
                    "card_variant_id": "variant-1",
                    "condition_id": "condition-1",
                    "Card Name": "Card A",
                    "rarity_group": "rare",
                    "Price ($)": 5.0,
                    "price_source": "tcgplayer",
                    "captured_at": "2026-04-18T00:00:00+00:00",
                    "Effective_Pull_Rate": 10.0,
                    "EV": 0.5,
                }
            ]
        ),
        config=object(),
    )

    assert result == {"top_hits_count": 1, "input_cards_count": 1}
    persisted_top_hits = mock_create_simulation_top_hits.call_args.args[1]
    assert set(persisted_top_hits[0].keys()) == {
        "card_id",
        "card_variant_id",
        "rank",
        "card_name",
        "rarity_bucket",
        "market_price_at_run",
        "effective_pull_rate",
        "ev_contribution",
    }
    mock_create_simulation_top_hits.assert_called_once_with(
        "run-1",
        [
            {
                "card_id": "card-1",
                "card_variant_id": "variant-1",
                "rank": 1,
                "card_name": "Card A",
                "rarity_bucket": "rare",
                "market_price_at_run": 5.0,
                "effective_pull_rate": 10.0,
                "ev_contribution": 0.5,
            }
        ],
    )
    mock_create_simulation_input_cards.assert_called_once_with(
        "run-1",
        [
            {
                "card_id": "card-1",
                "card_variant_id": "variant-1",
                "condition_id": "condition-1",
                "card_name": "Card A",
                "rarity_bucket": "rare",
                "price_source": "tcgplayer",
                "price_used": 5.0,
                "captured_at": "2026-04-18T00:00:00+00:00",
                "effective_pull_rate": 10.0,
                "ev_contribution": 0.5,
            }
        ],
    )


@patch("backend.calculations.packCalcsRefractored.PackCalculationOrchestrator")
@patch("backend.db.services.calculation_run_persistence_service.create_simulation_input_cards")
@patch("backend.db.services.calculation_run_persistence_service.create_simulation_top_hits")
def test_persist_simulation_inputs_falls_back_to_orchestrator_when_dataframe_missing_ev_fields(
    mock_create_simulation_top_hits,
    mock_create_simulation_input_cards,
    mock_orchestrator_cls,
):
    mock_create_simulation_top_hits.return_value = [{"id": "top-hit-1"}]
    mock_create_simulation_input_cards.return_value = [{"id": "input-1"}]

    runtime_input_df = pd.DataFrame(
        [
            {
                "card_id": "card-1",
                "card_variant_id": "variant-1",
                "condition_id": "condition-1",
                "Card Name": "Card A",
                "Rarity": "rare",
                "Price ($)": 5.0,
                "Pull Rate (1/X)": 10.0,
                "Pack Price": 4.0,
                "price_source": "tcgplayer",
                "captured_at": "2026-04-18T00:00:00+00:00",
            }
        ]
    )
    normalized_df = pd.DataFrame(
        [
            {
                "card_id": "card-1",
                "card_variant_id": "variant-1",
                "condition_id": "condition-1",
                "Card Name": "Card A",
                "rarity_group": "rare",
                "Price ($)": 5.0,
                "price_source": "tcgplayer",
                "captured_at": "2026-04-18T00:00:00+00:00",
                "Effective_Pull_Rate": 10.0,
                "EV": 0.5,
            }
        ]
    )
    mock_orchestrator = mock_orchestrator_cls.return_value
    mock_orchestrator.load_and_prepare_data.return_value = (normalized_df, 4.0)

    config = object()
    result = persist_simulation_inputs(
        run_id="run-1",
        top_10_hits=[
            {
                "card_id": "card-1",
                "card_variant_id": "variant-1",
                "rank": 1,
                "card_name": "Card A",
                "rarity_bucket": "rare",
                "market_price_at_run": 5.0,
                "effective_pull_rate": 10.0,
                "ev_contribution": 0.5,
            }
        ],
        calculation_input=runtime_input_df,
        config=config,
    )

    assert result == {"top_hits_count": 1, "input_cards_count": 1}
    mock_orchestrator_cls.assert_called_once_with(config)
    mock_orchestrator.load_and_prepare_data.assert_called_once_with(runtime_input_df)
    mock_create_simulation_input_cards.assert_called_once_with(
        "run-1",
        [
            {
                "card_id": "card-1",
                "card_variant_id": "variant-1",
                "condition_id": "condition-1",
                "card_name": "Card A",
                "rarity_bucket": "rare",
                "price_source": "tcgplayer",
                "price_used": 5.0,
                "captured_at": "2026-04-18T00:00:00+00:00",
                "effective_pull_rate": 10.0,
                "ev_contribution": 0.5,
            }
        ],
    )


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_derived_metrics")
def test_persist_simulation_derived_metrics_raises_when_required_source_missing(mock_create_simulation_derived_metrics):
    derived = {
        "ev_composition_metrics": {
            "total_pack_ev": 7.18,
            "hit_ev": 6.16,
            "non_hit_ev": 1.02,
            "hit_ev_share_of_pack_ev": 0.858,
            "hit_cards_count": 208,
        },
        "chase_dependency_metrics": {
            "n_cards": 600,
            "total_ev": 7.18,
            "top1_ev_share": 0.22,
            "top3_ev_share": 0.47,
            # top5_ev_share missing on purpose
        },
        "index_score": {
            "ind_ex_score_v1": 72.4,
            "prob_profit_component": 0.71,
            "stability_component": 0.65,
            "diversification_component": 0.37,
        },
    }

    with pytest.raises(ValueError, match="derived.chase_dependency_metrics.top5_ev_share"):
        persist_simulation_derived_metrics(run_id="run-1", derived=derived)

    mock_create_simulation_derived_metrics.assert_not_called()


@patch("backend.db.services.calculation_run_persistence_service.create_calculation_price_snapshot")
@patch("backend.db.services.calculation_run_persistence_service.create_parent_calculation_run")
@patch("backend.db.services.calculation_run_persistence_service.get_or_create_calculation_config")
@patch("backend.db.services.calculation_run_persistence_service.build_calculation_config_payload")
@patch("backend.db.services.calculation_run_persistence_service.get_set_by_canonical_key")
def test_persist_parent_run_with_price_snapshots_maps_all_value_vs_cost_comparisons(
    mock_get_set_by_canonical_key,
    mock_build_calculation_config_payload,
    mock_get_or_create_calculation_config,
    mock_create_parent_calculation_run,
    mock_create_calculation_price_snapshot,
):
    class _Config:
        USE_MONTE_CARLO_V2 = True

    mock_get_set_by_canonical_key.return_value = {"id": "set-1"}
    mock_build_calculation_config_payload.return_value = ("cfg-hash", {"cfg": True})
    mock_get_or_create_calculation_config.return_value = {"id": "cfg-1"}
    mock_create_parent_calculation_run.return_value = {"id": "run-1"}

    result = persist_parent_run_with_price_snapshots(
        config=_Config(),
        canonical_key="dummy-set",
        set_name="Dummy Set",
        input_mode="db",
        price_inputs={"pack": 5.0},
        pack_value_vs_cost_comparison={
            "simulated_mean_pack_value_vs_pack_cost": {"roi": 1.2},
            "simulated_median_pack_value_vs_pack_cost": {"roi": 0.9},
            "calculated_expected_pack_value_vs_pack_cost": {"roi": 1.1},
        },
        etb_value_vs_cost_comparison={
            "simulated_mean_etb_value_vs_etb_cost": {"roi": 1.15},
            "simulated_median_etb_value_vs_etb_cost": {"roi": 1.05},
            "calculated_expected_etb_value_vs_etb_cost": {"roi": 1.08},
        },
        booster_box_value_vs_cost_comparison={
            "simulated_mean_booster_box_value_vs_booster_box_cost": {"roi": 1.3},
            "simulated_median_booster_box_value_vs_booster_box_cost": {"roi": 1.1},
            "calculated_expected_booster_box_value_vs_booster_box_cost": {"roi": 1.2},
        },
    )

    assert result["run_id"] == "run-1"
    assert result["config_hash"] == "cfg-hash"

    comparison_payload = mock_create_parent_calculation_run.call_args.args[6]
    assert comparison_payload == {
        "simulated_mean_pack_value_vs_pack_cost": 1.2,
        "simulated_median_pack_value_vs_pack_cost": 0.9,
        "calculated_expected_pack_value_vs_pack_cost": 1.1,
        "simulated_mean_etb_value_vs_etb_cost": 1.15,
        "simulated_median_etb_value_vs_etb_cost": 1.05,
        "calculated_expected_etb_value_vs_etb_cost": 1.08,
        "simulated_mean_booster_box_value_vs_booster_box_cost": 1.3,
        "simulated_median_booster_box_value_vs_booster_box_cost": 1.1,
        "calculated_expected_booster_box_value_vs_booster_box_cost": 1.2,
    }
    mock_create_calculation_price_snapshot.assert_called_once()


@patch("backend.db.services.calculation_run_persistence_service.create_calculation_price_snapshot")
@patch("backend.db.services.calculation_run_persistence_service.create_parent_calculation_run")
@patch("backend.db.services.calculation_run_persistence_service.get_or_create_calculation_config")
@patch("backend.db.services.calculation_run_persistence_service.build_calculation_config_payload")
@patch("backend.db.services.calculation_run_persistence_service.get_set_by_canonical_key")
def test_persist_parent_run_with_price_snapshots_allows_missing_etb_comparison_and_skips_etb_snapshots(
    mock_get_set_by_canonical_key,
    mock_build_calculation_config_payload,
    mock_get_or_create_calculation_config,
    mock_create_parent_calculation_run,
    mock_create_calculation_price_snapshot,
):
    class _Config:
        USE_MONTE_CARLO_V2 = False

    mock_get_set_by_canonical_key.return_value = {"id": "set-1"}
    mock_build_calculation_config_payload.return_value = ("cfg-hash", {"cfg": True})
    mock_get_or_create_calculation_config.return_value = {"id": "cfg-1"}
    mock_create_parent_calculation_run.return_value = {"id": "run-1"}

    result = persist_parent_run_with_price_snapshots(
        config=_Config(),
        canonical_key="dummy-set",
        set_name="Dummy Set",
        input_mode="db",
        price_inputs={"pack": 5.0, "etb": 50.0, "etb_promo": 3.25, "booster_box": 180.0},
        pack_value_vs_cost_comparison={
            "simulated_mean_pack_value_vs_pack_cost": {"roi": 1.2},
            "simulated_median_pack_value_vs_pack_cost": {"roi": 0.9},
            "calculated_expected_pack_value_vs_pack_cost": {"roi": 1.1},
        },
        etb_value_vs_cost_comparison=None,
        booster_box_value_vs_cost_comparison={
            "simulated_mean_booster_box_value_vs_booster_box_cost": {"roi": 1.3},
            "simulated_median_booster_box_value_vs_booster_box_cost": {"roi": 1.1},
            "calculated_expected_booster_box_value_vs_booster_box_cost": {"roi": 1.2},
        },
    )

    assert result["snapshot_count"] == 2
    comparison_payload = mock_create_parent_calculation_run.call_args.args[6]
    assert comparison_payload["simulated_mean_etb_value_vs_etb_cost"] is None
    assert comparison_payload["simulated_median_etb_value_vs_etb_cost"] is None
    assert comparison_payload["calculated_expected_etb_value_vs_etb_cost"] is None
    snapshot_keys = [call.args[1] for call in mock_create_calculation_price_snapshot.call_args_list]
    assert snapshot_keys == ["pack", "booster_box"]
