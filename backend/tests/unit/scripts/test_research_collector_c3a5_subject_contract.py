import pytest

from backend.scripts.research_collector_c3a5_subject_contract import (
    concentration,
    set_overlap,
    transformed_distribution,
)


def test_set_overlap_reports_intersection_union_and_share():
    assert set_overlap({"a": 3, "b": 2, "c": 1}, {"a": 1, "b": 3, "c": 2}, 2) == (1, 3, 0.5)


def test_concentration_uses_share_of_total_signal():
    assert concentration({"a": 6, "b": 3, "c": 1}, 2) == pytest.approx(0.9)


def test_saturation_is_bounded_monotonic_and_preserves_zero():
    result = transformed_distribution({"zero": 0, "low": 10, "high": 20})
    assert result["zero"] == 0
    assert 0 < result["low"] < result["high"] < 100
