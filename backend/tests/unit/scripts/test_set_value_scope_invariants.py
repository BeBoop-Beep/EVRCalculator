import math

import pytest

from backend.scripts.set_value_scope_invariants import (
    SetValueScopeInvariantError,
    audit_set_value_scope_rows,
    validate_set_value_scope_rows,
)


def _rows(*, standard=100.0, hits=80.0, top10=70.0, set_id="set-1", date="2026-06-16"):
    return [
        {"set_id": set_id, "snapshot_date": date, "value_scope": "standard", "set_value": standard},
        {"set_id": set_id, "snapshot_date": date, "value_scope": "hits", "set_value": hits},
        {"set_id": set_id, "snapshot_date": date, "value_scope": "top10", "set_value": top10},
    ]


def test_hits_below_or_equal_to_checklist_passes():
    validate_set_value_scope_rows(_rows(hits=99.99))
    validate_set_value_scope_rows(_rows(hits=100.0))


def test_hits_above_checklist_beyond_currency_tolerance_fails():
    validate_set_value_scope_rows(_rows(hits=100.01))
    with pytest.raises(SetValueScopeInvariantError) as exc_info:
        validate_set_value_scope_rows(_rows(hits=100.02))
    assert exc_info.value.details["scope"] == "hits"
    assert exc_info.value.details["subsetValue"] == 100.02
    assert exc_info.value.details["checklistValue"] == 100.0


def test_top10_above_checklist_fails_without_assuming_top10_is_below_hits():
    validate_set_value_scope_rows(_rows(hits=60.0, top10=90.0))
    with pytest.raises(SetValueScopeInvariantError) as exc_info:
        validate_set_value_scope_rows(_rows(hits=60.0, top10=100.02))
    assert exc_info.value.details["scope"] == "top10"


@pytest.mark.parametrize("value", [-0.01, math.nan, math.inf, -math.inf, None])
def test_negative_and_non_finite_values_fail(value):
    with pytest.raises(SetValueScopeInvariantError):
        validate_set_value_scope_rows(_rows(hits=value))


def test_system_audit_reports_all_four_chaos_rising_failures_and_keeps_other_set_clean():
    rows = _rows(set_id="healthy", date="2026-06-16")
    for date_key in ("2026-06-16", "2026-06-17", "2026-06-18", "2026-06-19"):
        rows.extend(_rows(set_id="chaos", date=date_key, standard=1097.57, hits=118137.48, top10=941.79))

    report = audit_set_value_scope_rows(rows)

    assert report["hardFailureCount"] == 4
    assert {failure["setId"] for failure in report["hardFailures"]} == {"chaos"}
    assert {failure["date"] for failure in report["hardFailures"]} == {
        "2026-06-16", "2026-06-17", "2026-06-18", "2026-06-19"
    }
