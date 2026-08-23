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
