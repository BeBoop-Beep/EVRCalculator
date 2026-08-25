from datetime import date, timedelta

import pytest

from backend.domain.pokemon.market_index import (
    build_comparison_windows,
    build_chain_linked_history,
    compute_comparison_window_movements,
    compute_strict_window_movements,
    deterministic_fingerprint,
    resolve_window_baselines,
    resolve_one_day_comparison_close,
)


def obs(day, **values):
    return {"marketDate": day, "constituents": [{"setId": key, "setValue": value} for key, value in values.items()]}


def test_same_cohort_and_new_entry_are_chain_linked():
    rows = build_chain_linked_history([obs("2026-01-01", A=100, B=100), obs("2026-01-02", A=110, B=110, C=500)])
    assert rows[-1]["basketValue"] == 720
    assert rows[-1]["normalizedIndexValue"] == pytest.approx(110)
    assert rows[-1]["dailyReturn"] == pytest.approx(.10)


def test_set_exit_does_not_create_artificial_loss():
    rows = build_chain_linked_history([obs("2026-01-01", A=100, B=100, C=500), obs("2026-01-02", A=110, B=110)])
    assert rows[-1]["normalizedIndexValue"] == pytest.approx(110)


def test_strict_windows_and_since_tracking():
    points = [{"date": f"2026-01-{day:02d}", "value": day} for day in range(1, 32)]
    points += [{"date": f"2026-02-{day:02d}", "value": 31 + day} for day in range(1, 29)]
    points += [{"date": f"2026-03-{day:02d}", "value": 59 + day} for day in range(1, 32)]
    points += [{"date": f"2026-04-{day:02d}", "value": 90 + day} for day in range(1, 31)]
    windows = compute_strict_window_movements(points)
    assert windows["3M"]["available"] is True
    assert windows["6M"]["available"] is False
    assert windows["1Y"]["available"] is False
    assert windows["SinceTracking"]["available"] is True


def test_named_windows_use_true_elapsed_day_targets():
    end = date(2026, 8, 24)
    points = [
        {"date": (end - timedelta(days=offset)).isoformat(), "value": 400 - offset}
        for offset in reversed(range(366))
    ]
    windows = compute_strict_window_movements(points)
    assert windows["7D"]["targetStartDate"] == windows["7D"]["startDate"] == "2026-08-17"
    assert windows["30D"]["targetStartDate"] == windows["30D"]["startDate"] == "2026-07-25"
    assert windows["3M"]["targetStartDate"] == windows["3M"]["startDate"] == "2026-05-26"
    assert windows["6M"]["targetStartDate"] == windows["6M"]["startDate"] == "2026-02-25"
    assert windows["1Y"]["targetStartDate"] == windows["1Y"]["startDate"] == "2025-08-24"


def test_sparse_window_uses_newest_present_observation_on_or_before_target():
    windows = resolve_window_baselines(["2026-08-16", "2026-08-18", "2026-08-24"])
    assert windows["7D"] == {
        "targetStartDate": "2026-08-17",
        "startDate": "2026-08-16",
        "endDate": "2026-08-24",
        "available": True,
    }
    assert windows["1D"]["startDate"] == "2026-08-18"
    assert windows["SinceTracking"]["startDate"] == "2026-08-16"


def test_fingerprint_is_order_independent_for_mapping_keys():
    assert deterministic_fingerprint({"a": 1, "b": 2}) == deterministic_fingerprint({"b": 2, "a": 1})


def test_comparison_windows_use_inclusive_calendar_domains_and_common_all_start():
    common = ["2026-04-26", "2026-05-27", "2026-07-26", "2026-08-18", "2026-08-23", "2026-08-24"]
    windows = build_comparison_windows("2026-08-24", [
        ["2026-04-23", *common], ["2026-04-23", *common], ["2026-04-07", *common],
    ])
    assert windows["1D"]["displayStartDate"] == "2026-08-23"
    assert windows["7D"]["displayStartDate"] == "2026-08-18"
    assert windows["30D"]["displayStartDate"] == "2026-07-26"
    assert windows["3M"]["displayStartDate"] == "2026-05-27"
    assert windows["6M"]["targetStartDate"] == "2026-02-26"
    assert windows["1Y"]["targetStartDate"] == "2025-08-25"
    assert windows["6M"]["displayStartDate"] == "2026-04-26"
    assert windows["1Y"]["displayStartDate"] == "2026-04-26"
    assert windows["SinceTracking"]["displayStartDate"] == "2026-04-26"
    assert windows["7D"]["available"] is True
    assert windows["6M"]["available"] is True
    assert windows["6M"]["coverage"] == "partial"
    assert windows["6M"]["isSinceFirstAvailable"] is True
    assert windows["1Y"]["available"] is True
    assert windows["1Y"]["coverage"] == "partial"
    assert all(window["displayEndDate"] == "2026-08-24" for window in windows.values())


def test_comparison_baseline_requires_the_exact_common_boundary():
    dates = ["2026-07-16", "2026-07-29", "2026-08-24"]
    windows = build_comparison_windows("2026-08-24", [dates, dates, dates])
    changes = compute_comparison_window_movements([
        {"date": "2026-07-16", "value": 100},
        {"date": "2026-07-29", "value": 105},
        {"date": "2026-08-24", "value": 110},
    ], windows)
    assert changes["30D"]["startDate"] is None
    assert changes["30D"]["coverage"] == "unavailable"


def test_comparison_1d_gap_is_unavailable_instead_of_expanding_domain():
    dates = ["2026-08-22", "2026-08-24"]
    windows = build_comparison_windows("2026-08-24", [dates, dates, dates])
    changes = compute_comparison_window_movements([
        {"date": "2026-08-22", "value": 100},
        {"date": "2026-08-24", "value": 101},
    ], windows)
    assert windows["1D"]["displayStartDate"] == "2026-08-23"
    assert changes["1D"]["available"] is False
    assert changes["1D"]["percent"] is None


def test_comparison_1d_is_selectable_when_two_families_have_yesterday():
    windows = build_comparison_windows("2026-08-24", [
        ["2026-08-23", "2026-08-24"],
        ["2026-08-23", "2026-08-24"],
        ["2026-08-22", "2026-08-24"],
    ])
    assert windows["1D"]["available"] is True
    assert windows["1D"]["displayStartDate"] == "2026-08-23"
    raw = compute_comparison_window_movements([
        {"date": "2026-08-23", "value": 100}, {"date": "2026-08-24", "value": 101},
    ], windows)
    sealed = compute_comparison_window_movements([
        {"date": "2026-08-22", "value": 100}, {"date": "2026-08-24", "value": 101},
    ], windows)
    assert raw["1D"]["available"] is True
    assert sealed["1D"]["available"] is False


def test_partial_long_windows_match_all_and_mature_automatically():
    partial = build_comparison_windows("2026-08-24", [["2026-04-26", "2026-08-24"]] * 3)
    for key in ("6M", "1Y"):
        assert partial[key]["displayStartDate"] == partial["SinceTracking"]["displayStartDate"]
        assert partial[key]["coverage"] == "partial"
        assert partial[key]["isSinceFirstAvailable"] is True

    dates = ["2025-08-25", "2026-02-26", "2026-08-24"]
    mature = build_comparison_windows("2026-08-24", [dates] * 3)
    for key, target in (("6M", "2026-02-26"), ("1Y", "2025-08-25")):
        assert mature[key]["displayStartDate"] == target
        assert mature[key]["coverage"] == "full"
        assert mature[key]["isSinceFirstAvailable"] is False


def test_one_day_previous_close_is_observed_when_consecutive():
    result = resolve_one_day_comparison_close([
        {"date": "2026-08-23", "value": 106, "chainSegmentId": 4},
        {"date": "2026-08-24", "value": 105, "chainSegmentId": 4},
    ], target_date="2026-08-23", market_date="2026-08-24")
    assert result["available"] is True
    assert result["coverage"] == "full"
    assert result["isCarriedForwardBaseline"] is False
    assert result["baselineSourceDate"] == "2026-08-23"


def test_one_day_previous_close_carries_exactly_one_isolated_gap():
    history = [
        {"date": "2026-08-22", "value": 106.21882536871614, "chainSegmentId": 4},
        {"date": "2026-08-24", "value": 106.17849310930887, "chainSegmentId": 4},
    ]
    result = resolve_one_day_comparison_close(
        history, target_date="2026-08-23", market_date="2026-08-24"
    )
    assert result["available"] is True
    assert result["coverage"] == "carried_previous_close"
    assert result["baselineSourceDate"] == "2026-08-22"
    assert result["percent"] == pytest.approx(-0.0379709081)
    assert result["comparisonTrend"] == [
        {"date": "2026-08-23", "value": 106.21882536871614,
         "isObserved": False, "isCarriedForward": True, "sourceDate": "2026-08-22"},
        {"date": "2026-08-24", "value": 106.17849310930887,
         "isObserved": True, "isCarriedForward": False, "sourceDate": "2026-08-24"},
    ]
    assert [point["date"] for point in history] == ["2026-08-22", "2026-08-24"]


@pytest.mark.parametrize("history", [
    [{"date": "2026-08-21", "value": 106, "chainSegmentId": 1},
     {"date": "2026-08-24", "value": 105, "chainSegmentId": 1}],
    [{"date": "2026-08-22", "value": 106, "chainSegmentId": 1},
     {"date": "2026-08-23", "value": 105, "chainSegmentId": 1}],
    [{"date": "2026-08-22", "value": 106, "chainSegmentId": 1},
     {"date": "2026-08-24", "value": 105, "chainSegmentId": 2}],
])
def test_one_day_previous_close_rejects_long_gap_missing_current_or_chain_break(history):
    result = resolve_one_day_comparison_close(
        history, target_date="2026-08-23", market_date="2026-08-24"
    )
    assert result["available"] is False
    assert result["comparisonTrend"] == []
