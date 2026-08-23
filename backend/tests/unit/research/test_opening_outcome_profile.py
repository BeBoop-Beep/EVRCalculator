import numpy as np
import pytest

from backend.research.opening_outcome_profile import compute_profile, profile_from_persisted


def test_exact_boundaries_partition_once_and_sum_to_one():
    result = compute_profile(np.array([0, 2.5, 5, 7.5, 10, 15, 20, 50], dtype=float), 10)
    assert [row["occurrenceCount"] for row in result["buckets"]] == [1] * 8
    assert sum(row["occurrenceCount"] for row in result["buckets"]) == 8
    assert sum(row["probability"] for row in result["buckets"]) == pytest.approx(1)


@pytest.mark.parametrize("cost", [0, -1, float("nan")])
def test_non_positive_or_nonfinite_cost_is_rejected(cost):
    with pytest.raises(ValueError):
        compute_profile([1, 2], cost)


def test_invalid_persisted_partition_is_rejected():
    profile = compute_profile([1, 2, 3], 10)
    raw = {"cost": 10, "sampleSize": 4, "buckets": [
        {"ratioFloor": row["floorRatio"], "ratioCeiling": row["ceilingRatio"],
         "occurrenceCount": row["occurrenceCount"], "probability": row["probability"]}
        for row in profile["buckets"]
    ]}
    with pytest.raises(ValueError):
        profile_from_persisted(raw)


def test_each_probability_must_reconcile_to_its_own_occurrence_count():
    profile = compute_profile([0, 1, 2, 3, 6], 10)
    raw = {"cost": 10, "sampleSize": 5, "buckets": [
        {"ratioFloor": row["floorRatio"], "ratioCeiling": row["ceilingRatio"],
         "occurrenceCount": row["occurrenceCount"], "probability": row["probability"]}
        for row in profile["buckets"]
    ]}
    raw["buckets"][0]["probability"], raw["buckets"][2]["probability"] = (
        raw["buckets"][2]["probability"], raw["buckets"][0]["probability"]
    )
    assert sum(row["occurrenceCount"] for row in raw["buckets"]) == raw["sampleSize"]
    assert sum(row["probability"] for row in raw["buckets"]) == pytest.approx(1)
    with pytest.raises(ValueError, match="probability/count mismatch"):
        profile_from_persisted(raw)
