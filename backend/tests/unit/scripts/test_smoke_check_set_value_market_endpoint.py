"""The public smoke test must catch an unpublished global Market Set Value snapshot.

The exact production failure this covers: the aggregate was never bootstrapped,
so GET /explore/set-value-market returned 404
POKEMON_EXPLORE_SET_VALUE_UNAVAILABLE and /Market rendered its "temporarily
unavailable" fallback — while every other smoke-checked endpoint was healthy.
"""

from __future__ import annotations

from backend.scripts.smoke_check_public_snapshot_endpoints import _check_set_value_market

DATE = "2026-08-15"


def _row(**overrides):
    row = {"setId": "set-1", "currentSetValue": 100.0, "setValueAsOf": DATE}
    row.update(overrides)
    return row


def _payload(sets=None, **overrides):
    payload = {
        "sets": [_row()] if sets is None else sets,
        "meta": {"snapshot": {"marketDate": DATE}},
    }
    payload.update(overrides)
    return payload


def test_healthy_payload_reports_no_failures():
    assert _check_set_value_market(200, _payload(), 1) == []


def test_404_unavailable_fails_the_smoke_test():
    failures = _check_set_value_market(
        404, {"code": "POKEMON_EXPLORE_SET_VALUE_UNAVAILABLE"}, 22
    )

    assert len(failures) == 1
    assert "status=404" in failures[0]
    assert "POKEMON_EXPLORE_SET_VALUE_UNAVAILABLE" in failures[0]


def test_500_fails_the_smoke_test():
    assert _check_set_value_market(500, None, 22)


def test_zero_sets_fails():
    failures = _check_set_value_market(200, _payload(sets=[]), None)
    assert failures == ["explore_set_value_market published zero sets"]


def test_sets_must_be_an_array():
    failures = _check_set_value_market(200, {"sets": {}, "meta": {}}, None)
    assert failures == ["explore_set_value_market payload.sets is not an array"]


def test_cohort_shortfall_is_reported():
    failures = _check_set_value_market(200, _payload(), 22)
    assert any("expected cohort of 22" in failure for failure in failures)


def test_unknown_cohort_size_does_not_manufacture_a_failure():
    """A cohort lookup that fails must not invent a count mismatch."""
    assert _check_set_value_market(200, _payload(), None) == []


def test_missing_market_date_metadata_fails():
    payload = _payload()
    payload["meta"] = {}
    failures = _check_set_value_market(200, payload, None)
    assert any("meta.snapshot.marketDate" in failure for failure in failures)


def test_row_without_set_id_fails():
    failures = _check_set_value_market(200, _payload(sets=[_row(setId=None)]), None)
    assert any("no setId" in failure for failure in failures)


def test_non_positive_current_set_value_fails():
    for bad in (0, -1.0, None, "n/a"):
        failures = _check_set_value_market(200, _payload(sets=[_row(currentSetValue=bad)]), None)
        assert any("positive currentSetValue" in failure for failure in failures), bad
