import pytest

from backend.domain.pokemon.market_index import build_chain_linked_history, compute_strict_window_movements, deterministic_fingerprint


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


def test_fingerprint_is_order_independent_for_mapping_keys():
    assert deterministic_fingerprint({"a": 1, "b": 2}) == deterministic_fingerprint({"b": 2, "a": 1})
