from unittest.mock import patch

import pytest

from backend.db.repositories.calculation_runs_repository import (
    COMPARISON_METRIC_FIELDS,
    DERIVED_METRIC_FIELDS,
    ETB_COMPARISON_METRIC_FIELDS,
    _parse_percentile_rank,
    create_parent_calculation_run,
    get_latest_run_snapshot_for_target,
    create_simulation_derived_metrics,
    create_simulation_percentiles,
)


@pytest.mark.parametrize(
    "label,expected",
    [
        ("5th", 5.0),
        ("25th", 25.0),
        ("50th", 50.0),
        ("50th (median)", 50.0),
        ("95", 95.0),
        ("99th percentile", 99.0),
        (" 25.5th ", 25.5),
    ],
)
def test_parse_percentile_rank_accepts_valid_labels(label, expected):
    assert _parse_percentile_rank(label) == pytest.approx(expected)


@pytest.mark.parametrize("label", ["", "median", "p95", "top quartile"]) 
def test_parse_percentile_rank_rejects_invalid_labels(label):
    assert _parse_percentile_rank(label) is None


@patch("backend.db.repositories.calculation_runs_repository._insert_required_payload")
def test_create_simulation_percentiles_persists_numeric_percentile_ranks(mock_insert_required_payload):
    mock_insert_required_payload.side_effect = [
        {"id": "row-1", "percentile": 5.0, "value": 1.0},
        {"id": "row-2", "percentile": 50.0, "value": 2.0},
        {"id": "row-3", "percentile": 95.0, "value": 3.0},
    ]

    sim_results = {
        "percentiles": {
            "5th": 1.0,
            "50th (median)": 2.0,
            "95th": 3.0,
        }
    }

    rows = create_simulation_percentiles("run-1", sim_results)

    assert len(rows) == 3
    inserted_payloads = [call.args[1] for call in mock_insert_required_payload.call_args_list]
    assert inserted_payloads == [
        {"calculation_run_id": "run-1", "percentile": 5.0, "value": 1.0},
        {"calculation_run_id": "run-1", "percentile": 50.0, "value": 2.0},
        {"calculation_run_id": "run-1", "percentile": 95.0, "value": 3.0},
    ]


@patch("backend.db.repositories.calculation_runs_repository._insert_required_payload")
def test_create_simulation_percentiles_raises_for_invalid_label(mock_insert_required_payload):
    with pytest.raises(ValueError, match="Invalid percentile label"):
        create_simulation_percentiles("run-1", {"percentiles": {"median": 1.0}})

    mock_insert_required_payload.assert_not_called()


@patch("backend.db.repositories.calculation_runs_repository._insert_required_payload")
def test_create_simulation_percentiles_raises_for_missing_value(mock_insert_required_payload):
    with pytest.raises(ValueError, match="Missing required percentile value"):
        create_simulation_percentiles("run-1", {"percentiles": {"50th": None}})

    mock_insert_required_payload.assert_not_called()


@patch("backend.db.repositories.calculation_runs_repository._insert_required_payload")
def test_create_simulation_derived_metrics_persists_placeholder_with_null_scores(mock_insert_required_payload):
    mock_insert_required_payload.return_value = {"id": "derived-1"}

    derived_payload = {
        "hit_ev": 6.16,
        "non_hit_ev": 1.02,
        "hit_ev_share": 0.858,
        "hit_cards_tracked": 208,
        "cards_tracked": 600,
        "total_card_ev": 7.18,
        "top1_ev_share": 0.22,
        "top3_ev_share": 0.47,
        "top5_ev_share": 0.63,
        "pack_score": None,
        "profit_score": None,
        "safety_score": None,
        "stability_score": None,
        "p95_value_to_cost_ratio": None,
        "score_version": "pack_score_v1_singleton_placeholder",
        "normalization_mode": "singleton_placeholder",
        "pack_score_is_placeholder": True,
    }

    rows = create_simulation_derived_metrics("run-1", derived_payload)

    assert rows == [{"id": "derived-1"}]
    inserted_payload = mock_insert_required_payload.call_args.args[1]
    assert inserted_payload == {
        "calculation_run_id": "run-1",
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
    }


@patch("backend.db.repositories.calculation_runs_repository._insert_required_payload")
def test_create_simulation_derived_metrics_allows_missing_composite_fields(mock_insert_required_payload):
    mock_insert_required_payload.return_value = {"id": "derived-1"}

    rows = create_simulation_derived_metrics("run-1", {})

    assert rows == [{"id": "derived-1"}]
    inserted_payload = mock_insert_required_payload.call_args.args[1]
    assert inserted_payload == {
        "calculation_run_id": "run-1",
        "hit_ev": None,
        "non_hit_ev": None,
        "hit_ev_share": None,
        "hit_cards_tracked": None,
        "cards_tracked": None,
        "total_card_ev": None,
        "top1_ev_share": None,
        "top3_ev_share": None,
        "top5_ev_share": None,
        "hhi_ev_concentration": None,
        "effective_chase_count": None,
        "pack_score": None,
        "profit_score": None,
        "safety_score": None,
        "stability_score": None,
        "p95_value_to_cost_ratio": None,
        "mean_value_to_cost_ratio": None,
        "expected_loss_when_losing_fraction": None,
        "p05_shortfall_to_cost": None,
        "score_version": None,
        "normalization_mode": None,
        "pack_score_is_placeholder": None,
        "chase_potential_score": None,
        "experience_score": None,
        "chase_potential_tier": None,
        "experience_tier": None,
        "derived_metric_version": None,
    }


@patch("backend.db.repositories.calculation_runs_repository._insert_required_payload")
def test_create_simulation_derived_metrics_raises_when_required_field_missing(mock_insert_required_payload):
    derived_payload = {
        "hit_ev": 6.16,
        "non_hit_ev": 1.02,
        "hit_ev_share": 0.858,
        "hit_cards_tracked": 208,
        "cards_tracked": 600,
        "total_card_ev": 7.18,
        "top1_ev_share": 0.22,
        "top3_ev_share": 0.47,
        # top5_ev_share missing on purpose
        "pack_score": None,
        "profit_score": None,
        "safety_score": None,
        "stability_score": None,
        "p95_value_to_cost_ratio": None,
        "score_version": "pack_score_v1_singleton_placeholder",
        "normalization_mode": "singleton_placeholder",
        "pack_score_is_placeholder": True,
    }

    with pytest.raises(ValueError, match="Missing required field: calculation_run_id"):
        create_simulation_derived_metrics(None, derived_payload)

    mock_insert_required_payload.assert_not_called()


@patch("backend.db.repositories.calculation_runs_repository._insert_required_payload")
def test_create_simulation_derived_metrics_persists_real_scores_when_present(mock_insert_required_payload):
    mock_insert_required_payload.return_value = {"id": "derived-1"}

    rows = create_simulation_derived_metrics(
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
            "pack_score": 72.4,
            "profit_score": 71.0,
            "safety_score": 37.0,
            "stability_score": 65.0,
            "p95_value_to_cost_ratio": 1.91,
            "score_version": "pack_score_v1",
            "normalization_mode": "cross_set_minmax",
            "pack_score_is_placeholder": False,
        },
    )

    assert rows == [{"id": "derived-1"}]
    inserted_payload = mock_insert_required_payload.call_args.args[1]
    assert inserted_payload == {
        "calculation_run_id": "run-1",
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
        "pack_score": 72.4,
        "profit_score": 71.0,
        "safety_score": 37.0,
        "stability_score": 65.0,
        "p95_value_to_cost_ratio": 1.91,
        "mean_value_to_cost_ratio": None,
        "expected_loss_when_losing_fraction": None,
        "p05_shortfall_to_cost": None,
        "score_version": "pack_score_v1",
        "normalization_mode": "cross_set_minmax",
        "pack_score_is_placeholder": False,
        "chase_potential_score": None,
        "experience_score": None,
        "chase_potential_tier": None,
        "experience_tier": None,
        "derived_metric_version": None,
    }


@patch("backend.db.repositories.calculation_runs_repository._insert_required_payload")
def test_create_simulation_derived_metrics_persists_only_composite_stage1_fields(mock_insert_required_payload):
    mock_insert_required_payload.return_value = {"id": "derived-1"}

    rows = create_simulation_derived_metrics(
        "run-1",
        {
            "pack_score": 72.4,
            "profit_score": 71.0,
            "safety_score": 37.0,
            "stability_score": 65.0,
            "p95_value_to_cost_ratio": 1.91,
            "pack_affordability_score": 55.0,
            "big_hit_frequency_score": 62.0,
            "big_hit_upside_score": 70.0,
            "chase_depth_score": 48.0,
            "relative_chase_potential_score": 66.0,
            "relative_experience_score": 61.0,
            "chase_potential_score": 64.0,
            "experience_score": 59.0,
            "chase_potential_tier": None,
            "experience_tier": None,
            "derived_metric_version": "derived_intelligence_v1",
        },
    )

    assert rows == [{"id": "derived-1"}]
    inserted_payload = mock_insert_required_payload.call_args.args[1]
    assert inserted_payload == {
        "calculation_run_id": "run-1",
        "hit_ev": None,
        "non_hit_ev": None,
        "hit_ev_share": None,
        "hit_cards_tracked": None,
        "cards_tracked": None,
        "total_card_ev": None,
        "top1_ev_share": None,
        "top3_ev_share": None,
        "top5_ev_share": None,
        "hhi_ev_concentration": None,
        "effective_chase_count": None,
        "pack_score": 72.4,
        "profit_score": 71.0,
        "safety_score": 37.0,
        "stability_score": 65.0,
        "p95_value_to_cost_ratio": 1.91,
        "mean_value_to_cost_ratio": None,
        "expected_loss_when_losing_fraction": None,
        "p05_shortfall_to_cost": None,
        "score_version": None,
        "normalization_mode": None,
        "pack_score_is_placeholder": None,
        "chase_potential_score": 64.0,
        "experience_score": 59.0,
        "chase_potential_tier": None,
        "experience_tier": None,
        "derived_metric_version": "derived_intelligence_v1",
    }


@patch("backend.db.repositories.calculation_runs_repository._insert_required_payload")
def test_create_parent_calculation_run_includes_comparison_metrics_in_payload(mock_insert_required_payload):
    mock_insert_required_payload.return_value = {"id": "run-1"}

    result = create_parent_calculation_run(
        "cfg-1",
        "set",
        "set-1",
        "combined",
        "notes",
        "monte_carlo_v2",
        {
            "simulated_mean_pack_value_vs_pack_cost": 1.2,
            "simulated_median_pack_value_vs_pack_cost": 0.9,
            "calculated_expected_pack_value_vs_pack_cost": 1.1,
            "simulated_mean_etb_value_vs_etb_cost": 1.15,
            "simulated_median_etb_value_vs_etb_cost": 1.05,
            "calculated_expected_etb_value_vs_etb_cost": 1.08,
            "simulated_mean_booster_box_value_vs_booster_box_cost": 1.3,
            "simulated_median_booster_box_value_vs_booster_box_cost": 1.1,
            "calculated_expected_booster_box_value_vs_booster_box_cost": 1.2,
        },
    )

    assert result == {"id": "run-1"}
    inserted_payload = mock_insert_required_payload.call_args.args[1]
    assert inserted_payload["target_type"] == "set"
    assert inserted_payload["simulated_mean_pack_value_vs_pack_cost"] == pytest.approx(1.2)
    assert inserted_payload["simulated_median_pack_value_vs_pack_cost"] == pytest.approx(0.9)
    assert inserted_payload["calculated_expected_pack_value_vs_pack_cost"] == pytest.approx(1.1)
    assert inserted_payload["simulated_mean_etb_value_vs_etb_cost"] == pytest.approx(1.15)
    assert inserted_payload["simulated_median_etb_value_vs_etb_cost"] == pytest.approx(1.05)
    assert inserted_payload["calculated_expected_etb_value_vs_etb_cost"] == pytest.approx(1.08)
    assert inserted_payload["simulated_mean_booster_box_value_vs_booster_box_cost"] == pytest.approx(1.3)
    assert inserted_payload["simulated_median_booster_box_value_vs_booster_box_cost"] == pytest.approx(1.1)
    assert inserted_payload["calculated_expected_booster_box_value_vs_booster_box_cost"] == pytest.approx(1.2)


@patch("backend.db.repositories.calculation_runs_repository._select_rows_with_candidates")
def test_get_latest_run_snapshot_for_target_includes_explicit_derived_and_comparison_fields(mock_select_rows):
    run_row = {
        "id": "run-1",
        "created_at": "2026-04-18T00:00:00Z",
        "target_type": "set",
        "target_id": "sv8",
    }
    for index, field in enumerate(COMPARISON_METRIC_FIELDS, start=1):
        run_row[field] = float(index) / 10.0

    derived_row = {"calculation_run_id": "run-1"}
    for index, field in enumerate(DERIVED_METRIC_FIELDS, start=1):
        derived_row[field] = float(index)

    summary_row = {
        "calculation_run_id": "run-1",
        "simulation_count": 1000000,
        "pack_cost": 5.0,
        "total_ev": 6.0,
        "net_value": 1.0,
        "roi": 1.2,
        "roi_percent": 20.0,
    }

    percentile_row = {
        "calculation_run_id": "run-1",
        "percentile": 95.0,
        "value": 9.55,
    }

    mock_select_rows.side_effect = [[run_row], [derived_row], [summary_row], [percentile_row]]

    snapshot = get_latest_run_snapshot_for_target("set", "sv8")

    assert snapshot is not None
    assert snapshot["run"]["id"] == "run-1"

    for field in COMPARISON_METRIC_FIELDS:
        assert field in snapshot["comparison_metrics"]
        if field in ETB_COMPARISON_METRIC_FIELDS:
            assert snapshot["comparison_metrics"][field] is None
            assert snapshot["run"][field] is None
        else:
            assert snapshot["comparison_metrics"][field] == run_row[field]
            assert snapshot["run"][field] == run_row[field]

    for field in DERIVED_METRIC_FIELDS:
        assert field in snapshot["derived_metrics"]
        assert snapshot["derived_metrics"][field] == derived_row[field]

    assert snapshot["simulation_summary"]["calculation_run_id"] == "run-1"
    assert snapshot["simulation_summary"]["p95_value"] == pytest.approx(9.55)


@patch("backend.db.repositories.calculation_runs_repository._select_rows_with_candidates", return_value=[])
def test_get_latest_run_snapshot_for_target_returns_none_when_no_runs_exist(_mock_select_rows):
    assert get_latest_run_snapshot_for_target("set", "missing") is None


def test_derived_metric_fields_include_pack_score_v2_concentration_fields():
    assert "hhi_ev_concentration" in DERIVED_METRIC_FIELDS
    assert "effective_chase_count" in DERIVED_METRIC_FIELDS


def test_derived_metric_fields_include_stage1_composites_but_not_internal_components():
    for field in [
        "chase_potential_score",
        "experience_score",
        "chase_potential_tier",
        "experience_tier",
        "derived_metric_version",
    ]:
        assert field in DERIVED_METRIC_FIELDS

    for field in [
        "pack_affordability_score",
        "big_hit_frequency_score",
        "big_hit_upside_score",
        "chase_depth_score",
        "relative_chase_potential_score",
        "relative_experience_score",
    ]:
        assert field not in DERIVED_METRIC_FIELDS
