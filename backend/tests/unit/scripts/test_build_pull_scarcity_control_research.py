from backend.scripts.build_pull_scarcity_control_research import quantiles, spearman


def test_quantiles_reports_dispersion_and_ratio():
    result = quantiles([0.01, 0.02, 0.03, 0.04, 0.05])
    assert result == {
        "n": 5, "min": 0.01, "p25": 0.02, "median": 0.03,
        "p75": 0.04, "max": 0.05, "iqr": 0.02, "ratioMaxMin": 5.0,
    }


def test_spearman_handles_monotonic_and_unidentified_inputs():
    assert spearman([1, 2, 3], [10, 20, 30]) == 1.0
    assert spearman([1, 2, 3], [30, 20, 10]) == -1.0
    assert spearman([1, 1, 1], [10, 20, 30]) is None
