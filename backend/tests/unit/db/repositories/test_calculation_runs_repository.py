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
def test_create_simulation_derived_metrics_persists_all_required_fields_non_null(mock_insert_required_payload):
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
        "index_score": 72.4,
        "profit_component": 0.71,
        "stability_component": 0.65,
        "diversification_component": 0.37,
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
        "index_score": 72.4,
        "profit_component": 0.71,
        "stability_component": 0.65,
        "diversification_component": 0.37,
    }
    for field, value in inserted_payload.items():
        assert value is not None, f"Expected non-null value for {field}"


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
        "index_score": 72.4,
        "profit_component": 0.71,
        "stability_component": 0.65,
        "diversification_component": 0.37,
    }

    with pytest.raises(ValueError, match="simulation_derived_metrics: top5_ev_share"):
        create_simulation_derived_metrics("run-1", derived_payload)

    mock_insert_required_payload.assert_not_called()


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
        "simulation_count": 100000,
        "pack_cost": 5.0,
        "total_ev": 6.0,
        "net_value": 1.0,
        "roi": 1.2,
        "roi_percent": 20.0,
    }

    mock_select_rows.side_effect = [[run_row], [derived_row], [summary_row]]

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


@patch("backend.db.repositories.calculation_runs_repository._select_rows_with_candidates", return_value=[])
def test_get_latest_run_snapshot_for_target_returns_none_when_no_runs_exist(_mock_select_rows):
    assert get_latest_run_snapshot_for_target("set", "missing") is None
