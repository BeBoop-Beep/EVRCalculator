from unittest.mock import patch

import pandas as pd

import pandas as pd
import pytest

from backend.db.services.calculation_run_persistence_service import (
    _derive_slot_schema_combo_state_counts,
    persist_parent_run_with_price_snapshots,
    persist_simulation_derived_metrics,
    persist_simulation_etb_summary,
    persist_simulation_inputs,
    persist_simulation_outputs,
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
        "pack_score": {
            "pack_score": "72.4",
            "profit_score": "71.0",
            "safety_score": "37.0",
            "stability_score": "65.0",
            "score_version": "pack_score_v1_singleton_placeholder",
            "normalization_mode": "singleton_placeholder",
            "pack_score_is_placeholder": True,
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
            "hhi_ev_concentration": None,
            "effective_chase_count": None,
            "pack_score": None,
            "profit_score": None,
            "safety_score": None,
            "stability_score": None,
            "p95_value_to_cost_ratio": None,
            "p99_value_to_cost_ratio": None,
            "mean_value_to_cost_ratio": None,
            "expected_loss_when_losing_fraction": None,
            "p05_shortfall_to_cost": None,
            "score_version": "pack_score_v1_singleton_placeholder",
            "normalization_mode": "singleton_placeholder",
            "pack_score_is_placeholder": True,
            "chase_potential_score": None,
            "experience_score": None,
            "chase_potential_tier": None,
            "experience_tier": None,
            "derived_metric_version": None,
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
            "pack_score": {
                "pack_score": 72.4,
                "profit_score": 71.0,
                "safety_score": 37.0,
                "stability_score": 65.0,
                "score_version": "pack_score_v1_singleton_placeholder",
                "normalization_mode": "singleton_placeholder",
                "pack_score_is_placeholder": True,
            },
        },
    )

    persisted_payload = mock_create_simulation_derived_metrics.call_args.args[1]
    assert persisted_payload["pack_score"] is None
    assert persisted_payload["profit_score"] is None
    assert persisted_payload["safety_score"] is None
    assert persisted_payload["stability_score"] is None
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
        "pack_score": {
            "pack_score": 72.4,
            "profit_score": 71.0,
            "safety_score": 37.0,
            "stability_score": 65.0,
            "score_version": "pack_score_v1_singleton_placeholder",
            "normalization_mode": "singleton_placeholder",
            "pack_score_is_placeholder": True,
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
            "hhi_ev_concentration": None,
            "effective_chase_count": None,
            "pack_score": None,
            "profit_score": None,
            "safety_score": None,
            "stability_score": None,
            "p95_value_to_cost_ratio": None,
            "p99_value_to_cost_ratio": None,
            "mean_value_to_cost_ratio": None,
            "expected_loss_when_losing_fraction": None,
            "p05_shortfall_to_cost": None,
            "score_version": "pack_score_v1_singleton_placeholder",
            "normalization_mode": "singleton_placeholder",
            "pack_score_is_placeholder": True,
            "chase_potential_score": None,
            "experience_score": None,
            "chase_potential_tier": None,
            "experience_tier": None,
            "derived_metric_version": None,
        },
    )


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_input_cards")
def test_persist_simulation_inputs_persists_input_rows_without_top_hits_dependency(
    mock_create_simulation_input_cards,
):
    mock_create_simulation_input_cards.return_value = [{"id": "input-card-1"}]

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
        calculation_input=input_df,
        config=object(),
    )

    assert result == {"top_hits_count": 0, "input_cards_count": 1}
    mock_create_simulation_input_cards.assert_called_once_with(
        "run-1",
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
            "pack_score": {
                "pack_score": 0.0,
                "profit_score": 0.0,
                "safety_score": 100.0,
                "stability_score": 0.0,
                "score_version": "pack_score_v1_singleton_placeholder",
                "normalization_mode": "singleton_placeholder",
                "pack_score_is_placeholder": True,
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
            "hhi_ev_concentration": None,
            "effective_chase_count": None,
            "pack_score": None,
            "profit_score": None,
            "safety_score": None,
            "stability_score": None,
            "p95_value_to_cost_ratio": None,
            "p99_value_to_cost_ratio": None,
            "mean_value_to_cost_ratio": None,
            "expected_loss_when_losing_fraction": None,
            "p05_shortfall_to_cost": None,
            "score_version": "pack_score_v1_singleton_placeholder",
            "normalization_mode": "singleton_placeholder",
            "pack_score_is_placeholder": True,
            "chase_potential_score": None,
            "experience_score": None,
            "chase_potential_tier": None,
            "experience_tier": None,
            "derived_metric_version": None,
        },
    )


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_derived_metrics")
def test_persist_simulation_derived_metrics_does_not_map_safety_into_diversification(
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
                "n_cards": 600,
                "total_ev": 7.18,
                "top1_ev_share": 0.22,
                "top3_ev_share": 0.47,
                "top5_ev_share": 0.63,
            },
            "pack_score": {
                "pack_score": 72.4,
                "profit_score": 71.0,
                "safety_score": 12.0,
                "stability_score": 65.0,
                "score_version": "pack_score_v1_singleton_placeholder",
                "normalization_mode": "singleton_placeholder",
                "pack_score_is_placeholder": True,
            },
        },
    )

    persisted_payload = mock_create_simulation_derived_metrics.call_args.args[1]
    assert "safety_score" in persisted_payload
    assert "stability_score" in persisted_payload
    assert "impact_score" not in persisted_payload
    assert "diversification_component" not in persisted_payload


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_input_cards")
def test_persist_simulation_inputs_maps_dataframe_runtime_columns_to_child_table_contract(
    mock_create_simulation_input_cards,
):
    from backend.db.services.calculation_run_persistence_service import persist_simulation_inputs

    mock_create_simulation_input_cards.return_value = [{"id": "input-1"}]

    result = persist_simulation_inputs(
        run_id="run-1",
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

    assert result == {"top_hits_count": 0, "input_cards_count": 1}
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
def test_persist_simulation_inputs_falls_back_to_orchestrator_when_dataframe_missing_ev_fields(
    mock_create_simulation_input_cards,
    mock_orchestrator_cls,
):
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
        calculation_input=runtime_input_df,
        config=config,
    )

    assert result == {"top_hits_count": 0, "input_cards_count": 1}
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
        "pack_score": {
            "pack_score": 72.4,
            "profit_score": 71.0,
            "stability_score": 65.0,
            "safety_score": 37.0,
            "score_version": "pack_score_v1_singleton_placeholder",
            "normalization_mode": "singleton_placeholder",
            "pack_score_is_placeholder": True,
        },
    }

    with pytest.raises(ValueError, match="derived.chase_dependency_metrics.top5_ev_share"):
        persist_simulation_derived_metrics(run_id="run-1", derived=derived)

    mock_create_simulation_derived_metrics.assert_not_called()


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_derived_metrics")
def test_persist_simulation_derived_metrics_persists_real_scores_when_not_placeholder(
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
                "n_cards": 600,
                "total_ev": 7.18,
                "top1_ev_share": 0.22,
                "top3_ev_share": 0.47,
                "top5_ev_share": 0.63,
            },
            "pack_score": {
                "pack_score": 72.4,
                "profit_score": 71.0,
                "safety_score": 37.0,
                "stability_score": 65.0,
                "score_version": "pack_score_v1",
                "normalization_mode": "cross_set_minmax",
                "pack_score_is_placeholder": False,
            },
        },
    )

    persisted_payload = mock_create_simulation_derived_metrics.call_args.args[1]
    assert persisted_payload["pack_score"] == 72.4
    assert persisted_payload["profit_score"] == 71.0
    assert persisted_payload["safety_score"] == 37.0
    assert persisted_payload["stability_score"] == 65.0


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_derived_metrics")
def test_persist_simulation_derived_metrics_rejects_out_of_range_real_scores(
    mock_create_simulation_derived_metrics,
):
    with pytest.raises(ValueError, match="expected 0-100"):
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
                    "n_cards": 600,
                    "total_ev": 7.18,
                    "top1_ev_share": 0.22,
                    "top3_ev_share": 0.47,
                    "top5_ev_share": 0.63,
                },
                "pack_score": {
                    "pack_score": 101.0,
                    "profit_score": 71.0,
                    "safety_score": 37.0,
                    "stability_score": 65.0,
                    "score_version": "pack_score_v1",
                    "normalization_mode": "cross_set_minmax",
                    "pack_score_is_placeholder": False,
                },
            },
        )

    mock_create_simulation_derived_metrics.assert_not_called()


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_derived_metrics")
def test_persist_simulation_derived_metrics_accepts_runtime_v2_and_ignores_runtime_only_detail_fields(
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
                "n_cards": 600,
                "total_ev": 7.18,
                "top1_ev_share": 0.22,
                "top3_ev_share": 0.47,
                "top5_ev_share": 0.63,
                "hhi_ev_concentration": 0.30,
                "effective_chase_count": 3.3333,
            },
            "pack_score": {
                "pack_score": 72.4,
                "profit_score": 71.0,
                "safety_score": 37.0,
                "stability_score": 65.0,
                "chase_potential_score": 64.0,
                "experience_score": 59.0,
                "chase_potential_tier": None,
                "experience_tier": None,
                "derived_metric_version": "derived_intelligence_v1",
                "score_version": "pack_score_v2_1_runtime",
                "normalization_mode": "fixed_anchor_runtime_v2_1",
                "pack_score_is_placeholder": False,
                "weights_pct": {"pack_score": {"profit_score": 40.0}},
                "weights_normalized": {"pack_score": {"profit_score": 0.4}},
                "raw_inputs": {"prob_profit": 0.6},
                "normalized_inputs": {"prob_profit": {"score": 60.0}},
            },
        },
    )

    persisted_payload = mock_create_simulation_derived_metrics.call_args.args[1]
    assert persisted_payload["pack_score"] == 72.4
    assert persisted_payload["profit_score"] == 71.0
    assert persisted_payload["safety_score"] == 37.0
    assert persisted_payload["stability_score"] == 65.0
    assert persisted_payload["score_version"] == "pack_score_v2_1_runtime"
    assert persisted_payload["normalization_mode"] == "fixed_anchor_runtime_v2_1"
    assert persisted_payload["pack_score_is_placeholder"] is False
    assert persisted_payload["hhi_ev_concentration"] == pytest.approx(0.30)
    assert persisted_payload["effective_chase_count"] == pytest.approx(3.3333)
    assert persisted_payload["p95_value_to_cost_ratio"] is None
    assert persisted_payload["chase_potential_score"] == pytest.approx(64.0)
    assert persisted_payload["experience_score"] == pytest.approx(59.0)
    assert persisted_payload["chase_potential_tier"] is None
    assert persisted_payload["experience_tier"] is None
    assert persisted_payload["derived_metric_version"] == "derived_intelligence_v1"
    assert "raw_inputs" not in persisted_payload
    assert "normalized_inputs" not in persisted_payload
    assert "weights_pct" not in persisted_payload
    assert "weights_normalized" not in persisted_payload
    assert "pack_affordability_score" not in persisted_payload
    assert "big_hit_frequency_score" not in persisted_payload
    assert "big_hit_upside_score" not in persisted_payload
    assert "chase_depth_score" not in persisted_payload
    assert "relative_chase_potential_score" not in persisted_payload
    assert "relative_experience_score" not in persisted_payload


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_derived_metrics")
def test_persist_simulation_derived_metrics_uses_pack_score_raw_inputs_fallback_for_concentration_fields(
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
                "n_cards": 600,
                "total_ev": 7.18,
                "top1_ev_share": 0.22,
                "top3_ev_share": 0.47,
                "top5_ev_share": 0.63,
            },
            "pack_score": {
                "pack_score": 72.4,
                "profit_score": 71.0,
                "safety_score": 37.0,
                "stability_score": 65.0,
                "score_version": "pack_score_v2_1_runtime",
                "normalization_mode": "fixed_anchor_runtime_v2_1",
                "pack_score_is_placeholder": False,
                "raw_inputs": {
                    "hhi_ev_concentration": 0.44,
                    "effective_chase_count": 2.2727,
                    "p95_value_to_cost_ratio": 1.91,
                    "p99_value_to_cost_ratio": 2.45,
                },
            },
        },
    )

    persisted_payload = mock_create_simulation_derived_metrics.call_args.args[1]
    assert persisted_payload["hhi_ev_concentration"] == pytest.approx(0.44)
    assert persisted_payload["effective_chase_count"] == pytest.approx(2.2727)
    assert persisted_payload["p99_value_to_cost_ratio"] == pytest.approx(2.45)
    assert persisted_payload["p95_value_to_cost_ratio"] == pytest.approx(1.91)


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
            "simulated_mean_pack_value_vs_pack_cost": {
                "roi": 0.2,
                "value_to_cost_ratio": 1.2,
                "roi_formula": "(expected_value - cost) / cost",
                "metric_semantics_version": "formula_roi_v2",
            },
            "simulated_median_pack_value_vs_pack_cost": {
                "roi": -0.1,
                "value_to_cost_ratio": 0.9,
                "roi_formula": "(expected_value - cost) / cost",
                "metric_semantics_version": "formula_roi_v2",
            },
            "calculated_expected_pack_value_vs_pack_cost": {
                "expected_value": 1.1,
                "roi": 1.1,
                "value_to_cost_ratio": 1.1,
                "roi_formula": "(expected_value - cost) / cost",
                "metric_semantics_version": "formula_roi_v2",
            },
        },
        etb_value_vs_cost_comparison={
            "simulated_mean_etb_value_vs_etb_cost": {
                "roi": 0.15,
                "value_to_cost_ratio": 1.15,
                "roi_formula": "(expected_value - cost) / cost",
                "metric_semantics_version": "formula_roi_v2",
            },
            "simulated_median_etb_value_vs_etb_cost": {
                "roi": 0.05,
                "value_to_cost_ratio": 1.05,
                "roi_formula": "(expected_value - cost) / cost",
                "metric_semantics_version": "formula_roi_v2",
            },
            "calculated_expected_etb_value_vs_etb_cost": {
                "roi": 0.08,
                "value_to_cost_ratio": 1.08,
                "roi_formula": "(expected_value - cost) / cost",
                "metric_semantics_version": "formula_roi_v2",
            },
        },
        booster_box_value_vs_cost_comparison={
            "simulated_mean_booster_box_value_vs_booster_box_cost": {
                "roi": 0.3,
                "value_to_cost_ratio": 1.3,
                "roi_formula": "(expected_value - cost) / cost",
                "metric_semantics_version": "formula_roi_v2",
            },
            "simulated_median_booster_box_value_vs_booster_box_cost": {
                "roi": 0.1,
                "value_to_cost_ratio": 1.1,
                "roi_formula": "(expected_value - cost) / cost",
                "metric_semantics_version": "formula_roi_v2",
            },
            "calculated_expected_booster_box_value_vs_booster_box_cost": {
                "roi": 0.2,
                "value_to_cost_ratio": 1.2,
                "roi_formula": "(expected_value - cost) / cost",
                "metric_semantics_version": "formula_roi_v2",
            },
        },
    )

    assert result["run_id"] == "run-1"
    assert result["config_hash"] == "cfg-hash"

    comparison_payload = mock_create_parent_calculation_run.call_args.args[6]
    assert comparison_payload == {
        "simulated_mean_pack_value_vs_pack_cost": 0.2,
        "simulated_median_pack_value_vs_pack_cost": -0.1,
        "calculated_expected_pack_value_vs_pack_cost": 1.1,
        "simulated_mean_etb_value_vs_etb_cost": 0.15,
        "simulated_median_etb_value_vs_etb_cost": 0.05,
        "calculated_expected_etb_value_vs_etb_cost": 0.08,
        "simulated_mean_booster_box_value_vs_booster_box_cost": 0.3,
        "simulated_median_booster_box_value_vs_booster_box_cost": 0.1,
        "calculated_expected_booster_box_value_vs_booster_box_cost": 0.2,
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
            "simulated_mean_pack_value_vs_pack_cost": {
                "roi": 0.2,
                "value_to_cost_ratio": 1.2,
                "roi_formula": "(expected_value - cost) / cost",
                "metric_semantics_version": "formula_roi_v2",
            },
            "simulated_median_pack_value_vs_pack_cost": {
                "roi": -0.1,
                "value_to_cost_ratio": 0.9,
                "roi_formula": "(expected_value - cost) / cost",
                "metric_semantics_version": "formula_roi_v2",
            },
            "calculated_expected_pack_value_vs_pack_cost": {
                "expected_value": 1.1,
                "roi": 1.1,
                "value_to_cost_ratio": 1.1,
                "roi_formula": "(expected_value - cost) / cost",
                "metric_semantics_version": "formula_roi_v2",
            },
        },
        etb_value_vs_cost_comparison=None,
        booster_box_value_vs_cost_comparison={
            "simulated_mean_booster_box_value_vs_booster_box_cost": {
                "roi": 0.3,
                "value_to_cost_ratio": 1.3,
                "roi_formula": "(expected_value - cost) / cost",
                "metric_semantics_version": "formula_roi_v2",
            },
            "simulated_median_booster_box_value_vs_booster_box_cost": {
                "roi": 0.1,
                "value_to_cost_ratio": 1.1,
                "roi_formula": "(expected_value - cost) / cost",
                "metric_semantics_version": "formula_roi_v2",
            },
            "calculated_expected_booster_box_value_vs_booster_box_cost": {
                "roi": 0.2,
                "value_to_cost_ratio": 1.2,
                "roi_formula": "(expected_value - cost) / cost",
                "metric_semantics_version": "formula_roi_v2",
            },
        },
    )

    assert result["snapshot_count"] == 2
    comparison_payload = mock_create_parent_calculation_run.call_args.args[6]
    assert comparison_payload["simulated_mean_etb_value_vs_etb_cost"] is None
    assert comparison_payload["simulated_median_etb_value_vs_etb_cost"] is None
    assert comparison_payload["calculated_expected_etb_value_vs_etb_cost"] is None
    snapshot_keys = [call.args[1] for call in mock_create_calculation_price_snapshot.call_args_list]
    assert snapshot_keys == ["pack", "booster_box"]


def test_derive_slot_schema_combo_state_counts_extracts_reverse_plus_rare_states():
    sim_results = {
        "packs": [
            {
                "entry_path": "slot_schema",
                "cards": [
                    {
                        "slot_group": "rare_family",
                        "slot_role": "reverse_parallel",
                        "outcome": "regular reverse",
                    },
                    {
                        "slot_group": "rare_family",
                        "slot_role": "rare_or_better",
                        "outcome": "rare",
                    },
                ],
            },
            {
                "entry_path": "slot_schema",
                "cards": [
                    {
                        "slot_group": "rare_family",
                        "slot_role": "reverse_parallel",
                        "outcome": "holo rare",
                    },
                    {
                        "slot_group": "rare_family",
                        "slot_role": "rare_or_better",
                        "outcome": "regular v",
                    },
                ],
            },
        ]
    }

    combo_counts = _derive_slot_schema_combo_state_counts(sim_results)

    assert combo_counts == {
        "reverse:regular reverse|rare:rare": 1,
        "reverse:holo rare|rare:regular v": 1,
    }


def test_derive_slot_schema_combo_state_counts_preserves_double_hit_state():
    sim_results = {
        "packs": [
            {
                "entry_path": "slot_schema",
                "cards": [
                    {
                        "slot_group": "rare_family",
                        "slot_role": "reverse_parallel",
                        "outcome": "reverse rare",
                    },
                    {
                        "slot_group": "rare_family",
                        "slot_role": "rare_or_better",
                        "outcome": "regular v",
                    },
                ],
            }
        ]
    }

    combo_counts = _derive_slot_schema_combo_state_counts(sim_results)

    assert combo_counts == {"reverse:reverse rare|rare:regular v": 1}


@patch("backend.db.services.calculation_run_persistence_service.compute_simulation_value_threshold_bins")
@patch("backend.db.services.calculation_run_persistence_service.create_simulation_value_threshold_bins")
@patch("backend.db.services.calculation_run_persistence_service.compute_simulation_value_distribution_bins")
@patch("backend.db.services.calculation_run_persistence_service.create_simulation_value_distribution_bins")
@patch("backend.db.services.calculation_run_persistence_service.persist_simulation_derived_metrics")
@patch("backend.db.services.calculation_run_persistence_service.create_simulation_state_counts")
@patch("backend.db.services.calculation_run_persistence_service.create_simulation_pull_summary")
@patch("backend.db.services.calculation_run_persistence_service.create_simulation_percentiles")
@patch("backend.db.services.calculation_run_persistence_service.create_simulation_run_summary")
@patch("backend.db.services.calculation_run_persistence_service._build_simulation_summary_payloads")
def test_persist_simulation_outputs_wires_combo_counts_without_breaking_pull_summary(
    mock_build_summary_payloads,
    mock_create_run_summary,
    mock_create_percentiles,
    mock_create_pull_summary,
    mock_create_state_counts,
    mock_persist_derived,
    mock_create_distribution_bins,
    mock_compute_distribution_bins,
    mock_create_threshold_bins,
    mock_compute_threshold_bins,
):
    mock_build_summary_payloads.return_value = ({"values": [1.0]}, {"pack_cost": 5.0})
    mock_create_run_summary.return_value = {"id": "summary-1"}
    mock_create_percentiles.return_value = []
    mock_create_pull_summary.return_value = []
    mock_create_state_counts.return_value = []
    mock_persist_derived.return_value = []
    mock_compute_distribution_bins.return_value = []
    mock_create_distribution_bins.return_value = []
    mock_compute_threshold_bins.return_value = []
    mock_create_threshold_bins.return_value = []

    sim_results = {
        "values": [1.0],
        "pack_path_counts": {"normal": 1},
        "pack_state_counts": {"baseline": 1},
        "packs": [
            {
                "entry_path": "slot_schema",
                "cards": [
                    {
                        "slot_group": "rare_family",
                        "slot_role": "reverse_parallel",
                        "outcome": "reverse rare",
                    },
                    {
                        "slot_group": "rare_family",
                        "slot_role": "rare_or_better",
                        "outcome": "regular v",
                    },
                ],
            }
        ],
    }

    persist_simulation_outputs(
        run_id="run-1",
        sim_results=sim_results,
        pack_metrics={"total_ev": 1.0},
        derived={"pack_decision_metrics": {}},
    )

    mock_create_pull_summary.assert_called_once()
    state_sim_results = mock_create_state_counts.call_args.args[1]
    assert state_sim_results["pack_path_counts"] == {"normal": 1}
    assert state_sim_results["pack_state_counts"] == {"baseline": 1}
    assert state_sim_results["slot_schema_combo_state_counts"] == {
        "reverse:reverse rare|rare:regular v": 1,
    }
