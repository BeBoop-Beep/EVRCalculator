"""Unit tests for compute_simulation_value_distribution_bins."""
from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from backend.simulations.value_distribution_bins import (
    compute_simulation_value_distribution_bins,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sum_occurrence_counts(bins: list[dict]) -> int:
    return sum(b["occurrence_count"] for b in bins)


def _sum_probabilities(bins: list[dict]) -> float:
    return sum(b["probability"] for b in bins)


# ── Edge-case: empty input ────────────────────────────────────────────────────

def test_raises_on_empty_values():
    with pytest.raises(ValueError, match="empty"):
        compute_simulation_value_distribution_bins([])


def test_raises_on_zero_bins():
    with pytest.raises(ValueError, match="num_bins"):
        compute_simulation_value_distribution_bins([1.0, 2.0], num_bins=0)


# ── Single-value edge case ────────────────────────────────────────────────────

def test_single_value_produces_one_bin():
    values = [5.0] * 1_000
    bins = compute_simulation_value_distribution_bins(values)
    assert len(bins) == 1


def test_single_value_bin_fields():
    values = [3.75] * 500
    bins = compute_simulation_value_distribution_bins(values)
    b = bins[0]
    assert b["bin_floor"] == pytest.approx(3.75)
    assert b["bin_ceiling"] == pytest.approx(3.75)
    assert b["occurrence_count"] == 500
    assert b["probability"] == pytest.approx(1.0)
    assert b["cumulative_probability"] == pytest.approx(1.0)
    assert b["survival_probability"] == pytest.approx(1.0)


# ── Occurrence count integrity ────────────────────────────────────────────────

def test_occurrence_counts_sum_to_simulation_count():
    import random
    rng = random.Random(42)
    values = [rng.uniform(0.5, 50.0) for _ in range(10_000)]
    bins = compute_simulation_value_distribution_bins(values)
    assert _sum_occurrence_counts(bins) == len(values)


def test_occurrence_counts_sum_known_values():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    bins = compute_simulation_value_distribution_bins(values, num_bins=5)
    assert _sum_occurrence_counts(bins) == 5


# ── Probability integrity ─────────────────────────────────────────────────────

def test_probabilities_sum_to_approximately_one():
    import random
    rng = random.Random(7)
    values = [rng.uniform(0.0, 100.0) for _ in range(50_000)]
    bins = compute_simulation_value_distribution_bins(values)
    assert _sum_probabilities(bins) == pytest.approx(1.0, abs=1e-9)


def test_all_probabilities_between_zero_and_one():
    import random
    rng = random.Random(99)
    values = [rng.uniform(0.0, 20.0) for _ in range(1_000)]
    bins = compute_simulation_value_distribution_bins(values)
    for b in bins:
        assert 0.0 <= b["probability"] <= 1.0


# ── Cumulative probability ────────────────────────────────────────────────────

def test_cumulative_probability_is_monotonically_nondecreasing():
    import random
    rng = random.Random(13)
    values = [rng.uniform(1.0, 10.0) for _ in range(5_000)]
    bins = compute_simulation_value_distribution_bins(values)
    for i in range(1, len(bins)):
        assert bins[i]["cumulative_probability"] >= bins[i - 1]["cumulative_probability"]


def test_cumulative_probability_ends_at_one():
    import random
    rng = random.Random(17)
    values = [rng.uniform(0.0, 50.0) for _ in range(10_000)]
    bins = compute_simulation_value_distribution_bins(values)
    assert bins[-1]["cumulative_probability"] == pytest.approx(1.0, abs=1e-9)


# ── Survival probability ──────────────────────────────────────────────────────

def test_survival_probability_is_monotonically_nonincreasing():
    import random
    rng = random.Random(23)
    values = [rng.uniform(2.0, 80.0) for _ in range(5_000)]
    bins = compute_simulation_value_distribution_bins(values)
    for i in range(1, len(bins)):
        assert bins[i]["survival_probability"] <= bins[i - 1]["survival_probability"]


def test_survival_probability_starts_at_one():
    import random
    rng = random.Random(31)
    values = [rng.uniform(0.5, 15.0) for _ in range(10_000)]
    bins = compute_simulation_value_distribution_bins(values)
    assert bins[0]["survival_probability"] == pytest.approx(1.0, abs=1e-9)


# ── Max-value inclusion in final bin ─────────────────────────────────────────

def test_max_value_is_included_in_final_bin():
    values = [1.0, 2.0, 3.0, 10.0]  # max is 10.0
    bins = compute_simulation_value_distribution_bins(values, num_bins=5)
    assert bins[-1]["bin_ceiling"] == pytest.approx(10.0)
    assert _sum_occurrence_counts(bins) == 4  # max value must not be dropped


def test_max_value_occurrence_counted():
    """max_value must land in the final bin, not fall off the edge."""
    values = list(range(1, 101))  # 1..100, max = 100
    bins = compute_simulation_value_distribution_bins(values, num_bins=10)
    assert _sum_occurrence_counts(bins) == 100
    assert bins[-1]["bin_ceiling"] == pytest.approx(100.0)


# ── Known-value verification ──────────────────────────────────────────────────

def test_uniform_values_produce_correct_bin_count():
    import random
    rng = random.Random(55)
    values = [rng.uniform(0.0, 1.0) for _ in range(100_000)]
    bins = compute_simulation_value_distribution_bins(values, num_bins=50)
    assert len(bins) == 50


def test_known_values_bin_assignment():
    """With 4 values and 2 bins, verify counts manually."""
    # range = [0, 4], bin_width = 2
    # bin0: [0, 2)  → 0.0, 1.0  → 2 items
    # bin1: [2, 4]  → 3.0, 4.0  → 2 items
    values = [0.0, 1.0, 3.0, 4.0]
    bins = compute_simulation_value_distribution_bins(values, num_bins=2)
    assert len(bins) == 2
    assert bins[0]["occurrence_count"] == 2
    assert bins[1]["occurrence_count"] == 2
    assert bins[0]["probability"] == pytest.approx(0.5)
    assert bins[1]["probability"] == pytest.approx(0.5)
    assert bins[0]["cumulative_probability"] == pytest.approx(0.5)
    assert bins[1]["cumulative_probability"] == pytest.approx(1.0)
    assert bins[0]["survival_probability"] == pytest.approx(1.0)
    assert bins[1]["survival_probability"] == pytest.approx(0.5)


# ── DB payload shape ──────────────────────────────────────────────────────────

def test_persistence_payload_contains_only_expected_fields():
    """Bins must not carry unexpected keys that would corrupt a DB insert."""
    expected_keys = {
        "bin_floor",
        "bin_ceiling",
        "occurrence_count",
        "probability",
        "cumulative_probability",
        "survival_probability",
    }
    values = [float(i) for i in range(1, 101)]
    bins = compute_simulation_value_distribution_bins(values)
    for b in bins:
        assert set(b.keys()) == expected_keys


# ── Repository persistence wiring ────────────────────────────────────────────

@patch(
    "backend.db.repositories.calculation_runs_repository._insert_required_payload"
)
def test_create_simulation_value_distribution_bins_inserts_correct_payloads(mock_insert):
    from backend.db.repositories.calculation_runs_repository import (
        create_simulation_value_distribution_bins,
    )

    mock_insert.side_effect = [
        {"id": f"row-{i}"} for i in range(2)
    ]

    bins = [
        {
            "bin_floor": 0.0,
            "bin_ceiling": 5.0,
            "occurrence_count": 30,
            "probability": 0.6,
            "cumulative_probability": 0.6,
            "survival_probability": 1.0,
        },
        {
            "bin_floor": 5.0,
            "bin_ceiling": 10.0,
            "occurrence_count": 20,
            "probability": 0.4,
            "cumulative_probability": 1.0,
            "survival_probability": 0.4,
        },
    ]

    rows = create_simulation_value_distribution_bins("run-abc", bins)

    assert len(rows) == 2
    assert mock_insert.call_count == 2

    first_payload = mock_insert.call_args_list[0].args[1]
    assert first_payload["calculation_run_id"] == "run-abc"
    assert first_payload["bin_floor"] == pytest.approx(0.0)
    assert first_payload["bin_ceiling"] == pytest.approx(5.0)
    assert first_payload["occurrence_count"] == 30
    assert first_payload["probability"] == pytest.approx(0.6)
    assert first_payload["cumulative_probability"] == pytest.approx(0.6)
    assert first_payload["survival_probability"] == pytest.approx(1.0)

    # Confirm only the 7 allowed keys are in the payload (+ calculation_run_id).
    allowed = {
        "calculation_run_id",
        "bin_floor",
        "bin_ceiling",
        "occurrence_count",
        "probability",
        "cumulative_probability",
        "survival_probability",
    }
    for call in mock_insert.call_args_list:
        assert set(call.args[1].keys()) == allowed


@patch(
    "backend.db.repositories.calculation_runs_repository._insert_required_payload"
)
def test_create_simulation_value_distribution_bins_empty_returns_empty(mock_insert):
    from backend.db.repositories.calculation_runs_repository import (
        create_simulation_value_distribution_bins,
    )

    result = create_simulation_value_distribution_bins("run-xyz", [])
    assert result == []
    mock_insert.assert_not_called()
