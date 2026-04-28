"""Unit tests for fixed-threshold value bin aggregation and persistence wiring."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.simulations.value_threshold_bins import (
    DEFAULT_VALUE_THRESHOLD_BUCKETS,
    compute_simulation_value_threshold_bins,
)


def test_threshold_bins_raise_on_empty_values():
    with pytest.raises(ValueError, match="must not be empty"):
        compute_simulation_value_threshold_bins([])


def test_threshold_bins_counts_and_probabilities_cover_all_values():
    values = [0.2, 0.8, 1.0, 4.5, 9.99, 10.0, 40.0, 150.0, 6000.0]

    rows = compute_simulation_value_threshold_bins(values)

    assert len(rows) == len(DEFAULT_VALUE_THRESHOLD_BUCKETS)
    assert sum(row["occurrence_count"] for row in rows) == len(values)
    assert sum(row["probability"] for row in rows) == pytest.approx(1.0, abs=1e-9)


def test_threshold_bins_monotonicity_and_survival_definition():
    values = [0.2, 1.1, 8.0, 8.5, 40.0, 250.0, 900.0, 3200.0]

    rows = compute_simulation_value_threshold_bins(values)

    for i in range(1, len(rows)):
        assert rows[i]["cumulative_probability"] >= rows[i - 1]["cumulative_probability"]
        assert rows[i]["survival_probability"] <= rows[i - 1]["survival_probability"]

    for row in rows:
        expected_survival = 1.0 - row["cumulative_probability"] + row["probability"]
        assert row["survival_probability"] == pytest.approx(expected_survival, abs=1e-12)


def test_threshold_bins_known_boundaries():
    # [0,1), [1,5), [5,10), [10,25), [5000,+inf)
    values = [0.0, 0.9999, 1.0, 4.9999, 5.0, 10.0, 5000.0, 5001.0]

    rows = compute_simulation_value_threshold_bins(values)

    assert rows[0]["occurrence_count"] == 2
    assert rows[1]["occurrence_count"] == 2
    assert rows[2]["occurrence_count"] == 1
    assert rows[3]["occurrence_count"] == 1
    assert rows[-1]["occurrence_count"] == 2


@patch("backend.db.repositories.calculation_runs_repository._insert_required_payload")
def test_create_simulation_value_threshold_bins_inserts_expected_payloads(mock_insert):
    from backend.db.repositories.calculation_runs_repository import (
        create_simulation_value_threshold_bins,
    )

    mock_insert.side_effect = [{"id": "row-1"}, {"id": "row-2"}]

    bins = [
        {
            "threshold_floor": 0.0,
            "threshold_ceiling": 1.0,
            "occurrence_count": 25,
            "probability": 0.5,
            "cumulative_probability": 0.5,
            "survival_probability": 1.0,
            "bucket_label": "0-1",
            "bucket_order": 1,
        },
        {
            "threshold_floor": 1.0,
            "threshold_ceiling": None,
            "occurrence_count": 25,
            "probability": 0.5,
            "cumulative_probability": 1.0,
            "survival_probability": 0.5,
            "bucket_label": ">=1",
            "bucket_order": 2,
        },
    ]

    rows = create_simulation_value_threshold_bins("run-thr", bins)

    assert len(rows) == 2
    assert mock_insert.call_count == 2

    first_payload = mock_insert.call_args_list[0].args[1]
    second_payload = mock_insert.call_args_list[1].args[1]

    assert first_payload["calculation_run_id"] == "run-thr"
    assert first_payload["threshold_floor"] == pytest.approx(0.0)
    assert first_payload["threshold_ceiling"] == pytest.approx(1.0)
    assert first_payload["bucket_order"] == 1

    assert second_payload["threshold_ceiling"] is None
    assert second_payload["bucket_label"] == ">=1"


@patch("backend.db.repositories.calculation_runs_repository._insert_required_payload")
def test_create_simulation_value_threshold_bins_empty_returns_empty(mock_insert):
    from backend.db.repositories.calculation_runs_repository import (
        create_simulation_value_threshold_bins,
    )

    result = create_simulation_value_threshold_bins("run-empty", [])

    assert result == []
    mock_insert.assert_not_called()
